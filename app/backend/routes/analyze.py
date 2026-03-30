import uuid

from fastapi import APIRouter

from backend.models import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    # TODO: clone repo, run ETL pipeline, embed, index, generate onboarding doc
    run_id = str(uuid.uuid4())
    return AnalyzeResponse(
        success=True,
        runId=run_id,
        document="# Onboarding Guide\n\n> Stub response — pipeline not yet wired.\n",
        version=1,
    )
