from __future__ import annotations

from typing import TYPE_CHECKING

from src.pipeline.chunking.ts_base_strategy import (
    BaseTSChunkingStrategy,
    collect_nodes_by_type,
)

if TYPE_CHECKING:
    from tree_sitter import Node


class TSJSXChunkingStrategy(BaseTSChunkingStrategy):
    language_id = "jsx"
    strategy_id = "ts_jsx"
    grammar_module = "tree_sitter_javascript"

    def _collect_semantic_nodes(self, root: "Node") -> list["Node"]:
        return collect_nodes_by_type(
            root,
            {
                "function_declaration",
                "class_declaration",
                "method_definition",
            },
        )
