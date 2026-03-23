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
