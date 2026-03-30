from __future__ import annotations

from datetime import datetime, timezone
import io
from types import SimpleNamespace

import numpy as np
import pytest


class RecordingCursor:
    def __init__(
        self,
        *,
        row=None,
        rows=None,
        description=None,
        rowcount: int = 0,
    ) -> None:
        self.row = row
        self.rows = [] if rows is None else list(rows)
        self.description = description
        self.rowcount = rowcount
        self.executed: list[tuple[object, object | None]] = []
        self.executemany_calls: list[tuple[object, object]] = []

    def execute(self, query: object, params: object = None) -> None:
        self.executed.append((query, params))

    def executemany(self, query: object, params: object) -> None:
        self.executemany_calls.append((query, params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor
        self.commits = 0

    def cursor(self) -> RecordingCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_db_init_pgvectorstore_constructs_and_initializes(load_backend_module) -> None:
    db_init = load_backend_module("app.services.db_init")
    captured: dict[str, object] = {}

    class FakeStore:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.ensure_schema_called = False

        def ensure_schema(self) -> None:
            self.ensure_schema_called = True
            captured["ensure_schema_called"] = True

    db_init.PgVectorStore = FakeStore

    store = db_init.init_pgvectorstore()

    assert isinstance(store, FakeStore)
    assert captured == {
        "schema_name": "public",
        "table_name": "rag_vectors",
        "embedding_dimensions": 32,
        "ensure_schema_called": True,
    }


def test_s3_service_covers_success_and_failure_paths(load_backend_module) -> None:
    s3 = load_backend_module("app.services.s3")
    logged: list[str] = []
    puts: list[dict[str, object]] = []
    gets: list[dict[str, object]] = []
    deletes: list[dict[str, object]] = []

    class HappyClient:
        def put_object(self, **kwargs: object) -> None:
            puts.append(kwargs)

        def get_object(self, **kwargs: object) -> dict[str, object]:
            gets.append(kwargs)
            return {"Body": io.BytesIO(b"# Stored")}

        def delete_object(self, **kwargs: object) -> None:
            deletes.append(kwargs)

    s3.logger.error = lambda message: logged.append(message)
    s3.s3_client = HappyClient()

    assert s3.save_object_to_s3("docs/key.md", "hello") is True
    assert s3.load_object_from_s3("docs/key.md") == "# Stored"
    assert s3.delete_object_from_s3("docs/key.md") is True
    assert puts == [{"Bucket": "test-bucket", "Key": "docs/key.md", "Body": b"hello"}]
    assert gets == [{"Bucket": "test-bucket", "Key": "docs/key.md"}]
    assert deletes == [{"Bucket": "test-bucket", "Key": "docs/key.md"}]

    class SaveFailClient:
        def put_object(self, **kwargs: object) -> None:
            raise s3.ClientError("save failed")

    class LoadFailClient:
        def get_object(self, **kwargs: object) -> dict[str, object]:
            raise s3.BotoCoreError("load failed")

    class DeleteFailClient:
        def delete_object(self, **kwargs: object) -> None:
            raise s3.ClientError("delete failed")

    s3.s3_client = SaveFailClient()
    assert s3.save_object_to_s3("docs/key.md", "hello") is False
    s3.s3_client = LoadFailClient()
    assert s3.load_object_from_s3("docs/key.md") is None
    s3.s3_client = DeleteFailClient()
    assert s3.delete_object_from_s3("docs/key.md") is False
    assert any("Failed to save object to S3" in message for message in logged)
    assert any("Failed to load object from S3" in message for message in logged)
    assert any("Failed to delete object from S3" in message for message in logged)


def test_rds_helpers_cover_success_and_error_paths(load_backend_module) -> None:
    rds = load_backend_module("app.services.rds")
    models = load_backend_module("app.models")
    logged: list[str] = []

    def make_connection(cursor: RecordingCursor) -> RecordingConnection:
        return RecordingConnection(cursor)

    rds.logger.error = lambda message: logged.append(message)

    create_cursor = RecordingCursor()
    create_conn = make_connection(create_cursor)
    rds.get_connection = lambda: create_conn
    created = rds.create_kv_table_in_rds("kv_table")
    assert created["status"] == "success"
    assert "kv_table" in str(create_cursor.executed[0][0])
    assert create_conn.commits == 1

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("create boom"))
    create_error = rds.create_kv_table_in_rds("kv_table")
    assert create_error == {
        "status": "error",
        "message": "Failed to create RDS table: create boom",
    }

    save_cursor = RecordingCursor()
    save_conn = make_connection(save_cursor)
    rds.get_connection = lambda: save_conn
    saved = rds.save_value_to_rds("kv_table", "greeting", {"hello": "world"})
    assert saved["status"] == "success"
    assert save_cursor.executed[0][1] == ("greeting", '{"hello": "world"}')
    assert save_conn.commits == 1

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("save boom"))
    save_error = rds.save_value_to_rds("kv_table", "greeting", {"hello": "world"})
    assert save_error == {
        "status": "error",
        "message": "Failed to save value to RDS: save boom",
    }

    description = [SimpleNamespace(name="key"), SimpleNamespace(name="value")]
    load_cursor = RecordingCursor(row=("greeting", {"hello": "world"}), description=description)
    rds.get_connection = lambda: make_connection(load_cursor)
    loaded = rds.load_value_from_rds("kv_table", "greeting")
    assert loaded == {
        "status": "success",
        "row": {"key": "greeting", "value": {"hello": "world"}},
    }

    missing_cursor = RecordingCursor(row=None, description=description)
    rds.get_connection = lambda: make_connection(missing_cursor)
    missing = rds.load_value_from_rds("kv_table", "missing")
    assert missing == {
        "status": "error",
        "message": "No value found for key 'missing' in table 'kv_table'",
    }

    no_desc_cursor = RecordingCursor(row=("greeting", {"hello": "world"}), description=None)
    rds.get_connection = lambda: make_connection(no_desc_cursor)
    no_desc = rds.load_value_from_rds("kv_table", "greeting")
    assert no_desc == {
        "status": "error",
        "message": "Failed to retrieve column information from RDS",
    }

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("load boom"))
    load_error = rds.load_value_from_rds("kv_table", "greeting")
    assert load_error == {
        "status": "error",
        "message": "Failed to load value from RDS: load boom",
    }

    onboarding_cursor = RecordingCursor()
    onboarding_conn = make_connection(onboarding_cursor)
    rds.get_connection = lambda: onboarding_conn
    assert rds.save_onboarding_doc_repo("alpha", "example__project") is True
    assert onboarding_cursor.executed[0][1] == ("alpha", "example__project")
    assert onboarding_conn.commits == 1

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("onboarding boom"))
    assert rds.save_onboarding_doc_repo("alpha", "example__project") is False

    repo_cursor = RecordingCursor(rows=[("repo-a",), ("repo-b",)])
    rds.get_connection = lambda: make_connection(repo_cursor)
    assert rds.load_onboarding_doc_repos("alpha") == ["repo-a", "repo-b"]

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("repo load boom"))
    assert rds.load_onboarding_doc_repos("alpha") == []

    delete_repo_cursor = RecordingCursor(rowcount=2)
    delete_repo_conn = make_connection(delete_repo_cursor)
    rds.get_connection = lambda: delete_repo_conn
    assert rds.delete_onboarding_doc_repo("alpha", "example__project") == 2
    assert delete_repo_conn.commits == 1

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("repo delete boom"))
    assert rds.delete_onboarding_doc_repo("alpha", "example__project") == -1

    chat = models.ChatMessage(role="agent", message="Hi there")
    save_chat_cursor = RecordingCursor()
    save_chat_conn = make_connection(save_chat_cursor)
    rds.get_connection = lambda: save_chat_conn
    assert rds.save_chat_to_rds("alpha", "example__project", chat) is True
    assert save_chat_cursor.executed[0][1] == ("alpha", "example__project", "agent", "Hi there")
    assert save_chat_conn.commits == 1

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("chat save boom"))
    assert rds.save_chat_to_rds("alpha", "example__project", chat) is False

    created_at = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
    history_cursor = RecordingCursor(rows=[("user", "Hello", created_at)])
    rds.get_connection = lambda: make_connection(history_cursor)
    assert rds.load_chat_history_from_rds("alpha", "example__project") == [
        {
            "role": "user",
            "message": "Hello",
            "created_at": created_at.isoformat(),
        }
    ]

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("chat load boom"))
    assert rds.load_chat_history_from_rds("alpha", "example__project") == []

    delete_chat_cursor = RecordingCursor(rowcount=4)
    delete_chat_conn = make_connection(delete_chat_cursor)
    rds.get_connection = lambda: delete_chat_conn
    assert rds.delete_chat_history_from_rds("alpha", "example__project") == 4
    assert delete_chat_conn.commits == 1

    rds.get_connection = lambda: (_ for _ in ()).throw(rds.Error("chat delete boom"))
    assert rds.delete_chat_history_from_rds("alpha", "example__project") == -1
    assert len(logged) == 6


