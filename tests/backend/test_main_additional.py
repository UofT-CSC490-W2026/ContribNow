from __future__ import annotations

import asyncio

import numpy as np
import pytest


def test_lifespan_raises_when_pgvector_init_fails(load_backend_module) -> None:
    main = load_backend_module("app.main")
    calls: list[str] = []
    errors: list[str] = []

    main.init_db_onboarding_doc = lambda: calls.append("onboarding")
    main.init_db_chat_history = lambda: calls.append("chat")
    main.init_pgvectorstore = lambda: None
    main.logger.error = lambda message: errors.append(message)

    async def run_lifespan() -> None:
        async with main.lifespan(main.app):
            raise AssertionError("lifespan should not yield when pgvector initialization fails")

    with pytest.raises(RuntimeError, match="Failed to initialize PgVectorStore"):
        asyncio.run(run_lifespan())

    assert calls == ["onboarding", "chat"]
    assert errors == ["Failed to initialize PgVectorStore"]


def test_generate_onboarding_save_failures(load_backend_module) -> None:
    main = load_backend_module("app.main")
    models = load_backend_module("app.models")
    request = models.GenerateOnboardingRequest(
        repoUrl="https://github.com/example/project",
        repoSlug="example__project",
    )
    logged: list[str] = []
    deleted: list[str] = []

    main.verify_key = lambda access_key: True
    main.load_object_from_s3 = lambda object_key: None
    main.retrieve_context = lambda *args: "context"
    main.build_prompt = lambda user_prompt, context: "prompt"
    main.generate_document = lambda prompt, repo_url: "# Guide"
    main.logger.exception = lambda message: logged.append(message)

    main.save_object_to_s3 = lambda object_key, document: False
    with pytest.raises(main.HTTPException) as save_exc:
        main.generate_onboarding(request, x_access_key="alpha")
    assert save_exc.value.status_code == 500
    assert save_exc.value.detail == "Generation failed"
    assert "Failed to save onboarding document to S3" in logged[-1]

    main.save_object_to_s3 = lambda object_key, document: True
    main.save_onboarding_doc_repo = lambda access_key, repo_slug: False
    main.delete_object_from_s3 = lambda object_key: deleted.append(object_key) or True
    with pytest.raises(main.HTTPException) as metadata_exc:
        main.generate_onboarding(request, x_access_key="alpha")
    assert metadata_exc.value.status_code == 500
    assert metadata_exc.value.detail == "Generation failed"
    assert deleted == ["onboarding_docs/alpha/example__project.md"]
    assert "Failed to save onboarding document metadata to RDS" in logged[-1]


def test_store_vector_covers_auth_success_and_failure(load_backend_module) -> None:
    main = load_backend_module("app.main")
    models = load_backend_module("app.models")
    captured_records: list[object] = []
    errors: list[str] = []

    request = models.VectorRecordRequest(
        records=[
            models.VectorRecordAPI(
                vector=[1.0, 2.0, 3.0],
                repoSlug="example__project",
                headCommit="abc123",
                filePath="backend/app/main.py",
                startLine=10,
                endLine=20,
                dataId="chunk-1",
            )
        ]
    )

    main.verify_key = lambda access_key: False
    with pytest.raises(main.HTTPException) as auth_exc:
        main.store_vector(request, x_access_key="bad")
    assert auth_exc.value.status_code == 401

    class FakeStore:
        def upsert(self, records):
            captured_records.extend(records)
            return len(records)

    main.verify_key = lambda access_key: True
    main.pgvectorstore = FakeStore()
    assert main.store_vector(request, x_access_key="alpha") == {
        "message": "Successfully stored 1 vector records"
    }
    assert len(captured_records) == 1
    assert captured_records[0].repo_slug == "example__project"
    assert np.array_equal(captured_records[0].vector, np.array([1.0, 2.0, 3.0]))

    class FailingStore:
        def upsert(self, records):
            raise RuntimeError("boom")

    main.pgvectorstore = FailingStore()
    main.logger.error = lambda message: errors.append(message)
    with pytest.raises(main.HTTPException) as failure_exc:
        main.store_vector(request, x_access_key="alpha")
    assert failure_exc.value.status_code == 500
    assert failure_exc.value.detail == "Failed to store vector records"
    assert any("pgvectorstore.upsert error" in message for message in errors)


