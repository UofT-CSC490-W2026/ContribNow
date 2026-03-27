from contextlib import asynccontextmanager
import traceback

from fastapi import FastAPI, HTTPException
from mangum import Mangum

from app.models import GenerateOnboardingRequest, GenerateOnboardingResponse
from app.services.auth import verify_key
from app.services.retrieval import retrieve_context
from app.services.prompt_builder import build_prompt
from app.services.llm import generate_document
from app.services.storage import save_document, load_document
from app.services.cache import (
    get_cached_document,
    save_cached_document,
    get_repo_id,
    get_next_version,
)
from app.services.db_init import init_db


from app.config import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
) -> GenerateOnboardingResponse:
    if not verify_key(request.accessKey):
        raise HTTPException(status_code=401, detail="Invalid access key")

    repo_url = str(request.repoUrl)

    cached = get_cached_document(repo_url)
    if cached is not None and not request.forceRegenerate:
        try:
            cached_document = load_document(cached["storageKey"])
        except Exception as e:
            logger.exception(f"Error loading cached document: {repr(e)}")
            raise HTTPException(status_code=500, detail="Failed to load cached document")

        return GenerateOnboardingResponse(
            success=True,
            document=cached_document,
            storageKey=cached["storageKey"],
            fromCache=True,
            version=cached["version"],
        )

    try:
        context = retrieve_context(repo_url)
        prompt = build_prompt(request.userPrompt, context)
        document = generate_document(prompt, repo_url)

        repo_id = get_repo_id(repo_url)
        next_version = get_next_version(repo_url)

        storage_key = save_document(
            document=document,
            repo_id=repo_id,
            version=next_version,
        )

        record = save_cached_document(
            repo_url=repo_url,
            storage_key=storage_key,
            version=next_version,
        )
    except Exception as e:
        logger.exception(f"Generation failed: {repr(e)}")
        raise HTTPException(status_code=500, detail="Generation failed")

    return GenerateOnboardingResponse(
        success=True,
        document=document,
        storageKey=record["storageKey"],
        fromCache=False,
        version=record["version"],
    )


@app.get("/debug-db")
def debug_db() -> dict[str, str]:
    from app.services.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            result = cur.fetchone()
    assert result is not None
    return {"status": "ok", "result": str(result[0])}


handler = Mangum(app)