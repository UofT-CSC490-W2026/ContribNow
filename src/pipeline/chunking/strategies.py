from __future__ import annotations

import bisect
import hashlib

from src.pipeline.chunking.interfaces import Chunk, ChunkingConfig, FileChunkRequest


class NaiveChunkingStrategy:
    @property
    def name(self) -> str:
        return "naive"

    def supports_language(self, language: str | None) -> bool:
        return True

    def chunk(
        self, request: FileChunkRequest, language: str | None, config: ChunkingConfig
    ) -> list[Chunk]:
        text = request.content
        if not text:
            return []

        newline_offsets = [idx for idx, char in enumerate(text) if char == "\n"]
        chunks: list[Chunk] = []
        start = 0
        text_len = len(text)

        while start < text_len:
            limit = min(start + config.max_chars, text_len)
            end = limit

            if limit < text_len:
                floor = min(start + config.min_split_chars, limit)
                split_at = text.rfind("\n", floor, limit)
                if split_at != -1 and split_at + 1 > start:
                    end = split_at + 1

            if end <= start:
                end = min(start + config.max_chars, text_len)
                if end <= start:
                    break

            chunk_text = text[start:end]
            if not chunk_text:
                break

            start_line = _offset_to_line(newline_offsets, start)
            end_line = _offset_to_line(newline_offsets, max(start, end - 1))
            chunks.append(
                Chunk(
                    chunk_id=_build_chunk_id(
                        request.repo_slug,
                        request.file_path,
                        start,
                        end,
                        chunk_text,
                    ),
                    repo_slug=request.repo_slug,
                    file_path=request.file_path,
                    language=language,
                    strategy=self.name,
                    start_offset=start,
                    end_offset=end,
                    start_line=start_line,
                    end_line=end_line,
                    text=chunk_text,
                )
            )

            if end >= text_len:
                break

            start = max(end - config.overlap_chars, start + 1)

        return chunks


class TSPyChunkingStrategy:
    """
    Python Tree-sitter chunking strategy.

    Strategy is leaf-level processing logic; it does not perform fallback routing.
    """

    def __init__(self) -> None:
        self._parser = _build_ts_py_parser()

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

        tree = self._parser.parse(source_bytes)
        root = getattr(tree, "root_node", None)
        if root is None:
            raise RuntimeError("Tree-sitter parser returned no root_node")

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


def _build_ts_py_parser() -> object:
    import tree_sitter
    import tree_sitter_python

    language_obj = tree_sitter.Language(tree_sitter_python.language())
    try:
        parser = tree_sitter.Parser()
    except TypeError:
        # Some versions require language in constructor.
        parser = tree_sitter.Parser(language_obj)
        return parser

    if hasattr(parser, "set_language"):
        parser.set_language(language_obj)
    elif hasattr(parser, "language"):
        parser.language = language_obj
    else:
        raise RuntimeError("Unsupported tree_sitter.Parser API")

    return parser


def _offset_to_line(newline_offsets: list[int], offset: int) -> int:
    if offset <= 0:
        return 1
    return bisect.bisect_right(newline_offsets, offset - 1) + 1


def _build_chunk_id(
    repo_slug: str, file_path: str, start: int, end: int, text: str
) -> str:
    payload = (
        f"{repo_slug}:{file_path}:{start}:{end}:"
        f"{hashlib.sha256(text.encode('utf-8', errors='replace')).hexdigest()}"
    )
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def _collect_python_semantic_nodes(root: object) -> list[object]:
    wanted_types = {
        "function_definition",
        "class_definition",
        "decorated_definition",
        "async_function_definition",
    }
    children = list(getattr(root, "children", []))
    nodes = [node for node in children if getattr(node, "type", None) in wanted_types]
    nodes.sort(
        key=lambda node: (
            int(getattr(node, "start_byte", 0)),
            int(getattr(node, "end_byte", 0)),
        )
    )
    return nodes


def _semantic_spans_with_gaps(
    nodes: list[object], total_bytes: int
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0

    for node in nodes:
        start_byte = max(0, int(getattr(node, "start_byte", 0)))
        end_byte = min(total_bytes, int(getattr(node, "end_byte", 0)))
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
