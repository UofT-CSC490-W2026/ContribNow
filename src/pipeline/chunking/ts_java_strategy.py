from __future__ import annotations

from typing import TYPE_CHECKING

from src.pipeline.chunking.ts_base_strategy import (
    BaseTSChunkingStrategy,
    collect_nodes_by_type,
)

if TYPE_CHECKING:
    from tree_sitter import Node


class TSJavaChunkingStrategy(BaseTSChunkingStrategy):
    language_id = "java"
    strategy_id = "ts_java"
    grammar_module = "tree_sitter_java"

    def _collect_semantic_nodes(self, root: "Node") -> list["Node"]:
        return collect_nodes_by_type(
            root,
            {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "method_declaration",
                "constructor_declaration",
            },
        )
