from __future__ import annotations

import bisect
from typing import TYPE_CHECKING

from src.pipeline.chunking.interfaces import Chunk, ChunkingConfig, FileChunkRequest
from src.pipeline.chunking.strategies import _build_chunk_id, _offset_to_line

if TYPE_CHECKING:
    from tree_sitter import Node, Parser, Tree


class TSPyChunkingStrategy:
    """
    Python Tree-sitter chunking strategy with typed syntax-node boundaries.
    """

    def __init__(self) -> None:
        self._parser: Parser = _build_ts_py_parser()

    @property
    def name(self) -> str:
        return "ts_py"

    def supports_language(self, language: str | None) -> bool:
        return language == "python"

    def chunk(
        self, request: FileChunkRequest, language: str | None, config: ChunkingConfig
    ) -> list[Chunk]:
        if language != "python":
            raise ValueError("TSPyChunkingStrategy only supports language='python'")

        source_text = request.content
        source_bytes = source_text.encode("utf-8", errors="replace")
        total_bytes = len(source_bytes)
        if total_bytes == 0:
            return []

        tree: Tree = self._parser.parse(source_bytes)
        root: Node = tree.root_node
        semantic_nodes = _collect_python_semantic_nodes(root)
        semantic_spans = _semantic_spans_with_gaps(semantic_nodes, total_bytes)
        if not semantic_spans:
            semantic_spans = [(0, total_bytes)]

        char_to_byte = _build_char_to_byte_offsets(source_text)
        newline_offsets = [idx for idx, char in enumerate(source_text) if char == "\n"]
        chunks: list[Chunk] = []

        for start_byte, end_byte in semantic_spans:
            span_start_char = _byte_to_char_offset(char_to_byte, start_byte)
            span_end_char = _byte_to_char_offset(char_to_byte, end_byte)
            if span_end_char <= span_start_char:
                continue
            if not source_text[span_start_char:span_end_char].strip():
                continue

            for start_char, end_char in _split_char_span(
                source_text,
                start=span_start_char,
                end=span_end_char,
                config=config,
            ):
                chunk_text = source_text[start_char:end_char]
                if not chunk_text:
                    continue
                chunks.append(
                    Chunk(
                        chunk_id=_build_chunk_id(
                            request.repo_slug,
                            request.file_path,
                            start_char,
                            end_char,
                            chunk_text,
                        ),
                        repo_slug=request.repo_slug,
                        file_path=request.file_path,
                        language=language,
                        strategy=self.name,
                        start_offset=start_char,
                        end_offset=end_char,
                        start_line=_offset_to_line(newline_offsets, start_char),
                        end_line=_offset_to_line(
                            newline_offsets, max(start_char, end_char - 1)
                        ),
                        text=chunk_text,
                    )
                )

        return chunks


def _build_ts_py_parser() -> "Parser":
    import tree_sitter_python
    from tree_sitter import Language, Parser

    language_obj = Language(tree_sitter_python.language())
    return Parser(language_obj)


def _collect_python_semantic_nodes(root: "Node") -> list["Node"]:
    wanted_types = {
        "function_definition",
        "class_definition",
        "decorated_definition",
        "async_function_definition",
    }
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


def _build_char_to_byte_offsets(text: str) -> list[int]:
    offsets = [0]
    total = 0
    for char in text:
        total += len(char.encode("utf-8", errors="replace"))
        offsets.append(total)
    return offsets


def _byte_to_char_offset(char_to_byte: list[int], byte_offset: int) -> int:
    if byte_offset <= 0:
        return 0
    last = char_to_byte[-1]
    if byte_offset >= last:
        return len(char_to_byte) - 1
    return bisect.bisect_left(char_to_byte, byte_offset)


def _split_char_span(
    text: str,
    start: int,
    end: int,
    config: ChunkingConfig,
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    current = start

    while current < end:
        limit = min(current + config.max_chars, end)
        split = limit

        if limit < end:
            floor = min(current + config.min_split_chars, limit)
            split_at = text.rfind("\n", floor, limit)
            if split_at != -1 and split_at + 1 > current:
                split = split_at + 1

        if split <= current:
            split = limit
            if split <= current:
                break

        spans.append((current, split))
        if split >= end:
            break

        current = max(split - config.overlap_chars, current + 1)

    return spans
