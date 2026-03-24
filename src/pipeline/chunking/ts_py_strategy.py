from __future__ import annotations

from typing import TYPE_CHECKING

from src.pipeline.chunking.ts_base_strategy import (
    BaseTSChunkingStrategy,
    collect_nodes_by_type,
)

if TYPE_CHECKING:
    from tree_sitter import Node


class TSPyChunkingStrategy(BaseTSChunkingStrategy):
    """
    Python Tree-sitter chunking strategy.
    """

    language_id = "python"
    strategy_id = "ts_py"
    grammar_module = "tree_sitter_python"

    def _collect_semantic_nodes(self, root: "Node") -> list["Node"]:
        # Prefer top-level definition-like nodes for retrieval boundaries.
        return collect_nodes_by_type(
            root,
            {
                "function_definition",
                "class_definition",
                "decorated_definition",
                "async_function_definition",
            },
        )