def test_query_vector_covers_auth_success_and_failure(load_backend_module) -> None:
    main = load_backend_module("app.main")
    models = load_backend_module("app.models")
    interfaces = load_backend_module("app.services.pgvector_interfaces")
    errors: list[str] = []

    request = models.VectorQueryRequest(
        query_vector=[0.1, 0.2, 0.3],
        k=2,
        repo_slug="example__project",
        head_commit="abc123",
        file_path="backend/app/main.py",
    )

    main.verify_key = lambda access_key: False
    with pytest.raises(main.HTTPException) as auth_exc:
        main.query_vector(request, x_access_key="bad")
    assert auth_exc.value.status_code == 401

    class FakeStore:
        def search(self, **kwargs):
            assert np.array_equal(kwargs["query_vector"], np.array([0.1, 0.2, 0.3]))
            assert kwargs["k"] == 2
            assert kwargs["repo_slug"] == "example__project"
            assert kwargs["head_commit"] == "abc123"
            assert kwargs["file_path"] == "backend/app/main.py"
            return [
                interfaces.SearchResult(
                    score=0.9,
                    repo_slug="example__project",
                    head_commit="abc123",
                    file_path="backend/app/main.py",
                    start_line=1,
                    end_line=10,
                    vector=np.array([1.0, 2.0, 3.0]),
                ),
                interfaces.SearchResult(
                    score=0.5,
                    repo_slug="example__project",
                    head_commit="abc123",
                    file_path="README.md",
                    start_line=1,
                    end_line=5,
                    vector=None,
                ),
            ]

    main.verify_key = lambda access_key: True
    main.pgvectorstore = FakeStore()
    response = main.query_vector(request, x_access_key="alpha")
    assert [result.file_path for result in response.results] == ["backend/app/main.py", "README.md"]
    assert response.results[0].vector == [1.0, 2.0, 3.0]
    assert response.results[1].vector is None

    class FailingStore:
        def search(self, **kwargs):
            raise RuntimeError("boom")

    main.pgvectorstore = FailingStore()
    main.logger.error = lambda message: errors.append(message)
    with pytest.raises(main.HTTPException) as failure_exc:
        main.query_vector(request, x_access_key="alpha")
    assert failure_exc.value.status_code == 500
    assert failure_exc.value.detail == "Failed to query vector records"
    assert any("pgvectorstore.search error" in message for message in errors)


def test_delete_vectors_by_repo_covers_auth_success_and_failure(load_backend_module) -> None:
    main = load_backend_module("app.main")
    errors: list[str] = []

    main.verify_key = lambda access_key: False
    with pytest.raises(main.HTTPException) as auth_exc:
        main.delete_vectors_by_repo("example__project", x_access_key="bad")
    assert auth_exc.value.status_code == 401

    class FakeStore:
        def delete_by_repo(self, repo_slug: str) -> int:
            assert repo_slug == "example__project"
            return 3

    main.verify_key = lambda access_key: True
    main.pgvectorstore = FakeStore()
    assert main.delete_vectors_by_repo("example__project", x_access_key="alpha") == {
        "message": "Deleted 3 vector records for repo 'example__project'"
    }

    class FailingStore:
        def delete_by_repo(self, repo_slug: str) -> int:
            raise RuntimeError("boom")

    main.pgvectorstore = FailingStore()
    main.logger.error = lambda message: errors.append(message)
    with pytest.raises(main.HTTPException) as failure_exc:
        main.delete_vectors_by_repo("example__project", x_access_key="alpha")
    assert failure_exc.value.status_code == 500
    assert failure_exc.value.detail == "Failed to delete vector records for repo example__project"
    assert any("pgvectorstore.delete_by_repo error" in message for message in errors)


