from __future__ import annotations

import hashlib

from src.pipeline.embedding.interfaces import (
    EmbeddingConfig,
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResult,
)

# This is a stub provider meant for use in tests or offline dev
# Returns fake vectors
class LocalEmbeddingProvider(EmbeddingProvider):
    @property
    def name(self) -> str:
        return "random"

    def embed(
        self, requests: list[EmbeddingRequest], config: EmbeddingConfig
    ) -> EmbeddingResult:
        vectors = [self._random_vector(request.text) for request in requests]
        metadata = [request.metadata for request in requests]
        return EmbeddingResult(vectors=vectors, metadata=metadata)

    def _random_vector(self, text: str, dim: int = 8) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
        return [byte / 255.0 for byte in digest[:dim]]