def test_pgvector_store_covers_validation_and_database_methods(load_backend_module) -> None:
    pgvector = load_backend_module("app.services.pgvector")
    interfaces = load_backend_module("app.services.pgvector_interfaces")

    with pytest.raises(ValueError, match="embedding_dimensions must be > 0"):
        pgvector.PgVectorStore(embedding_dimensions=0)
    with pytest.raises(ValueError, match="schema_name must be a non-empty string"):
        pgvector.PgVectorStore(schema_name="", table_name="rag_vectors", embedding_dimensions=3)
    with pytest.raises(ValueError, match="table_name must match SQL identifier pattern"):
        pgvector.PgVectorStore(schema_name="public", table_name="bad-name", embedding_dimensions=3)

    store = pgvector.PgVectorStore(schema_name="public", table_name="rag_vectors", embedding_dimensions=3)
    assert store.name == "pgvector"
    assert store._table_ref == "public.rag_vectors"

    sentinel = object()
    pgvector.get_connection = lambda: sentinel
    assert store._connect() is sentinel

    ensure_cursor = RecordingCursor()
    ensure_conn = RecordingConnection(ensure_cursor)
    store._connect = lambda: ensure_conn
    store.ensure_schema()
    assert len(ensure_cursor.executed) == 4
    assert "CREATE EXTENSION IF NOT EXISTS vector" in ensure_cursor.executed[0][0]
    assert "CREATE TABLE IF NOT EXISTS public.rag_vectors" in ensure_cursor.executed[1][0]
    assert ensure_conn.commits == 1

    assert store.upsert([]) == 0

    upsert_cursor = RecordingCursor()
    upsert_conn = RecordingConnection(upsert_cursor)
    store._connect = lambda: upsert_conn
    record = interfaces.VectorRecord(
        vector=np.array([1.5, 2.5, 3.5], dtype=float),
        repo_slug="example__project",
        head_commit="abc123",
        file_path="backend/app/main.py",
        start_line=10,
        end_line=20,
        data_id="chunk-1",
    )
    assert store.upsert([record]) == 1
    assert "INSERT INTO public.rag_vectors" in upsert_cursor.executemany_calls[0][0]
    assert upsert_cursor.executemany_calls[0][1] == [
        ("example__project", "abc123", "backend/app/main.py", 10, 20, "[1.5,2.5,3.5]")
    ]
    assert upsert_conn.commits == 1

    assert store.delete_by_repo("") == 0
    delete_cursor = RecordingCursor(rowcount=3)
    delete_conn = RecordingConnection(delete_cursor)
    store._connect = lambda: delete_conn
    assert store.delete_by_repo("example__project") == 3
    assert delete_cursor.executed[0][1] == ("example__project",)
    assert delete_conn.commits == 1

    assert store.search(np.array([1.0, 2.0, 3.0], dtype=float), k=0) == []

    search_cursor = RecordingCursor(rows=[("example__project", "abc123", "backend/app/main.py", 10, 20, 0.25)])
    search_conn = RecordingConnection(search_cursor)
    store._connect = lambda: search_conn
    results = store.search(
        np.array([1.0, 2.0, 3.0], dtype=float),
        k=2,
        repo_slug="example__project",
        head_commit="abc123",
        file_path="backend/app/main.py",
    )
    assert len(results) == 1
    assert results[0].score == pytest.approx(0.75)
    assert results[0].vector is None
    assert "WHERE repo_slug = %s AND head_commit = %s AND file_path = %s" in search_cursor.executed[0][0]
    assert search_cursor.executed[0][1] == [
        "[1,2,3]",
        "example__project",
        "abc123",
        "backend/app/main.py",
        2,
    ]

    store._validate_dimensions(np.array([1.0, 2.0, 3.0], dtype=float))
    with pytest.raises(ValueError, match="vector must be a non-empty 1D array"):
        store._validate_dimensions(np.array([], dtype=float))
    with pytest.raises(ValueError, match="vector has dimension 2, expected 3"):
        store._validate_dimensions(np.array([1.0, 2.0], dtype=float))

    assert store._vector_literal(np.array([1.0, 2.0, 3.0], dtype=float)) == "[1,2,3]"
    with pytest.raises(ValueError, match="vector must be a non-empty 1D array"):
        store._vector_literal(np.array([], dtype=float))
    with pytest.raises(ValueError, match="vector values must be finite floats"):
        store._vector_literal(np.array([1.0, np.nan, 3.0], dtype=float))


