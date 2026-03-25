# Embedding Library

This package provides embedding primitives for the RAG indexing flow.
It is designed as a library (not a full pipeline stage by itself).

## Public API

Import from:

```python
from src.pipeline.embedding import (
    EmbeddingConfig,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingProvider,
    HuggingFaceEmbeddingProvider,
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
    RandomEmbeddingProvider,
    batch_requests,
)
```

## Core Types

### `EmbeddingConfig`

- `model`: model identifier (provider-specific)
- `batch_size`: max number of requests per batch
- `request_timeout_s`: request timeout in seconds
- `max_tokens`: optional per-input token cap
- `max_bytes`: optional per-input byte cap

### `EmbeddingRequest`

- `text`: text to embed
- `metadata`: metadata payload passed through to results

### `EmbeddingResult`

- `vectors`: list of embeddings (one per input)
- `metadata`: list of metadata entries aligned with `vectors`

### `EmbeddingProvider`

Interface for providers. Each provider implements:

- `name: str`
- `embed(requests: list[EmbeddingRequest], config: EmbeddingConfig) -> EmbeddingResult`

## Providers

### OpenAI

`OpenAIEmbeddingProvider` calls the OpenAI embeddings API using the official SDK.

Dependencies:

- `openai`
- `tiktoken` (used for token counting)

### Hugging Face (local, sentence-transformers)

`HuggingFaceEmbeddingProvider` runs local inference using `sentence-transformers`.

Dependencies:

- `sentence-transformers`

Example models:

- `BAAI/bge-code-v1`
- `microsoft/codebert-base`

### Local (stub)

`LocalEmbeddingProvider` returns deterministic fake vectors for testing.

### Random (if present)

`RandomEmbeddingProvider` is exported if available in the package.

## Batching + Preprocessing

Use `batch_requests(...)` to group inputs while enforcing size limits:

```python
from src.pipeline.embedding import EmbeddingConfig, EmbeddingRequest, batch_requests

def token_counter(text: str, model: str) -> int:
    return len(text.split())

config = EmbeddingConfig(model="BAAI/bge-code-v1", batch_size=16, max_tokens=8192)
requests = [EmbeddingRequest(text="def add(a, b): return a + b", metadata={})]

batches = batch_requests(
    requests,
    config,
    token_counter=token_counter,
    max_total_tokens=300_000,
)
```

## Example Usage

```python
from src.pipeline.embedding import (
    EmbeddingConfig,
    EmbeddingRequest,
    HuggingFaceEmbeddingProvider,
    batch_requests,
)

provider = HuggingFaceEmbeddingProvider()
config = EmbeddingConfig(model="BAAI/bge-code-v1", batch_size=8)
requests = [EmbeddingRequest(text="class Greeter: pass", metadata={"path": "app.py"})]

batches = batch_requests(requests, config)
results = [provider.embed(batch, config) for batch in batches]
```

## Notes

- Providers are leaf processors. They do not handle orchestration or vector store writes.
- OpenAI provider expects `OPENAI_API_KEY` to be set in the environment.
- Hugging Face provider will download models on first use.

## Tests

- `tests/test_embedding_batcher.py` validates batching behavior.
- `tests/test_huggingface_provider.py` downloads a model and runs only when `RUN_HF_TESTS=1`.
