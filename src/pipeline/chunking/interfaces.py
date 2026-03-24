from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int = 1200
    overlap_chars: int = 120
    min_split_chars: int = 300

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be > 0")
        if self.overlap_chars < 0:
            raise ValueError("overlap_chars must be >= 0")
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be < max_chars")
        if self.min_split_chars < 0:
            raise ValueError("min_split_chars must be >= 0")
        if self.min_split_chars > self.max_chars:
            raise ValueError("min_split_chars must be <= max_chars")


@dataclass(frozen=True)
class FileChunkRequest:
    repo_slug: str
    file_path: str
    # TODO(chunking-mem): prefer bytes + memoryview in orchestrator/strategies so
    # the same source buffer can be reused without copying.
    content: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    repo_slug: str
    file_path: str
    language: str | None
    strategy: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    # TODO(chunking-mem): store only source spans (start/end offsets) in chunk
    # records and materialize text lazily right before embedding/write.
    text: str


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
