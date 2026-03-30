from fastapi import APIRouter, HTTPException

from ..agent.loop import (
    build_agent_prompt,
    invoke_bedrock_agent,
    load_bedrock_agent_config,
)
from ..models import AskRequest, AskResponse

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    try:
        prompt = build_agent_prompt(
            question=request.question,
            conversation_history=request.conversationHistory,
            # repo_slug=request.repoSlug,
        )
        answer = invoke_bedrock_agent(
            prompt=prompt,
            session_id=request.runId,
            config=load_bedrock_agent_config(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise exc
        # raise HTTPException(status_code=500, detail="Failed to query agent") from exc

    return AskResponse(answer=answer, citations=[])
