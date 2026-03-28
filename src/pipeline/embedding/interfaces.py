from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


# Embedding Library Interface Classes:
# EmbeddingProvider, EmbeddingResult, EmbeddingRequest, EmbeddingConfig
# The top-level interface is EmbeddingProvider and embed(...),
# which takes in a batch of EmbeddingRequest + EmbeddingConfig and returns EmbeddingResult

@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    batch_size: int = 64
    request_timeout_s: float = 30.0
    max_tokens: int | None = None
    max_bytes: int | None = None

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise ValueError("model must be a non-empty string")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if self.request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be > 0")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("max_tokens must be > 0 when provided")
        if self.max_bytes is not None and self.max_bytes <= 0:
            raise ValueError("max_bytes must be > 0 when provided")


@dataclass(frozen=True)
class EmbeddingRequest:
    text: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if self.text is None:
            raise ValueError("text must not be None")
        if self.metadata is None:
            raise ValueError("metadata must not be None")


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    metadata: list[dict[str, Any]]

    def __post_init__(self) -> None:
        if len(self.vectors) != len(self.metadata):
            raise ValueError("vectors and metadata must be the same length")


class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str:
        """Human-readable provider identifier."""

    def embed(
        self, requests: list[EmbeddingRequest], config: EmbeddingConfig
    ) -> EmbeddingResult:
        """Embed a batch of requests and return vectors with metadata passthrough."""
