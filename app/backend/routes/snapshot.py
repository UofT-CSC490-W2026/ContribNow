import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

DATA_DIR = Path("data")


def _load_snapshot(run_id: str) -> dict:
    """Find and load the onboarding snapshot for a given run ID (repo slug)."""
    snapshot_path = DATA_DIR / "output" / run_id / "onboarding_snapshot.json"
    if not snapshot_path.exists():
        raise HTTPException(status_code=404, detail=f"No snapshot found for run {run_id}")

    return json.loads(snapshot_path.read_text(encoding="utf-8"))


@router.get("/snapshot/{run_id}/hotspots")
async def get_hotspots(run_id: str) -> list:
    snapshot = _load_snapshot(run_id)
    return snapshot.get("hotspots", [])


@router.get("/snapshot/{run_id}/risk-levels")
async def get_risk_levels(run_id: str) -> list:
    snapshot = _load_snapshot(run_id)
    return snapshot.get("risk_matrix", [])


@router.get("/snapshot/{run_id}/conventions")
async def get_conventions(run_id: str) -> dict:
    snapshot = _load_snapshot(run_id)
    return snapshot.get("conventions", {})


@router.get("/snapshot/{run_id}/authorship")
async def get_authorship(run_id: str) -> list:
    snapshot = _load_snapshot(run_id)
    return snapshot.get("authorship_summary", [])


@router.get("/snapshot/{run_id}/co-changes")
async def get_co_changes(run_id: str) -> list:
    snapshot = _load_snapshot(run_id)
    return snapshot.get("co_change_pairs", [])


@router.get("/snapshot/{run_id}/dependencies")
async def get_dependencies(run_id: str) -> dict:
    snapshot = _load_snapshot(run_id)
    return snapshot.get("dependency_graph", {})
