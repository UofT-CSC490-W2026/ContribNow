import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

from ..agent.loop import (
    build_agent_prompt,
    invoke_bedrock_agent,
    load_bedrock_agent_config,
)
from ..models import AskRequest, AskResponse
from .cloud import _api_url

router = APIRouter()


async def _save_message(repo_slug: str, role: str, message: str, access_key: str) -> None:
    """Fire-and-forget save of a single chat message to the hosted API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_api_url()}/chat-history/save",
                json={
                    "repo_slug": repo_slug,
                    "role": role,
                    "message": message,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                headers={"X-Access-Key": access_key},
            )
            print(f"[ask] chat-history/save role={role} status={resp.status_code}")
            if resp.status_code != 200:
                print(f"[ask] chat-history/save error: {resp.text}")
    except Exception as exc:
        print(f"[ask] chat-history/save failed for role={role}: {exc}")


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    try:
        prompt = build_agent_prompt(
            question=request.question,
            conversation_history="",
            repo_slug=request.repoSlug,
        )
        session_id = str(uuid.uuid4())
        answer = invoke_bedrock_agent(
            prompt=prompt,
            session_id=session_id,
            config=load_bedrock_agent_config(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Save both messages to cloud after a successful response
    await _save_message(request.repoSlug, "user", request.question, request.accessKey)
    await _save_message(request.repoSlug, "agent", answer, request.accessKey)

    return AskResponse(answer=answer, citations=[])
