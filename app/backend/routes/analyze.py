import json
import os
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from backend.models import AnalyzeRequest, AnalyzeResponse
from src.pipeline.ingest import ingest_repos
from src.pipeline.transform import transform_repo
from src.pipeline.load import load_artifact

router = APIRouter()

DATA_DIR = Path("data")


def _get_config():
    return {
        "api_url": os.environ.get("API_URL", "https://l6a25jv8zi.execute-api.ca-central-1.amazonaws.com"),
        "max_file_size": int(os.environ.get("MAX_FILE_SIZE", "100000")),
        "api_timeout": float(os.environ.get("API_TIMEOUT", "120")),
    }


def _repo_slug(url: str) -> str:
    """Derive a filesystem-safe slug from a repo URL."""
    trimmed = re.sub(r"\.git$", "", url.strip().rstrip("/"))
    tail = trimmed.split("://", 1)[-1] if "://" in trimmed else trimmed
    tail = tail.split("/", 1)[1] if "/" in tail else tail
    return re.sub(r"[^a-zA-Z0-9._-]", "_", tail.replace("/", "__")) or "repo"


def _read_selected_files(
    repo_checkout: Path, candidates: list[dict], max_file_size: int,
) -> list[dict]:
    """Read file contents for start_here_candidates from the cloned repo."""
    selected = []
    for candidate in candidates:
        file_path = repo_checkout / candidate["path"]
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        truncated = len(content) > max_file_size
        if truncated:
            content = content[:max_file_size]
        selected.append({
            "path": candidate["path"],
            "content": content,
            "truncated": truncated,
        })
    return selected


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    slug = _repo_slug(request.repoUrl)
    raw_root = DATA_DIR / "raw"
    transform_root = DATA_DIR / "transform"
    output_root = DATA_DIR / "output"

    # 1. Ingest — clone repo and generate manifest
    completed = ingest_repos(repo_urls=[request.repoUrl], raw_root=raw_root)
    if not completed:
        raise HTTPException(status_code=400, detail="Failed to ingest repository")

    # 2. Transform — structure summary, hotspots, risk levels, etc.
    raw_repo_dir = completed[0]
    transform_path = transform_repo(raw_repo_dir, transform_root, top_n_hotspots=20)

    # 3. Load — produce final onboarding snapshot
    snapshot_path = load_artifact(transform_path, output_root)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    # 4. Build repo snapshot (file list + selected file contents)
    config = _get_config()
    ingest_data = json.loads((raw_repo_dir / "ingest.json").read_text(encoding="utf-8"))
    repo_checkout = raw_repo_dir / "repo"
    start_here = snapshot.get("structure_summary", {}).get("start_here_candidates", [])
    selected_files = _read_selected_files(repo_checkout, start_here, config["max_file_size"])

    repo_snapshot = {
        "repo_slug": slug,
        "files": ingest_data.get("files", []),
        "selected_file_contents": selected_files,
    }

    # 5. Call generate-onboarding API
    api_body = {
        "repoUrl": request.repoUrl,
        "repoSlug": slug,
        "userPrompt": request.taskType or "understand",
        "forceRegenerate": False,
        "repoSnapshot": repo_snapshot,
        "onboardingSnapshot": snapshot,
    }

    headers = {"X-Access-Key": request.accessKey}
    async with httpx.AsyncClient(timeout=config["api_timeout"]) as client:
        resp = await client.post(f"{config['api_url']}/generate-onboarding", json=api_body, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Generate API returned {resp.status_code}: {resp.text}",
        )

    api_result = resp.json()

    return AnalyzeResponse(
        success=api_result.get("success", True),
        runId=slug,
        document=api_result.get("document", ""),
        storageKey=api_result.get("storageKey"),
        fromCache=api_result.get("fromCache", False),
        version=api_result.get("version"),
    )
