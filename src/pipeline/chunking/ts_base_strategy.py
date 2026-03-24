from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from src.pipeline.chunking.interfaces import Chunk, ChunkingConfig, FileChunkRequest
from src.pipeline.chunking.strategies import _build_chunk_id, _offset_to_line

if TYPE_CHECKING:
    from tree_sitter import Node, Parser, Tree


class BaseTSChunkingStrategy:
    """
    Shared Tree-sitter chunking flow.

    Subclasses specialize semantic-node collection for one language.
    """

    language_id: str = ""
    strategy_id: str = ""
    grammar_module: str = ""

    def __init__(self) -> None:
        self._parser: Parser = self._build_parser()

    @property
    def name(self) -> str:
        return self.strategy_id

    def supports_language(self, language: str | None) -> bool:
        return language == self.language_id

    def chunk(
        self, request: FileChunkRequest, language: str | None, config: ChunkingConfig
    ) -> list[Chunk]:
        if language != self.language_id:
            raise ValueError(
                f"{self.__class__.__name__} only supports language='{self.language_id}'"
            )

        source_bytes = request.content
        total_bytes = len(source_bytes)
        if total_bytes == 0:
            return []

        tree: Tree = self._parser.parse(source_bytes)
        root: Node = tree.root_node
        semantic_nodes = self._collect_semantic_nodes(root)
        semantic_spans = _semantic_spans_with_gaps(semantic_nodes, total_bytes)
        if not semantic_spans:
            semantic_spans = [(0, total_bytes)]

        newline_offsets = [idx for idx, byte in enumerate(source_bytes) if byte == 10]
        chunks: list[Chunk] = []

        for start_byte, end_byte in semantic_spans:
            if end_byte <= start_byte:
                continue
            if not source_bytes[start_byte:end_byte].strip():
                continue

            for chunk_start_byte, chunk_end_byte in _split_byte_span(
                source_bytes,
                start=start_byte,
                end=end_byte,
                config=config,
            ):
                chunk_content = source_bytes[chunk_start_byte:chunk_end_byte]
                if not chunk_content:
                    continue
                chunks.append(
                    Chunk(
                        chunk_id=_build_chunk_id(
                            request.repo_slug,
                            request.file_path,
                            chunk_start_byte,
                            chunk_end_byte,
                            chunk_content,
                        ),
                        repo_slug=request.repo_slug,
                        file_path=request.file_path,
                        language=language,
                        strategy=self.name,
                        start_byte=chunk_start_byte,
                        end_byte=chunk_end_byte,
                        start_line=_offset_to_line(newline_offsets, chunk_start_byte),
                        end_line=_offset_to_line(
                            newline_offsets, max(chunk_start_byte, chunk_end_byte - 1)
                        ),
                        content=chunk_content,
                    )
                )

        return chunks

    def _build_parser(self) -> "Parser":
        from tree_sitter import Language, Parser

        ts_lang = importlib.import_module(self.grammar_module)
        language_obj = Language(ts_lang.language())
        return Parser(language_obj)

    def _collect_semantic_nodes(self, root: "Node") -> list["Node"]:
        raise NotImplementedError


def collect_nodes_by_type(root: "Node", wanted_types: set[str]) -> list["Node"]:
    # Keep stable ordering so chunk boundaries are deterministic.
    nodes = [node for node in root.children if node.type in wanted_types]
    nodes.sort(key=lambda node: (node.start_byte, node.end_byte))
    return nodes


def _semantic_spans_with_gaps(
    nodes: list["Node"], total_bytes: int
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0

    for node in nodes:
        start_byte = max(0, node.start_byte)
        end_byte = min(total_bytes, node.end_byte)
        if end_byte <= start_byte:
            continue
        if start_byte > cursor:
            spans.append((cursor, start_byte))
        spans.append((start_byte, end_byte))
        cursor = max(cursor, end_byte)

    if cursor < total_bytes:
        spans.append((cursor, total_bytes))
    return spans


def _split_byte_span(
    source: bytes,
    start: int,
    end: int,
    config: ChunkingConfig,
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    current = start

    while current < end:
        limit = min(current + config.max_bytes, end)
        split = limit

        if limit < end:
            floor = min(current + config.min_split_bytes, limit)
            split_at = source.rfind(b"\n", floor, limit)
            if split_at != -1 and split_at + 1 > current:
                split = split_at + 1

        if split <= current:
            split = limit
            if split <= current:
                break

        spans.append((current, split))
        if split >= end:
            break

        current = max(split - config.overlap_bytes, current + 1)

    return spans
