from contextlib import asynccontextmanager
from typing import Any, cast
import traceback
import numpy as np

from fastapi import FastAPI, HTTPException, Header
from mangum import Mangum

from app.models import (
    GenerateOnboardingRequest,
    GenerateOnboardingResponse,
    CreateRdsTableRequest,
    SaveToRdsRequest,
    SaveToS3Request,
    VectorRecordRequest,
    VectorQueryRequest,
    SearchResultAPI,
    VectorQueryResponse,
    SaveOnboardingDocRequest,
    ChatMessage,
)
from app.constants import *
from app.services.pgvector_interfaces import VectorRecord, SearchResult
from app.services.auth import verify_key
from app.services.retrieval import retrieve_context
from app.services.prompt_builder import build_prompt
from app.services.llm import generate_document
from app.services.db_init import (
    init_db_onboarding_doc,
    init_db_chat_history,
    init_pgvectorstore,
)
from app.services.rds import (
    create_kv_table_in_rds,
    save_value_to_rds,
    load_value_from_rds,
    save_onboarding_doc_repo,
    load_onboarding_doc_repos,
    delete_onboarding_doc_repo,
    save_chat_to_rds,
    load_chat_history_from_rds,
    delete_chat_history_from_rds
)
from app.services.s3 import (
    save_object_to_s3,
    load_object_from_s3,
    delete_object_from_s3
)
from app.services.pgvector import PgVectorStore

from app.config import logger

pgvectorstore: PgVectorStore | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_onboarding_doc()
    init_db_chat_history()

    global pgvectorstore
    pgvectorstore = init_pgvectorstore()
    if pgvectorstore is None:
        logger.error("Failed to initialize PgVectorStore")
        raise RuntimeError("Failed to initialize PgVectorStore")
    
    try:
        yield
    finally:
        pass


app = FastAPI(lifespan=lifespan)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Backend is running"}


