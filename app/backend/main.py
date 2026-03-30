"""
Local FastAPI server for the ContribNow desktop app.

In development: `uvicorn backend.main:app --reload` from the app/ directory.
In production:  launched by launcher.py (PyInstaller bundle).

Static files (frontend/dist) are served from FRONTEND_DIST, which resolves to:
  - <app>/frontend_dist/   when running from source
  - <_MEIPASS>/frontend_dist/  when running as a PyInstaller exe
"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routes import analyze, ask, snapshot

# ── Path resolution ────────────────────────────────────────────────────────────

if getattr(sys, "frozen", False):
    # PyInstaller bundle: files are extracted to a temp dir at runtime
    _BASE = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    # Running from source: app/ is the working directory
    _BASE = Path(__file__).parent.parent

FRONTEND_DIST = _BASE / "frontend_dist"

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="ContribNow", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes first so they take priority over the catch-all SPA route
app.include_router(analyze.router)
app.include_router(snapshot.router)
app.include_router(ask.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ── Frontend static files ──────────────────────────────────────────────────────

if FRONTEND_DIST.exists():
    # Serve hashed asset files (JS/CSS bundles)
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        """Catch-all: return index.html so React Router handles client-side nav."""
        return FileResponse(str(FRONTEND_DIST / "index.html"))
