from __future__ import annotations

from pathlib import Path

from .shared import LocalTool, resolve_repo_path


def handler(params: dict[str, str], repo_roots: dict[str, Path]) -> str:
    target = resolve_repo_path(
        repo_roots=repo_roots,
        repo_slug=params["repoSlug"],
        path=params["path"],
    )
    if not target.exists():
        raise ValueError(f"Path does not exist: {params['path']}")
    if not target.is_file():
        raise ValueError(f"Path is not a file: {params['path']}")
    return target.read_text(encoding="utf-8", errors="replace")[:12000]


TOOL: LocalTool = {
    "definition": {
        "name": "readRepoFile",
        "description": "Read the contents of a text file from the repository.",
        "parameters": {
            "repoSlug": {
                "description": "Repository identifier for the local repository workspace.",
                "required": True,
                "type": "string",
            },
            "path": {
                "description": "File path inside the repository.",
                "required": True,
                "type": "string",
            },
        },
    },
    "handler": handler,
}
