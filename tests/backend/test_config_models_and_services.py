from __future__ import annotations

from datetime import datetime, timezone
import io
import types

import pytest
from pydantic import ValidationError


class FakeCursor:
    def __init__(self, row=None) -> None:
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
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_config_parses_env_and_defaults(monkeypatch: pytest.MonkeyPatch, load_backend_module) -> None:
    monkeypatch.setenv("ACCESS_KEYS", " alpha , beta ,, gamma ")
    config = load_backend_module("app.config")

    assert config.ACCESS_KEYS == ["alpha", "beta", "gamma"]
    assert config.AWS_REGION == "ca-central-1"
    assert config.DB_SSLMODE == "require"
    assert config.BEDROCK_MODEL_ID == "bedrock-test-model"
    assert config.S3_BUCKET_NAME == "test-bucket"


@pytest.mark.parametrize(
    ("env_name", "env_value", "message"),
    [
        ("ACCESS_KEYS", None, "ACCESS_KEYS environment variable is not set"),
        ("BEDROCK_MODEL_ID", None, "BEDROCK_MODEL_ID environment variable is not set"),
        ("S3_BUCKET_NAME", None, "S3_BUCKET_NAME environment variable is not set"),
        ("DB_HOST", None, "RDS database environment variables are not fully set"),
    ],
)
def test_config_raises_for_missing_required_values(
    monkeypatch: pytest.MonkeyPatch,
    load_backend_module,
    env_name: str,
    env_value: str | None,
    message: str,
) -> None:
    if env_value is None:
        monkeypatch.delenv(env_name, raising=False)
    else:
        monkeypatch.setenv(env_name, env_value)

    with pytest.raises(ValueError, match=message):
        load_backend_module("app.config")


def test_models_validate_fields(load_backend_module) -> None:
    models = load_backend_module("app.models")

    request = models.GenerateOnboardingRequest(
        repoUrl="https://github.com/example/project",
        repoSlug="example__project",
        userPrompt="Focus on setup",
        repoSnapshot={
            "repo_slug": "example__project",
            "files": ["README.md", "backend/app/main.py"],
            "selected_file_contents": [{"path": "README.md", "content": "# Project", "truncated": False}],
        },
        onboardingSnapshot={
            "repo_slug": "example__project",
            "structure_summary": {"total_files": 2},
            "hotspots": [{"path": "README.md", "touch_count": 3, "last_touched": "2026-03-30T12:00:00Z"}],
            "risk_matrix": [{"path": "README.md", "risk_level": "low", "risk_score": 0.2}],
            "co_change_pairs": [{"file_a": "README.md", "file_b": "backend/app/main.py", "co_change_count": 2}],
            "authorship_summary": [
                {
                    "path": "README.md",
                    "total_commits": 3,
                    "primary_contributors": [{"name": "Alice", "commit_count": 3}],
                }
            ],
            "conventions": {"test_framework": {"name": "pytest", "config_path": "pytest.ini"}},
        },
    )
    response = models.GenerateOnboardingResponse(
        success=True,
        document="# Guide",
        storageKey="outputs/repo/v1.md",
        fromCache=False,
    )

    assert str(request.repoUrl) == "https://github.com/example/project"
    assert request.repoSnapshot is not None
    assert request.repoSnapshot.repo_slug == "example__project"
    assert request.repoSnapshot.files == ["README.md", "backend/app/main.py"]
    assert request.repoSnapshot.selected_file_contents[0].path == "README.md"
    assert request.onboardingSnapshot is not None
    assert request.onboardingSnapshot.repo_slug == "example__project"
    assert response.storageKey == "outputs/repo/v1.md"

    with pytest.raises(ValidationError):
        models.GenerateOnboardingRequest(
            repoUrl="not-a-url",
        )

    save_chat = models.SaveChatRequest(
        repo_slug="example__project",
        role="user",
        message="Hello",
    )
    assert save_chat.repo_slug == "example__project"


def test_auth_verify_key(load_backend_module) -> None:
    auth = load_backend_module("app.services.auth")

    assert auth.verify_key("alpha") is True
    assert auth.verify_key("missing") is False


def test_prompt_builder_handles_optional_user_prompt(load_backend_module) -> None:
    prompt_builder = load_backend_module("app.services.prompt_builder")

    without_user_prompt = prompt_builder.build_prompt(None, "repo context")
    with_user_prompt = prompt_builder.build_prompt("  mention tests  ", "repo context")

    assert "Additional user request" not in without_user_prompt
    assert "Repository context:\nrepo context" in without_user_prompt
    assert "Additional user request" in with_user_prompt
    assert "mention tests" in with_user_prompt