def test_retrieval_helpers_cover_formatting_and_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
    load_backend_module,
) -> None:
    retrieval = load_backend_module("app.services.retrieval")
    models = load_backend_module("app.models")

    assert retrieval._normalize_files(["src\\app.py", "src/app.py", "", "README.md"]) == ["README.md", "src/app.py"]
    assert retrieval._top_level_counts(["backend/app/main.py", "backend/app/models.py", "README.md"]) == [
        ("backend", 2),
        (".", 1),
    ]
    assert retrieval._file_type_counts(["a.py", "b", "c.TXT"]) == [
        (".py", 1),
        ("[no_ext]", 1),
        (".txt", 1),
    ]

    start_here = retrieval._find_start_here_candidates(
        ["README.md", "CONTRIBUTING.md", "docs/setup.md", "pyproject.toml", "tests/test_api.py"]
    )
    assert start_here[0].startswith("- README.md")
    assert any("documentation" in line for line in start_here)

    selected = [
        models.RepoFileContent(path="pyproject.toml", content="[tool.pytest.ini_options]", truncated=False),
        models.RepoFileContent(path="README.md", content="# Project", truncated=False),
    ]
    conventions = retrieval._detect_conventions(
        [
            "pytest.ini",
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            ".github/workflows/tests.yml",
            "Dockerfile",
            "docker-compose.yml",
            "Makefile",
        ],
        selected,
    )
    assert conventions == [
        "- Tests: pytest is likely configured",
        "- JavaScript package management: package.json is present",
        "- Python packaging: pyproject.toml is present",
        "- Python dependencies: requirements file is present",
        "- CI/CD: GitHub Actions workflow files are present",
        "- Containerization: Docker-related files are present",
        "- Local developer commands may be centralized in Makefile",
    ]

    assert retrieval._format_file_inventory([]) == "No file inventory was provided."
    monkeypatch.setattr(retrieval, "_MAX_FILE_LIST_FOR_PROMPT", 2)
    inventory = retrieval._format_file_inventory(["a", "b", "c"])
    assert inventory == "\n".join(
        [
            "All repository file paths:",
            "- a",
            "- b",
            "- ... 1 more files omitted for prompt size",
        ]
    )
    assert retrieval._truncate_content("abc", 10) == "abc"
    assert retrieval._truncate_content("abcdef", 4) == "abcd\n...[truncated]"

    assert retrieval._format_selected_file_contents([]) == "No selected file contents were provided."
    monkeypatch.setattr(retrieval, "_MAX_TOTAL_CONTENT_CHARS", 0)
    assert retrieval._format_selected_file_contents(selected) == "No file contents fit within the prompt budget."

    monkeypatch.setattr(retrieval, "_MAX_TOTAL_CONTENT_CHARS", 15)
    monkeypatch.setattr(retrieval, "_MAX_FILE_CONTENT_CHARS", 12)
    formatted = retrieval._format_selected_file_contents(
        [
            models.RepoFileContent(path="README.md", content="# Project guide", truncated=True),
            models.RepoFileContent(path="docs/setup.md", content="Install deps and run tests", truncated=False),
        ]
    )
    assert "### README.md (source was truncated before upload)" in formatted
    assert "... 1 additional selected file entries omitted for prompt size" in formatted

    assert retrieval._snapshot_top_level({"top_level_directories": [{"path": "backend", "file_count": 4}, "bad"]}) == [
        "- backend: 4 files"
    ]
    assert retrieval._snapshot_top_level({"top_level_directories": "bad"}) == []
    assert retrieval._snapshot_file_types({"file_type_counts": [{"extension": ".py", "count": 4}, "bad"]}) == [
        "- .py: 4 files"
    ]
    assert retrieval._snapshot_file_types({"file_type_counts": "bad"}) == []
    assert retrieval._snapshot_start_here(
        {
            "start_here_candidates": [
                {"path": "README.md", "reasons": ["project_overview", "docs"]},
                "bad",
                {"path": "backend/app/main.py", "reasons": "ignored"},
                {"reasons": ["bad"]},
            ]
        }
    ) == [
        "- README.md (project_overview, docs)",
        "- backend/app/main.py",
    ]
    assert retrieval._snapshot_start_here({"start_here_candidates": "bad"}) == []
    assert retrieval._snapshot_hotspots([{"path": "backend/app/main.py", "touch_count": 7, "last_touched": "today"}]) == [
        "- backend/app/main.py: 7 touches; last touched today"
    ]
    assert retrieval._snapshot_risk_matrix([{"path": "backend/app/main.py", "risk_level": "medium", "risk_score": 0.6}]) == [
        "- backend/app/main.py: risk=medium score=0.6"
    ]
    assert retrieval._snapshot_authorship(
        [
            {
                "path": "backend/app/main.py",
                "total_commits": 6,
                "primary_contributors": [{"name": "Alice"}, {"name": "Bob"}, "bad"],
            }
        ]
    ) == ["- backend/app/main.py: 6 commits; primary contributors: Alice, Bob"]
    assert retrieval._snapshot_top_contributors(
        [
            {"primary_contributors": "bad"},
            {
                "primary_contributors": [
                    {"name": "Alice", "commit_count": 3},
                    {"name": "Bob", "commit_count": "bad"},
                    "skip",
                ]
            }
        ]
    ) == [
        "- Alice: 3 commits across listed files",
        "- Bob: 0 commits across listed files",
    ]
    assert retrieval._snapshot_co_changes([{"file_a": "README.md", "file_b": "backend/app/main.py", "co_change_count": 2}]) == [
        "- README.md <-> backend/app/main.py: 2 co-changes"
    ]
    assert retrieval._snapshot_conventions(
        {
            "test_framework": {"name": "pytest", "config_path": "pytest.ini"},
            "test_dirs": ["tests"],
            "linters": [{"name": "ruff"}, {"name": "black"}, "bad"],
            "ci_pipelines": [{"platform": "github-actions"}, "bad"],
            "contribution_docs": ["CONTRIBUTING.md"],
            "package_manager": "pip",
        }
    ) == [
        "- Tests: pytest configured via pytest.ini",
        "- Test directories: tests",
        "- Linters/formatters: ruff, black",
        "- CI/CD: github-actions",
        "- Contribution docs: CONTRIBUTING.md",
        "- Package manager: pip",
    ]
    assert retrieval._snapshot_conventions({}) == []

    fallback_context = retrieval.retrieve_context(
        "https://github.com/example/project",
        onboarding_snapshot=models.OnboardingSnapshot(repo_slug="example__project"),
    )
    assert "Repository slug: example__project" in fallback_context
    assert "Total files discovered: 0" in fallback_context
    assert "- No top-level directory summary available" in fallback_context
    assert "- No strong conventions detected from provided files" in fallback_context
    assert "No selected file contents were provided." in fallback_context
