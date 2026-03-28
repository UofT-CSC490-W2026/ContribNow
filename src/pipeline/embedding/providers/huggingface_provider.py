from __future__ import annotations

from typing import Any

from src.pipeline.embedding.interfaces import (
    EmbeddingConfig,
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResult,
)


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider backed by sentence-transformers.

    Expects EmbeddingConfig.model to be a Hugging Face model id
    (e.g., "BAAI/bge-code-v1" or "microsoft/codebert-base").
    """

    def __init__(self) -> None:
        self._model_cache: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "huggingface"

    def embed(
        self, requests: list[EmbeddingRequest], config: EmbeddingConfig
    ) -> EmbeddingResult:
        if not requests:
            return EmbeddingResult(vectors=[], metadata=[])

        model = self._get_model(config.model)
        self._validate_inputs(requests, config, model)

        texts = [request.text for request in requests]
        vectors = model.encode(
            texts,
            batch_size=config.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        metadata = [request.metadata for request in requests]
        return EmbeddingResult(vectors=vectors.tolist(), metadata=metadata)

    def _get_model(self, model_id: str) -> Any:
        if model_id in self._model_cache:
            return self._model_cache[model_id]

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers not installed. Add it to dependencies."
            ) from exc

        model = SentenceTransformer(model_id)
        self._model_cache[model_id] = model
        return model

    def _validate_inputs(
        self, requests: list[EmbeddingRequest], config: EmbeddingConfig, model: Any
    ) -> None:
        if config.max_tokens is not None:
            tokenizer = getattr(model, "tokenizer", None)
            if tokenizer is None:
                raise RuntimeError("Tokenizer unavailable to enforce max_tokens.")
            for req in requests:
                token_count = len(tokenizer.encode(req.text))
                if token_count > config.max_tokens:
                    raise ValueError(
                        f"Embedding input exceeds max_tokens ({token_count} > {config.max_tokens})."
                    )

        if config.max_bytes is None:
            return

        for request in requests:
            size = len(request.text.encode("utf-8", errors="replace"))
            if size > config.max_bytes:
                raise ValueError(
                    f"Embedding input exceeds max_bytes ({size} > {config.max_bytes})."
                )
