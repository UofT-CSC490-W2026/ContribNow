from __future__ import annotations

from pathlib import Path
from typing import Callable, TypedDict


class ToolParameter(TypedDict):
    description: str
    required: bool
    type: str


class ToolDefinition(TypedDict):
    name: str
    description: str
    parameters: dict[str, ToolParameter]


ToolHandler = Callable[[dict[str, str], dict[str, Path]], str]


class LocalTool(TypedDict):
    definition: ToolDefinition
    handler: ToolHandler


IGNORED_DIR_NAMES: set[str] = {
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
}


BINARY_EXTENSIONS: set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".svg",
    ".tiff",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".mp3",
    ".wav",
    ".flac",
    ".ogg",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".class",
    ".o",
    ".a",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".bin",
    ".dat",
    ".db",
    ".sqlite",
    ".wasm",
}

DEFAULT_REPO_ROOT = Path("/home/louis/programming/ContribNow")


def load_repo_roots() -> dict[str, Path]:
    return {"default": DEFAULT_REPO_ROOT.resolve()}


def resolve_repo_path(repo_roots: dict[str, Path], repo_slug: str, path: str) -> Path:
    if repo_slug not in repo_roots:
        raise ValueError(f"Unsupported repo slug: {repo_slug}")
    root = repo_roots[repo_slug].resolve()
    target = (root / path).resolve()
    target.relative_to(root)
    return target
