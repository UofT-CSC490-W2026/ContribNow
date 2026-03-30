from fastapi import APIRouter

router = APIRouter()


@router.get("/snapshot/{run_id}/hotspots")
async def get_hotspots(run_id: str) -> list:
    # TODO: read from pipeline run JSON
    return []


@router.get("/snapshot/{run_id}/risk-levels")
async def get_risk_levels(run_id: str) -> list:
    return []


@router.get("/snapshot/{run_id}/conventions")
async def get_conventions(run_id: str) -> dict:
    return {"testing": [], "ci": [], "linters": [], "contribution_docs": []}


@router.get("/snapshot/{run_id}/authorship")
async def get_authorship(run_id: str) -> list:
    return []


@router.get("/snapshot/{run_id}/co-changes")
async def get_co_changes(run_id: str) -> list:
    return []


@router.get("/snapshot/{run_id}/dependencies")
async def get_dependencies(run_id: str) -> dict:
    return {"nodes": [], "edges": []}
