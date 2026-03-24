from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChunkingConfig:
    max_bytes: int = 1200
    overlap_bytes: int = 120
    min_split_bytes: int = 300

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be > 0")
        if self.overlap_bytes < 0:
            raise ValueError("overlap_bytes must be >= 0")
        if self.overlap_bytes >= self.max_bytes:
            raise ValueError("overlap_bytes must be < max_bytes")
        if self.min_split_bytes < 0:
            raise ValueError("min_split_bytes must be >= 0")
        if self.min_split_bytes > self.max_bytes:
            raise ValueError("min_split_bytes must be <= max_bytes")


@dataclass(frozen=True)
class FileChunkRequest:
    repo_slug: str
    file_path: str
    # TODO(chunking-mem): switch to memoryview-backed buffers to avoid copies.
    content: bytes


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    repo_slug: str
    file_path: str
    language: str | None
    strategy: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    # TODO(chunking-mem): store only source spans and materialize bytes lazily.
    content: bytes


# TODO(chunking-mem): add a memory regression benchmark test that tracks peak RSS
# while chunking large repositories and gates increases.


@dataclass(frozen=True)
class ChunkingResult:
    language: str | None
    strategy: str
    chunks: list[Chunk]
    fallback_reason: str | None = None


class LanguageRegistry(Protocol):
    def detect(self, file_path: str, content_head: str | None = None) -> str | None:
        """Return a canonical language id for a file, or None if unknown."""

    def register_strategy(self, language: str, strategy: "ChunkingStrategy") -> None:
        """Register a language-specific chunking strategy."""

    def get_strategy(self, language: str) -> "ChunkingStrategy | None":
        """Return the language-specific chunking strategy, if any."""


class ChunkingStrategy(Protocol):
    @property
    def name(self) -> str:
        """Human-readable strategy identifier."""

    def supports_language(self, language: str | None) -> bool:
        """Return True if this strategy can chunk this language."""

    def chunk(
        self, request: FileChunkRequest, language: str | None, config: ChunkingConfig
    ) -> list[Chunk]:
        """Split one source file into retrieval chunks."""
