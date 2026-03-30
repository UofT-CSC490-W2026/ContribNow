import json
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_ROOT = Path(os.getenv("CONTRIBNOW_DATA_ROOT", _REPO_ROOT / "data"))
_REGISTRY_PATH = _DATA_ROOT / "run_registry.json"
_RUN_REGISTRY: Dict[str, str] = {}


def _load_registry_from_disk() -> None:
    if not _REGISTRY_PATH.exists():
        return
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _RUN_REGISTRY.update({str(k): str(v) for k, v in data.items()})
    except Exception:
        _RUN_REGISTRY.clear()


def _save_registry_to_disk() -> None:
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(_RUN_REGISTRY, indent=2, sort_keys=True), encoding="utf-8")


def register_run_snapshot(run_id: str, snapshot_path: Path) -> None:
    _RUN_REGISTRY[run_id] = str(snapshot_path)
    _save_registry_to_disk()


def _resolve_snapshot_path_from_index(run_id: str) -> Path | None:
    output_root = _DATA_ROOT / f"output_{run_id}"
    index_path = output_root / "index.json"
    if not index_path.exists():
        return None
    try:
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    artifacts = index_data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return None

    artifact_path = artifacts[0].get("artifact_path") if isinstance(artifacts[0], dict) else None
    if not artifact_path:
        return None
    return output_root / artifact_path


def _resolve_snapshot_path(run_id: str) -> Path | None:
    if not _RUN_REGISTRY:
        _load_registry_from_disk()

    if run_id in _RUN_REGISTRY:
        candidate = Path(_RUN_REGISTRY[run_id])
        if candidate.exists():
            return candidate

    candidate = _resolve_snapshot_path_from_index(run_id)
    if candidate and candidate.exists():
        _RUN_REGISTRY[run_id] = str(candidate)
        _save_registry_to_disk()
        return candidate

    return None


def _load_snapshot(run_id: str) -> Dict[str, Any]:
    snapshot_path = _resolve_snapshot_path(run_id)
    if snapshot_path is None:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load snapshot: {exc}") from exc


def _require_key(snapshot: Dict[str, Any], key: str) -> Any:
    if key not in snapshot:
        raise HTTPException(status_code=500, detail=f"Snapshot missing key: {key}")
    return snapshot[key]


@router.get("/snapshot/{run_id}/hotspots")
async def get_hotspots(run_id: str) -> list:
    snapshot = _load_snapshot(run_id)
    return _require_key(snapshot, "hotspots")


@router.get("/snapshot/{run_id}/risk-levels")
async def get_risk_levels(run_id: str) -> list:
    snapshot = _load_snapshot(run_id)
    return _require_key(snapshot, "risk_matrix")


@router.get("/snapshot/{run_id}/conventions")
async def get_conventions(run_id: str) -> dict:
    snapshot = _load_snapshot(run_id)
    return _require_key(snapshot, "conventions")


@router.get("/snapshot/{run_id}/authorship")
async def get_authorship(run_id: str) -> list:
    snapshot = _load_snapshot(run_id)
    return _require_key(snapshot, "authorship_summary")


@router.get("/snapshot/{run_id}/co-changes")
async def get_co_changes(run_id: str) -> list:
    snapshot = _load_snapshot(run_id)
    return _require_key(snapshot, "co_change_pairs")


@router.get("/snapshot/{run_id}/dependencies")
async def get_dependencies(run_id: str) -> dict:
    snapshot = _load_snapshot(run_id)
    return _require_key(snapshot, "dependency_graph")