def test_retrieval_includes_repo_url(load_backend_module) -> None:
    retrieval = load_backend_module("app.services.retrieval")

    result = retrieval.retrieve_context("https://github.com/example/project")

    assert "https://github.com/example/project" in result
    assert "Repository snapshot: not provided" in result


def test_retrieval_uses_repo_snapshot_file_inventory(load_backend_module) -> None:
    retrieval = load_backend_module("app.services.retrieval")
    models = load_backend_module("app.models")

    snapshot = models.RepoSnapshot(
        repo_slug="example__project",
        files=[
            "README.md",
            "backend/app/main.py",
            ".github/workflows/tests.yml",
            "pytest.ini",
        ],
        selected_file_contents=[
            models.RepoFileContent(path="README.md", content="# Project", truncated=False),
            models.RepoFileContent(path="pytest.ini", content="[pytest]\naddopts = -v", truncated=False),
        ],
    )
    onboarding_snapshot = models.OnboardingSnapshot(
        repo_slug="example__project",
        structure_summary={
            "total_files": 4,
            "top_level_directories": [{"path": "backend", "file_count": 1}],
            "file_type_counts": [{"extension": ".py", "count": 1}],
            "start_here_candidates": [{"path": "README.md", "reasons": ["project_overview"]}],
        },
        hotspots=[{"path": "backend/app/main.py", "touch_count": 6, "last_touched": "2026-03-30T12:00:00Z"}],
        risk_matrix=[{"path": "backend/app/main.py", "risk_level": "medium", "risk_score": 0.6}],
        co_change_pairs=[{"file_a": "README.md", "file_b": "backend/app/main.py", "co_change_count": 3}],
        authorship_summary=[
            {
                "path": "backend/app/main.py",
                "total_commits": 6,
                "primary_contributors": [
                    {"name": "Alice", "commit_count": 4},
                    {"name": "Bob", "commit_count": 2},
                ],
            }
        ],
        conventions={"test_framework": {"name": "pytest", "config_path": "pytest.ini"}},
    )

    result = retrieval.retrieve_context("https://github.com/example/project", snapshot, onboarding_snapshot)

    assert "All repository file paths:" in result
    assert "- backend/app/main.py" in result
    assert "Repository slug: example__project" in result
    assert "Hotspots:" in result
    assert "Risk areas:" in result
    assert "Frequently co-changed files:" in result
    assert "Ownership examples:" in result
    assert "Detected conventions:" in result
    assert "Selected file contents:" in result


def test_db_get_connection_uses_config_values(load_backend_module) -> None:
    db = load_backend_module("app.services.db")
    captured: dict[str, object] = {}

    def fake_connect(**kwargs: object) -> str:
        captured.update(kwargs)
        return "connection"

    db.psycopg = types.SimpleNamespace(connect=fake_connect)

    assert db.get_connection() == "connection"
    assert captured == {
        "host": "db.example.com",
        "port": "5432",
        "dbname": "contribnow",
        "user": "postgres",
        "password": "secret",
        "sslmode": "require",
    }


def test_init_db_onboarding_doc_executes_query_and_commits(load_backend_module) -> None:
    db_init = load_backend_module("app.services.db_init")
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    db_init.get_connection = lambda: connection

    db_init.init_db_onboarding_doc()

    assert len(cursor.executed) == 1
    assert "CREATE TABLE IF NOT EXISTS onboarding_user_repos" in cursor.executed[0][0]
    assert "CREATE INDEX IF NOT EXISTS idx_onboarding_user_repos_access_key" in cursor.executed[0][0]
    assert connection.commits == 1


def test_init_db_chat_history_executes_query_and_commits(load_backend_module) -> None:
    db_init = load_backend_module("app.services.db_init")
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    db_init.get_connection = lambda: connection

    db_init.init_db_chat_history()

    assert len(cursor.executed) == 1
    assert "CREATE TABLE IF NOT EXISTS chat_history" in cursor.executed[0][0]
    assert "repo_slug TEXT NOT NULL" in cursor.executed[0][0]
    assert "CREATE INDEX IF NOT EXISTS idx_chat_history_access_key_repo_slug_created_at" in cursor.executed[0][0]
    assert connection.commits == 1


