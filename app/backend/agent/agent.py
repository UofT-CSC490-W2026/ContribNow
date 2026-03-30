from __future__ import annotations

from pathlib import Path

from .tools import LOCAL_FUNCTIONS, load_repo_roots


def run_local_tool(name: str, params: dict[str, str]) -> str:
    print(f"debug: using tool:\n{name}\n{params}\n")
    repo_roots = load_repo_roots()
    try:
        handler = LOCAL_FUNCTIONS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported tool: {name}") from exc
    return handler(params, repo_roots)
