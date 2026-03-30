from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest


class FakeCursor:
    def __init__(self, row) -> None:
        self.row = row
        self.executed: list[tuple[str, object | None]] = []

    def execute(self, query: str, params: object = None) -> None:
        self.executed.append((query, params))

    def fetchone(self):
        return self.row

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def make_request(**overrides: object) -> SimpleNamespace:
    payload = {
        "repoUrl": "https://github.com/example/project",
        "repoSlug": "example__project",
        "userPrompt": "Focus on setup",
        "forceRegenerate": False,
        "repoSnapshot": None,
        "onboardingSnapshot": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_root_and_handler(load_backend_module) -> None:
    main = load_backend_module("app.main")

    assert main.root() == {"message": "Backend is running"}
    assert main.handler.app is main.app


def test_lifespan_initializes_datastores(load_backend_module) -> None:
    main = load_backend_module("app.main")
    calls: list[str] = []
    store = object()
    main.init_db_onboarding_doc = lambda: calls.append("onboarding")
    main.init_db_chat_history = lambda: calls.append("chat")

    def fake_init_pgvectorstore():
        calls.append("pgvector")
        return store

    main.init_pgvectorstore = fake_init_pgvectorstore

    async def run_lifespan() -> None:
        async with main.lifespan(main.app):
            calls.append("running")

    asyncio.run(run_lifespan())

    assert calls == ["onboarding", "chat", "pgvector", "running"]
    assert main.pgvectorstore is store


def test_debug_db_runs_query(load_backend_module) -> None:
    main = load_backend_module("app.main")
    db = importlib.import_module("app.services.db")
    cursor = FakeCursor((1,))
    db.get_connection = lambda: FakeConnection(cursor)

    result = main.debug_db()

    assert result == {"status": "ok", "result": "1"}
    assert cursor.executed == [("SELECT 1;", None)]


def test_generate_onboarding_rejects_invalid_key(load_backend_module) -> None:
    main = load_backend_module("app.main")
    request = make_request(accessKey="bad-key")

    with pytest.raises(main.HTTPException) as exc_info:
        main.generate_onboarding(request, x_access_key="bad-key")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid access key"


def test_generate_onboarding_returns_cached_document(load_backend_module) -> None:
    main = load_backend_module("app.main")
    main.verify_key = lambda access_key: True
    main.load_object_from_s3 = lambda object_key: "# Cached guide"

    response = main.generate_onboarding(
        make_request(repoSnapshot={"repo_slug": "example__project"}),
        x_access_key="alpha",
    )

    assert response.success is True
    assert response.document == "# Cached guide"
    assert response.storageKey == "onboarding_docs/alpha/example__project.md"
    assert response.fromCache is True


def test_generate_onboarding_cached_load_failure_returns_http_500(load_backend_module) -> None:
    main = load_backend_module("app.main")
    main.verify_key = lambda access_key: True

    def fail_load(object_key: str) -> str:
        raise RuntimeError("s3 unavailable")

    main.load_object_from_s3 = fail_load

    with pytest.raises(main.HTTPException) as exc_info:
        main.generate_onboarding(
            make_request(repoSnapshot={"repo_slug": "example__project"}),
            x_access_key="alpha",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to load cached document"


def test_generate_onboarding_generates_and_saves_document(load_backend_module) -> None:
    main = load_backend_module("app.main")
    saved_calls: dict[str, object] = {}
    repo_calls: list[tuple[str, str]] = []
    main.verify_key = lambda access_key: True
    main.load_object_from_s3 = lambda object_key: None
    main.retrieve_context = (
        lambda repo_url, repo_snapshot=None, onboarding_snapshot=None:
        f"context for {repo_url}::{repo_snapshot}::{onboarding_snapshot}"
    )
    main.build_prompt = lambda user_prompt, context: f"prompt::{user_prompt}::{context}"
    main.generate_document = lambda prompt, repo_url: "# Fresh guide"

    def save_object_to_s3(object_key: str, obj: str) -> bool:
        saved_calls.update(
            {
                "object_key": object_key,
                "obj": obj,
            }
        )
        return True

    def save_onboarding_doc_repo(access_key: str, repo_slug: str) -> bool:
        repo_calls.append((access_key, repo_slug))
        return True

    main.save_object_to_s3 = save_object_to_s3
    main.save_onboarding_doc_repo = save_onboarding_doc_repo

    snapshot = {
        "repo_slug": "example__project",
        "files": ["README.md", "backend/app/main.py"],
        "selected_file_contents": [{"path": "README.md", "content": "# Project"}],
    }
    onboarding_snapshot = {
        "repo_slug": "example__project",
        "structure_summary": {"total_files": 2},
    }
    response = main.generate_onboarding(
        make_request(
            forceRegenerate=True,
            repoSnapshot=snapshot,
            onboardingSnapshot=onboarding_snapshot,
        ),
        x_access_key="alpha",
    )

    assert response.success is True
    assert response.document == "# Fresh guide"
    assert response.storageKey == "onboarding_docs/alpha/example__project.md"
    assert response.fromCache is False
    assert saved_calls == {
        "object_key": "onboarding_docs/alpha/example__project.md",
        "obj": "# Fresh guide",
    }
    assert repo_calls == [("alpha", "example__project")]


def test_generate_onboarding_requires_repo_slug(load_backend_module) -> None:
    main = load_backend_module("app.main")
    main.verify_key = lambda access_key: True

    with pytest.raises(main.HTTPException) as exc_info:
        main.generate_onboarding(make_request(repoSlug=""), x_access_key="alpha")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "repoSlug is required in the request body"


def test_generate_onboarding_generation_failure_returns_http_500(load_backend_module) -> None:
    main = load_backend_module("app.main")
    main.verify_key = lambda access_key: True
    main.load_object_from_s3 = lambda object_key: None

    def fail_generation(repo_url: str, repo_snapshot=None, onboarding_snapshot=None) -> str:
        raise RuntimeError("rag unavailable")

    main.retrieve_context = fail_generation

    with pytest.raises(main.HTTPException) as exc_info:
        main.generate_onboarding(
            make_request(repoSnapshot={"repo_slug": "example__project"}),
            x_access_key="alpha",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Generation failed"
