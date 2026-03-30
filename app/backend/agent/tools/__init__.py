from __future__ import annotations

from .list_repo_files import TOOL as LIST_REPO_FILES_TOOL
from .read_repo_file import TOOL as READ_REPO_FILE_TOOL
from .search_repo_text import TOOL as SEARCH_REPO_TEXT_TOOL
from .shared import load_repo_roots

TOOLS = [
    LIST_REPO_FILES_TOOL,
    READ_REPO_FILE_TOOL,
    SEARCH_REPO_TEXT_TOOL,
]

LOCAL_FUNCTIONS = {tool["definition"]["name"]: tool["handler"] for tool in TOOLS}


def build_tool_definitions() -> list[dict[str, object]]:
    return [tool["definition"] for tool in TOOLS]


__all__ = [
    "LOCAL_FUNCTIONS",
    "TOOLS",
    "build_tool_definitions",
    "load_repo_roots",
]