def test_cache_helpers_cover_success_and_failure_paths(load_backend_module) -> None:
    cache = load_backend_module("app.services.cache")

    assert cache.normalize_repo_url(" HTTPS://GitHub.com/Example/Repo/ ") == "https://github.com/example/repo"
    assert cache.get_repo_id("https://github.com/example/repo") == cache.get_repo_id("https://github.com/example/repo/")

    cache.get_connection = lambda: FakeConnection(FakeCursor(None))
    assert cache.get_cached_document("https://github.com/example/repo") is None

    created_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    cache.get_connection = lambda: FakeConnection(
        FakeCursor(("repo-id", "https://github.com/example/repo", 7, "outputs/key.md", created_at))
    )
    cached = cache.get_cached_document("https://github.com/example/repo")
    assert cached == {
        "repoId": "repo-id",
        "repoUrl": "https://github.com/example/repo",
        "version": 7,
        "storageKey": "outputs/key.md",
        "createdAt": created_at.isoformat(),
    }

    cache.get_connection = lambda: FakeConnection(FakeCursor((5,)))
    assert cache.get_next_version("https://github.com/example/repo") == 5

    cache.get_connection = lambda: FakeConnection(FakeCursor(None))
    with pytest.raises(RuntimeError, match="Failed to get next version"):
        cache.get_next_version("https://github.com/example/repo")

    save_cursor = FakeCursor(("repo-id", "https://github.com/example/repo", 8, "outputs/key.md", None))
    save_connection = FakeConnection(save_cursor)
    cache.get_connection = lambda: save_connection
    saved = cache.save_cached_document(
        repo_url="https://github.com/example/repo/",
        storage_key="outputs/key.md",
        version=8,
    )

    assert saved == {
        "repoId": "repo-id",
        "repoUrl": "https://github.com/example/repo",
        "version": 8,
        "storageKey": "outputs/key.md",
        "createdAt": None,
    }
    assert save_connection.commits == 1
    assert save_cursor.executed[0][1][1] == "https://github.com/example/repo"

    cache.get_connection = lambda: FakeConnection(FakeCursor(None))
    with pytest.raises(RuntimeError, match="Failed to save cached document"):
        cache.save_cached_document(
            repo_url="https://github.com/example/repo",
            storage_key="outputs/key.md",
            version=9,
        )


def test_storage_save_and_load_document(load_backend_module) -> None:
    storage = load_backend_module("app.services.storage")
    calls: dict[str, object] = {}

    class FakeS3Client:
        def put_object(self, **kwargs: object) -> None:
            calls["put"] = kwargs

        def get_object(self, **kwargs: object) -> dict[str, object]:
            calls["get"] = kwargs
            return {"Body": io.BytesIO(b"# Stored markdown")}

    storage.s3_client = FakeS3Client()

    key = storage.save_document("Hello", "repo-id", 3)
    loaded = storage.load_document(key)

    assert key == "outputs/repo-id/v3.md"
    assert loaded == "# Stored markdown"
    assert calls["put"] == {
        "Bucket": "test-bucket",
        "Key": "outputs/repo-id/v3.md",
        "Body": b"Hello",
        "ContentType": "text/markdown; charset=utf-8",
    }
    assert calls["get"] == {
        "Bucket": "test-bucket",
        "Key": "outputs/repo-id/v3.md",
    }


def test_llm_generate_document_success_and_empty_response(load_backend_module) -> None:
    llm = load_backend_module("app.services.llm")
    captured: dict[str, object] = {}

    class FakeBedrockClient:
        def invoke_model(self, **kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {
                "body": io.BytesIO(
                    b'{"content":[{"type":"text","text":"# Guide"},{"type":"tool","text":"ignore"},{"type":"text","text":"\\nMore"}]}'
                )
            }

    llm.boto3 = types.SimpleNamespace(
        client=lambda service_name, region_name=None: FakeBedrockClient()
    )

    assert llm.generate_document("Prompt text", "https://github.com/example/repo") == "# Guide\nMore"
    assert captured["modelId"] == "bedrock-test-model"
    assert captured["contentType"] == "application/json"
    assert captured["accept"] == "application/json"
    assert "Prompt text" in captured["body"]

    class EmptyBedrockClient:
        def invoke_model(self, **kwargs: object) -> dict[str, object]:
            return {"body": io.BytesIO(b'{"content":[{"type":"tool","text":"ignore"}]}')}

    llm.boto3 = types.SimpleNamespace(
        client=lambda service_name, region_name=None: EmptyBedrockClient()
    )

    with pytest.raises(ValueError, match="Bedrock returned an empty response"):
        llm.generate_document("Prompt text", "https://github.com/example/repo")
