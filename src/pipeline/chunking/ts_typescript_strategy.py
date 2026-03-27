from __future__ import annotations

from typing import TYPE_CHECKING

from src.pipeline.chunking.ts_base_strategy import (
    BaseTSChunkingStrategy,
    collect_nodes_by_type,
)

if TYPE_CHECKING:
    from tree_sitter import Node, Parser


class TSTypeScriptChunkingStrategy(BaseTSChunkingStrategy):
    language_id = "typescript"
    strategy_id = "ts_typescript"
    grammar_module = "tree_sitter_typescript"

    def _build_parser(self) -> "Parser":
        import tree_sitter_typescript as ts_lang
        from tree_sitter import Language, Parser

        # tree_sitter_typescript exposes language-specific constructors.
        language_factory = getattr(ts_lang, "language_typescript", None)
        if language_factory is None:
            language_factory = getattr(ts_lang, "language", None)
        if language_factory is None:
            raise RuntimeError(
                "tree_sitter_typescript does not expose language_typescript()"
            )
        return Parser(Language(language_factory()))

    def _collect_semantic_nodes(self, root: "Node") -> list["Node"]:
        return collect_nodes_by_type(
            root,
            {
                "function_declaration",
                "class_declaration",
                "interface_declaration",
                "type_alias_declaration",
                "enum_declaration",
                "method_definition",
            },
        )
