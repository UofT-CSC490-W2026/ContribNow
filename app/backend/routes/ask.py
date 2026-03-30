from fastapi import APIRouter

from backend.models import AskRequest, AskResponse

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    # TODO: route to local Codex agent
    return AskResponse(
        answer="Interactive Q&A not yet implemented.",
        citations=[],
    )
