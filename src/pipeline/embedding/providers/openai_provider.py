# TODO: This provider is a WIP. We plan to mainly use open source embeddings for MVP first.
#       OpenAI text-embedding-3-large has excellent semantic understanding across NL and code.
#       In the future this could be used by instantiating
#       EmbeddingConfig(model="text-embedding-3-large", ...)

from __future__ import annotations

from typing import Any, Iterable

from src.pipeline.embedding.interfaces import (
    EmbeddingConfig,
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResult,
)

import tiktoken

class OpenAIEmbeddingProvider(EmbeddingProvider):
    @property
    def name(self) -> str:
        return "openai"

    def embed(
        self, requests: list[EmbeddingRequest], config: EmbeddingConfig
    ) -> EmbeddingResult:
        if not requests:
            return EmbeddingResult(vectors=[], metadata=[])

        self._validate_inputs(requests, config)

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK not installed. Add 'openai' to your dependencies."
            ) from exc

        client = OpenAI(timeout=config.request_timeout_s)
        response = client.embeddings.create(
            model=config.model,
            input=[request.text for request in requests],
            encoding_format="float",
        )

        vectors = self._extract_vectors(response.data)
        metadata = [request.metadata for request in requests]
        return EmbeddingResult(vectors=vectors, metadata=metadata)

    @staticmethod
    def _count_tokens(text: str, model: str) -> int:
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))

    def _validate_inputs(
        self, requests: list[EmbeddingRequest], config: EmbeddingConfig
    ) -> None:
        if config.max_tokens is not None:
            for req in requests:
                n = self._count_tokens(req.text, config.model)
                if n > config.max_tokens:
                    raise ValueError(
                        f"Embedding input exceeds max_tokens ({n} > {config.max_tokens})."
                    )

        if config.max_bytes is None:
            return

        for request in requests:
            size = len(request.text.encode("utf-8", errors="replace"))
            if size > config.max_bytes:
                raise ValueError(
                    f"Embedding input exceeds max_bytes ({size} > {config.max_bytes})."
                )

    def _extract_vectors(self, data: Iterable[Any]) -> list[list[float]]:
        items = list(data)
        if not items:
            return []

        vectors: list[list[float] | None] = [None] * len(items)
        for item in items:
            try:
                index = item.index
                embedding = item.embedding
            except AttributeError:
                index = item.get("index")
                embedding = item.get("embedding")
            if index is None:
                continue
            vectors[index] = list(embedding)

        if any(vector is None for vector in vectors):
            return [list(getattr(item, "embedding", item.get("embedding"))) for item in items]

        return [vector for vector in vectors if vector is not None]
