import os

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _api_url() -> str:
    return os.environ.get("API_URL", "https://l6a25jv8zi.execute-api.ca-central-1.amazonaws.com")


class SaveChatMessageRequest(BaseModel):
    repo_slug: str
    role: str
    message: str
    created_at: str


@router.get("/onboarding-doc/load")
async def load_onboarding_doc(
    repo_slug: str | None = None,
    storage_key: str | None = None,
    storageKey: str | None = Query(None, alias="storageKey"),
    x_access_key: str = Header(..., alias="X-Access-Key"),
) -> dict:
    if not repo_slug and not storage_key and not storageKey:
        raise HTTPException(status_code=400, detail="Missing repo_slug or storageKey")

    params: dict[str, str] = {}
    if repo_slug:
        params["repo_slug"] = repo_slug
    storage_value = storageKey or storage_key
    if storage_value:
        # Forward both naming conventions; upstream should ignore unknown params.
        params["storageKey"] = storage_value
        params["storage_key"] = storage_value

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_api_url()}/onboarding-doc/load",
            params=params,
            headers={"X-Access-Key": x_access_key},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post("/chat-history/save")
async def save_chat_message(
    body: SaveChatMessageRequest, x_access_key: str = Header(..., alias="X-Access-Key")
) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_api_url()}/chat-history/save",
            json=body.model_dump(),
            headers={"X-Access-Key": x_access_key},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/chat-history/load")
async def load_chat_history(
    repo_slug: str, x_access_key: str = Header(..., alias="X-Access-Key")
) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_api_url()}/chat-history/load",
            params={"repo_slug": repo_slug},
            headers={"X-Access-Key": x_access_key},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
