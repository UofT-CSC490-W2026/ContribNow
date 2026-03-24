from __future__ import annotations

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

        source_bytes = request.content
        total_bytes = len(source_bytes)
        if total_bytes == 0:
            return []

        tree: Tree = self._parser.parse(source_bytes)
        root: Node = tree.root_node
        semantic_nodes = _collect_python_semantic_nodes(root)
        semantic_spans = _semantic_spans_with_gaps(semantic_nodes, total_bytes)
        if not semantic_spans:
            semantic_spans = [(0, total_bytes)]

        newline_offsets = [
            idx for idx, byte in enumerate(source_bytes) if byte == b"\n"[0]
        ]
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
                chunk_id = _build_chunk_id(
                    request.repo_slug,
                    request.file_path,
                    chunk_start_byte,
                    chunk_end_byte,
                    chunk_content,
                )
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
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


def _build_ts_py_parser() -> "Parser":
    """Build a Python Tree-sitter parser configured with the python grammar."""
    import tree_sitter_python
    from tree_sitter import Language, Parser

    language_obj = Language(tree_sitter_python.language())
    return Parser(language_obj)


def _collect_python_semantic_nodes(root: "Node") -> list["Node"]:
    """Collect top-level semantic Python definition nodes in source order."""
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
    """Return byte spans for semantic nodes plus inter-node gaps."""
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
    """Split one byte span into overlap-aware chunk windows."""
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