def test_onboarding_doc_routes_cover_all_branches(load_backend_module) -> None:
    main = load_backend_module("app.main")
    models = load_backend_module("app.models")
    save_request = models.SaveOnboardingDocRequest(
        repo_slug="example__project",
        onboarding_doc="# Guide",
    )
    deleted_keys: list[str] = []

    main.verify_key = lambda access_key: False
    with pytest.raises(main.HTTPException) as save_auth_exc:
        main.save_onboarding_doc(save_request, x_access_key="bad")
    assert save_auth_exc.value.status_code == 401

    with pytest.raises(main.HTTPException) as load_auth_exc:
        main.load_onboarding_doc("example__project", x_access_key="bad")
    assert load_auth_exc.value.status_code == 401

    with pytest.raises(main.HTTPException) as load_all_auth_exc:
        main.load_all_onboarding_docs(x_access_key="bad")
    assert load_all_auth_exc.value.status_code == 401

    with pytest.raises(main.HTTPException) as delete_auth_exc:
        main.delete_onboarding_doc("example__project", x_access_key="bad")
    assert delete_auth_exc.value.status_code == 401

    main.verify_key = lambda access_key: True

    main.save_object_to_s3 = lambda object_key, obj: False
    with pytest.raises(main.HTTPException) as save_s3_exc:
        main.save_onboarding_doc(save_request, x_access_key="alpha")
    assert save_s3_exc.value.status_code == 500
    assert "Failed to save onboarding document to S3" in save_s3_exc.value.detail

    main.save_object_to_s3 = lambda object_key, obj: True
    main.save_onboarding_doc_repo = lambda access_key, repo_slug: False
    main.delete_object_from_s3 = lambda object_key: deleted_keys.append(object_key) or True
    with pytest.raises(main.HTTPException) as save_metadata_exc:
        main.save_onboarding_doc(save_request, x_access_key="alpha")
    assert save_metadata_exc.value.status_code == 500
    assert deleted_keys == ["onboarding_docs/alpha/example__project.md"]

    main.save_onboarding_doc_repo = lambda access_key, repo_slug: True
    assert main.save_onboarding_doc(save_request, x_access_key="alpha") == {
        "message": "Onboarding document saved successfully with object key: onboarding_docs/alpha/example__project.md"
    }

    main.load_object_from_s3 = lambda object_key: None
    with pytest.raises(main.HTTPException) as load_missing_exc:
        main.load_onboarding_doc("example__project", x_access_key="alpha")
    assert load_missing_exc.value.status_code == 404

    main.load_object_from_s3 = lambda object_key: "# Guide" if object_key.endswith("example__project.md") else None
    assert main.load_onboarding_doc("example__project", x_access_key="alpha") == {
        "onboarding_doc": "# Guide"
    }

    main.load_onboarding_doc_repos = lambda access_key: ["example__project", "missing"]
    assert main.load_all_onboarding_docs(x_access_key="alpha") == {
        "onboarding_docs": {"example__project": "# Guide"}
    }

    main.delete_onboarding_doc_repo = lambda access_key, repo_slug: -1
    with pytest.raises(main.HTTPException) as delete_rds_exc:
        main.delete_onboarding_doc("example__project", x_access_key="alpha")
    assert delete_rds_exc.value.status_code == 500

    main.delete_onboarding_doc_repo = lambda access_key, repo_slug: 0
    with pytest.raises(main.HTTPException) as delete_missing_exc:
        main.delete_onboarding_doc("example__project", x_access_key="alpha")
    assert delete_missing_exc.value.status_code == 404

    main.delete_onboarding_doc_repo = lambda access_key, repo_slug: 1
    main.delete_object_from_s3 = lambda object_key: False
    with pytest.raises(main.HTTPException) as delete_s3_exc:
        main.delete_onboarding_doc("example__project", x_access_key="alpha")
    assert delete_s3_exc.value.status_code == 500

    main.delete_object_from_s3 = lambda object_key: True
    assert main.delete_onboarding_doc("example__project", x_access_key="alpha") == {
        "message": "Onboarding document deleted successfully for repo 'example__project'"
    }


def test_chat_history_routes_cover_all_branches(load_backend_module) -> None:
    main = load_backend_module("app.main")
    models = load_backend_module("app.models")
    chat = models.ChatMessage(role="user", message="Hello")

    main.verify_key = lambda access_key: False
    with pytest.raises(main.HTTPException) as save_auth_exc:
        main.save_chat(chat, x_access_key="bad")
    assert save_auth_exc.value.status_code == 401

    with pytest.raises(main.HTTPException) as load_auth_exc:
        main.load_chat_history(x_access_key="bad")
    assert load_auth_exc.value.status_code == 401

    with pytest.raises(main.HTTPException) as delete_auth_exc:
        main.delete_chat_history(x_access_key="bad")
    assert delete_auth_exc.value.status_code == 401

    main.verify_key = lambda access_key: True
    main.save_chat_to_rds = lambda access_key, payload: False
    with pytest.raises(main.HTTPException) as save_fail_exc:
        main.save_chat(chat, x_access_key="alpha")
    assert save_fail_exc.value.status_code == 500

    main.save_chat_to_rds = lambda access_key, payload: True
    assert main.save_chat(chat, x_access_key="alpha") == {
        "message": "Chat history saved successfully"
    }

    main.load_chat_history_from_rds = lambda access_key: [{"role": "user", "message": "Hello", "created_at": "2026-03-30T12:00:00"}]
    assert main.load_chat_history(x_access_key="alpha") == {
        "history": [{"role": "user", "message": "Hello", "created_at": "2026-03-30T12:00:00"}]
    }

    main.delete_chat_history_from_rds = lambda access_key: -1
    with pytest.raises(main.HTTPException) as delete_fail_exc:
        main.delete_chat_history(x_access_key="alpha")
    assert delete_fail_exc.value.status_code == 500

    main.delete_chat_history_from_rds = lambda access_key: 0
    with pytest.raises(main.HTTPException) as delete_missing_exc:
        main.delete_chat_history(x_access_key="alpha")
    assert delete_missing_exc.value.status_code == 404

    main.delete_chat_history_from_rds = lambda access_key: 2
    assert main.delete_chat_history(x_access_key="alpha") == {
        "message": "Chat history deleted successfully, 2 records removed"
    }
