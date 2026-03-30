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
        "userPrompt": "Focus on setup",
        "forceRegenerate": False,
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
    main.get_cached_document = lambda repo_url: {
        "storageKey": "outputs/repo/v2.md",
        "version": 2,
    }
    main.load_document = lambda storage_key: "# Cached guide"

    response = main.generate_onboarding(make_request(), x_access_key="alpha")

    assert response.success is True
    assert response.document == "# Cached guide"
    assert response.storageKey == "outputs/repo/v2.md"
    assert response.fromCache is True
    assert response.version == 2


def test_generate_onboarding_cached_load_failure_returns_http_500(load_backend_module) -> None:
    main = load_backend_module("app.main")
    main.verify_key = lambda access_key: True
    main.get_cached_document = lambda repo_url: {
        "storageKey": "outputs/repo/v2.md",
        "version": 2,
    }

    def fail_load(storage_key: str) -> str:
        raise RuntimeError("s3 unavailable")

    main.load_document = fail_load

    with pytest.raises(main.HTTPException) as exc_info:
        main.generate_onboarding(make_request(), x_access_key="alpha")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to load cached document"


def test_generate_onboarding_generates_and_saves_document(load_backend_module) -> None:
    main = load_backend_module("app.main")
    saved_calls: dict[str, object] = {}
    cached_calls: dict[str, object] = {}
    main.verify_key = lambda access_key: True
    main.get_cached_document = lambda repo_url: {
        "storageKey": "outputs/repo/v1.md",
        "version": 1,
    }
    main.retrieve_context = lambda repo_url: f"context for {repo_url}"
    main.build_prompt = lambda user_prompt, context: f"prompt::{user_prompt}::{context}"
    main.generate_document = lambda prompt, repo_url: "# Fresh guide"
    main.get_repo_id = lambda repo_url: "repo-id"
    main.get_next_version = lambda repo_url: 2

    def save_document(*, document: str, repo_id: str, version: int) -> str:
        saved_calls.update(
            {
                "document": document,
                "repo_id": repo_id,
                "version": version,
            }
        )
        return "outputs/repo-id/v2.md"

    def save_cached_document(*, repo_url: str, storage_key: str, version: int) -> dict[str, object]:
        cached_calls.update(
            {
                "repo_url": repo_url,
                "storage_key": storage_key,
                "version": version,
            }
        )
        return {
            "storageKey": storage_key,
            "version": version,
        }

    main.save_document = save_document
    main.save_cached_document = save_cached_document

    response = main.generate_onboarding(make_request(forceRegenerate=True), x_access_key="alpha")

    assert response.success is True
    assert response.document == "# Fresh guide"
    assert response.storageKey == "outputs/repo-id/v2.md"
    assert response.fromCache is False
    assert response.version == 2
    assert saved_calls == {
        "document": "# Fresh guide",
        "repo_id": "repo-id",
        "version": 2,
    }
    assert cached_calls == {
        "repo_url": "https://github.com/example/project",
        "storage_key": "outputs/repo-id/v2.md",
        "version": 2,
    }


def test_generate_onboarding_generation_failure_returns_http_500(load_backend_module) -> None:
    main = load_backend_module("app.main")
    main.verify_key = lambda access_key: True
    main.get_cached_document = lambda repo_url: None

    def fail_generation(repo_url: str) -> str:
        raise RuntimeError("rag unavailable")

    main.retrieve_context = fail_generation

    with pytest.raises(main.HTTPException) as exc_info:
        main.generate_onboarding(make_request(), x_access_key="alpha")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Generation failed"
