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
        source = request.content
        if not source:
            return []

        newline_offsets = [idx for idx, byte in enumerate(source) if byte == b"\n"[0]]
        chunks: list[Chunk] = []
        start = 0
        source_len = len(source)

        while start < source_len:
            limit = min(start + config.max_bytes, source_len)
            end = limit

            if limit < source_len:
                floor = min(start + config.min_split_bytes, limit)
                split_at = source.rfind(b"\n", floor, limit)
                if split_at != -1 and split_at + 1 > start:
                    end = split_at + 1

            if end <= start:
                end = min(start + config.max_bytes, source_len)
                if end <= start:
                    break

            chunk_content = source[start:end]
            if not chunk_content:
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
                        chunk_content,
                    ),
                    repo_slug=request.repo_slug,
                    file_path=request.file_path,
                    language=language,
                    strategy=self.name,
                    start_byte=start,
                    end_byte=end,
                    start_line=start_line,
                    end_line=end_line,
                    content=chunk_content,
                )
            )

            if end >= source_len:
                break

            start = max(end - config.overlap_bytes, start + 1)

        return chunks


def _offset_to_line(newline_offsets: list[int], offset: int) -> int:
    if offset <= 0:
        return 1
    return bisect.bisect_right(newline_offsets, offset - 1) + 1


def _build_chunk_id(
    repo_slug: str, file_path: str, start: int, end: int, content: bytes
) -> str:
    payload = (
        f"{repo_slug}:{file_path}:{start}:{end}:{hashlib.sha256(content).hexdigest()}"
    )
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