@app.post("/generate-onboarding", response_model=GenerateOnboardingResponse)
def generate_onboarding(
    request: GenerateOnboardingRequest,
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> GenerateOnboardingResponse:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")

    repo_url = str(request.repoUrl)
    repo_slug = request.repoSlug
    if not repo_slug:
        raise HTTPException(status_code=400, detail="repoSlug is required in the request body")
    object_key = f"{ONBOARDING_DOC_PATH}/{x_access_key}/{repo_slug}.md"

    if not request.forceRegenerate:
        try:
            cached_document = load_object_from_s3(object_key)
        except Exception as e:
            logger.exception(f"Error loading cached document: {repr(e)}")
            raise HTTPException(status_code=500, detail="Failed to load cached document")

        if cached_document is not None:
            return GenerateOnboardingResponse(
                success=True,
                document=cached_document,
                storageKey=object_key,
                fromCache=True,
            )

    try:
        context = retrieve_context(repo_url, request.repoSnapshot, request.onboardingSnapshot)
        prompt = build_prompt(request.userPrompt, context)
        document = generate_document(prompt, repo_url)
        if not save_object_to_s3(object_key, document):
            raise RuntimeError(f"Failed to save onboarding document to S3 for repo '{repo_slug}'")
        if not save_onboarding_doc_repo(x_access_key, repo_slug):
            delete_object_from_s3(object_key)
            raise RuntimeError(f"Failed to save onboarding document metadata to RDS for repo '{repo_slug}'")
    except Exception as e:
        logger.exception(f"Generation failed: {repr(e)}")
        raise HTTPException(status_code=500, detail="Generation failed")

    return GenerateOnboardingResponse(
        success=True,
        document=document,
        storageKey=object_key,
        fromCache=False,
    )


# @app.post("/rds/create-table")
# def create_rds_table(
#     request: CreateRdsTableRequest,
#     x_access_key: str = Header(..., alias="X-Access-Key"),
# ) -> dict[str, str]:
#     if not verify_key(x_access_key):
#         raise HTTPException(status_code=401, detail="Invalid access key")

#     create_kv_table_in_rds(
#         table_name=request.tableName,
#     )

#     return {"message": "RDS table created successfully"}


# @app.post("/rds/save")
# def save_to_rds(
#     request: SaveToRdsRequest,
#     x_access_key: str = Header(..., alias="X-Access-Key"),
# ) -> dict[str, str]:
#     if not verify_key(x_access_key):
#         raise HTTPException(status_code=401, detail="Invalid access key")

#     return save_value_to_rds(
#         table_name=request.tableName,
#         key=request.key,
#         value=request.value,
#     )


# @app.get("/rds/load")
# def load_from_rds(
#     tableName: str,
#     key: str,
#     x_access_key: str = Header(..., alias="X-Access-Key"),
# ) -> dict[str, Any]:
#     if not verify_key(x_access_key):
#         raise HTTPException(status_code=401, detail="Invalid access key")

#     return load_value_from_rds(
#         table_name=tableName,
#         key=key,
#     )


# @app.post("/s3/save")
# def save_to_s3(
#     request: SaveToS3Request,
#     x_access_key: str = Header(..., alias="X-Access-Key"),
# ) -> dict[str, str]:
#     if not verify_key(x_access_key):
#         raise HTTPException(status_code=401, detail="Invalid access key")

#     return save_object_to_s3(
#         object_key=request.objectKey,
#         obj=request.obj,
#     )


# @app.get("/s3/load")
# def load_from_s3(
#     objectKey: str,
#     x_access_key: str = Header(..., alias="X-Access-Key"),
# ) -> dict[str, str]:
#     if not verify_key(x_access_key):
#         raise HTTPException(status_code=401, detail="Invalid access key")

#     return load_object_from_s3(objectKey)


@app.post("/vector/store")
def store_vector(
    request: VectorRecordRequest,
    x_access_key: str = Header(..., alias="X-Access-Key"),
):
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    
    records = [
        VectorRecord(
            vector=np.array(r.vector, dtype=float),
            repo_slug=r.repoSlug,
            head_commit=r.headCommit,
            file_path=r.filePath,
            start_line=r.startLine,
            end_line=r.endLine,
            data_id=r.dataId,
        )
        for r in request.records
    ]
    try:
        assert pgvectorstore is not None, "PgVectorStore is not initialized"
        num_records: int = pgvectorstore.upsert(records)
    except Exception as e:
        logger.error(f"pgvectorstore.upsert error: {repr(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to store vector records")

    return {"message": f"Successfully stored {num_records} vector records"}


@app.post("/vector/query")
def query_vector(
    request: VectorQueryRequest,
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> VectorQueryResponse:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    
    try:
        assert pgvectorstore is not None, "PgVectorStore is not initialized"
        results = pgvectorstore.search(
            query_vector=np.array(request.query_vector, dtype=float),
            k=request.k,
            repo_slug=request.repo_slug,
            head_commit=request.head_commit,
            file_path=request.file_path,
        )
    except Exception as e:
        logger.error(f"pgvectorstore.search error: {repr(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to query vector records")

    results = [
        SearchResultAPI(
            score=r.score,
            repo_slug=r.repo_slug,
            head_commit=r.head_commit,
            file_path=r.file_path,
            start_line=r.start_line,
            end_line=r.end_line,
            vector=cast(
                list[float] | None,
                np.array(r.vector, dtype=float).tolist() if r.vector is not None else None,
            ),
        )
        for r in results
    ]
    return VectorQueryResponse(results=results)


@app.delete("/vector/delete-by-repo")
def delete_vectors_by_repo(
    repo_slug: str,
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict[str, str]:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    try:
        assert pgvectorstore is not None, "PgVectorStore is not initialized"
        deleted_count = pgvectorstore.delete_by_repo(repo_slug)
    except Exception as e:
        logger.error(f"pgvectorstore.delete_by_repo error: {repr(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to delete vector records for repo {repo_slug}")

    return {"message": f"Deleted {deleted_count} vector records for repo '{repo_slug}'"}


@app.post("/onboarding-doc/save")
def save_onboarding_doc(
    request: SaveOnboardingDocRequest,
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict[str, str]:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")

    accessKey = x_access_key
    object_key = f"{ONBOARDING_DOC_PATH}/{accessKey}/{request.repo_slug}.md"
    obj = request.onboarding_doc

    if not save_object_to_s3(object_key, obj):
        raise HTTPException(status_code=500, detail=f"Failed to save onboarding document to S3 for repo '{request.repo_slug}'")

    if not save_onboarding_doc_repo(accessKey, request.repo_slug):
        delete_object_from_s3(object_key)
        raise HTTPException(status_code=500, detail=f"Failed to save onboarding document metadata to RDS for repo '{request.repo_slug}'")

    return {"message": f"Onboarding document saved successfully with object key: {object_key}"}


@app.get("/onboarding-doc/load")
def load_onboarding_doc(
    repo_slug: str,
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict[str, str]:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    
    accessKey = x_access_key
    object_key = f"{ONBOARDING_DOC_PATH}/{accessKey}/{repo_slug}.md"
    obj = load_object_from_s3(object_key)

    if obj is None:
        raise HTTPException(status_code=404, detail=f"Onboarding document not found for repo '{repo_slug}'")

    return {"onboarding_doc": obj}


@app.get("/onboarding-doc/load-all")
def load_all_onboarding_docs(
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict[str, Any]:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    
    accessKey = x_access_key
    repo_slugs = load_onboarding_doc_repos(accessKey)

    onboarding_docs = {}
    for repo_slug in repo_slugs:
        object_key = f"{ONBOARDING_DOC_PATH}/{accessKey}/{repo_slug}.md"
        obj = load_object_from_s3(object_key)
        if obj is not None:
            onboarding_docs[repo_slug] = obj

    return {"onboarding_docs": onboarding_docs}


@app.delete("/onboarding-doc/delete")
def delete_onboarding_doc(
    repo_slug: str,
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict[str, str]:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    
    accessKey = x_access_key
    object_key = f"{ONBOARDING_DOC_PATH}/{accessKey}/{repo_slug}.md"
    deleted_cnt = delete_onboarding_doc_repo(accessKey, repo_slug)

    if deleted_cnt == -1:
        raise HTTPException(status_code=500, detail=f"Failed to delete onboarding document metadata from RDS for repo '{repo_slug}'")
    if deleted_cnt == 0:
        raise HTTPException(status_code=404, detail=f"No onboarding document metadata found to delete in RDS for repo '{repo_slug}'")

    if not delete_object_from_s3(object_key):
        raise HTTPException(status_code=500, detail=f"Failed to delete onboarding document from S3 for repo '{repo_slug}'")

    return {"message": f"Onboarding document deleted successfully for repo '{repo_slug}'"}


@app.post("/chat-history/save")
def save_chat(
    chat: ChatMessage,
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict[str, str]:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    
    accessKey = x_access_key
    if not save_chat_to_rds(accessKey, chat):
        raise HTTPException(status_code=500, detail="Failed to save chat history to RDS")
    
    return {"message": "Chat history saved successfully"}


@app.get("/chat-history/load")
def load_chat_history(
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict[str, Any]:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    
    accessKey = x_access_key
    result = load_chat_history_from_rds(accessKey)
    
    return {"history": result}


@app.delete("/chat-history/delete")
def delete_chat_history(
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict[str, str]:
    if not verify_key(x_access_key):
        raise HTTPException(status_code=401, detail="Invalid access key")
    
    accessKey = x_access_key
    deleted_cnt = delete_chat_history_from_rds(accessKey)

    if deleted_cnt == -1:
        raise HTTPException(status_code=500, detail="Failed to delete chat history from RDS")
    if deleted_cnt == 0:
        raise HTTPException(status_code=404, detail="No chat history found to delete")    
    
    return {"message": f"Chat history deleted successfully, {deleted_cnt} records removed"}


@app.get("/debug-db")
def debug_db() -> dict[str, str]:
    from app.services.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            result = cur.fetchone()
    assert result is not None
    return {"status": "ok", "result": str(result[0])}


handler = Mangum(app, lifespan="auto")
