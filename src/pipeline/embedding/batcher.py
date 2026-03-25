from __future__ import annotations

from typing import Callable, Iterable

from src.pipeline.embedding.interfaces import EmbeddingConfig, EmbeddingRequest

TokenCounter = Callable[[str, str], int]


def batch_requests(
    requests: Iterable[EmbeddingRequest],
    config: EmbeddingConfig,
    token_counter: TokenCounter | None = None,
    max_total_tokens: int | None = None,
    max_total_bytes: int | None = None,
) -> list[list[EmbeddingRequest]]:
    """
    Group embedding requests into batches while enforcing size limits.

    - Enforces per-item limits using config.max_tokens / config.max_bytes.
    - Enforces per-batch limits using max_total_tokens / max_total_bytes.
    - Preserves input order to keep metadata aligned downstream.
    """

    request_list = list(requests)
    if not request_list:
        return []

    if (config.max_tokens is not None or max_total_tokens is not None) and token_counter is None:  
        raise ValueError("token_counter is required when any token-based limit is set")  

    sizes = []
    for req in request_list:
        token_count = None
        if config.max_tokens is not None or max_total_tokens is not None:
            token_count = token_counter(req.text, config.model)
            if config.max_tokens is not None and token_count > config.max_tokens:
                raise ValueError(
                    f"Embedding input exceeds max_tokens ({token_count} > {config.max_tokens})."
                )

        byte_count = len(req.text.encode("utf-8", errors="replace"))
        if config.max_bytes is not None and byte_count > config.max_bytes:
            raise ValueError(
                f"Embedding input exceeds max_bytes ({byte_count} > {config.max_bytes})."
            )

        sizes.append((token_count, byte_count))

    batches: list[list[EmbeddingRequest]] = []
    current: list[EmbeddingRequest] = []
    current_tokens = 0
    current_bytes = 0

    for req, (token_count, byte_count) in zip(request_list, sizes, strict=True):
        next_tokens = current_tokens + (token_count or 0)
        next_bytes = current_bytes + byte_count
        would_exceed_count = len(current) >= config.batch_size
        would_exceed_tokens = (
            max_total_tokens is not None and token_count is not None and next_tokens > max_total_tokens
        )
        would_exceed_bytes = (
            max_total_bytes is not None and next_bytes > max_total_bytes
        )

        if current and (would_exceed_count or would_exceed_tokens or would_exceed_bytes):
            batches.append(current)
            current = []
            current_tokens = 0
            current_bytes = 0

        if max_total_tokens is not None and token_count is not None and token_count > max_total_tokens:
            raise ValueError(
                f"Embedding input exceeds max_total_tokens ({token_count} > {max_total_tokens})."
            )
        if max_total_bytes is not None and byte_count > max_total_bytes:
            raise ValueError(
                f"Embedding input exceeds max_total_bytes ({byte_count} > {max_total_bytes})."
            )

        current.append(req)
        current_tokens += token_count or 0
        current_bytes += byte_count

    if current:
        batches.append(current)

    return batches
