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
    if not target.is_dir():
        raise ValueError(f"Path is not a directory: {params['path']}")
    entries = sorted(item.name for item in target.iterdir())
    return "\n".join(entries[:200])


TOOL: LocalTool = {
    "definition": {
        "name": "listRepoFiles",
        "description": "List files and subdirectories inside a repository directory.",
        "parameters": {
            "repoSlug": {
                "description": "Repository identifier for the local repository workspace.",
                "required": True,
                "type": "string",
            },
            "path": {
                "description": "Directory path inside the repository.",
                "required": True,
                "type": "string",
            },
        },
    },
    "handler": handler,
}
