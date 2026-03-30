from __future__ import annotations

import os
from pathlib import Path

from .tools import LOCAL_FUNCTIONS, load_repo_roots


def _load_repo_roots() -> dict[str, Path]:
    return load_repo_roots()


REPO_ROOTS = _load_repo_roots()


def run_local_tool(name: str, params: dict[str, str]) -> str:
    print(f"debug: using tool:\n{name}\n{params}\n")
    try:
        handler = LOCAL_FUNCTIONS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported tool: {name}") from exc
    return handler(params, REPO_ROOTS)
