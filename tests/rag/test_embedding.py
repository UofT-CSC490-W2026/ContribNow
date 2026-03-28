from __future__ import annotations

from types import ModuleType, SimpleNamespace
import builtins
import sys

import pytest

from src.pipeline.embedding import (
    EmbeddingConfig,
    EmbeddingRequest,
    EmbeddingResult,
    batch_requests,
)
from src.pipeline.embedding.providers.huggingface_provider import (
    HuggingFaceEmbeddingProvider,
)
from src.pipeline.embedding.providers.local_provider import LocalEmbeddingProvider
from src.pipeline.embedding.providers.openai_provider import OpenAIEmbeddingProvider


def _token_counter(text: str, model: str) -> int:
    return len(text.split())


class _DummyEncoding:
    def __init__(self, tokens: int) -> None:
        self._tokens = tokens

    def encode(self, text: str) -> list[int]:
        return [0] * self._tokens


class _DummyVectorArray:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


class _DummyHFModel:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows
        self.tokenizer = _DummyEncoding(tokens=2)

    def encode(self, texts: list[str], **_: object) -> _DummyVectorArray:
        return _DummyVectorArray(self._rows[: len(texts)])

# Embedding Library Classes Tests

def test_embedding_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        EmbeddingConfig(model="")
    with pytest.raises(ValueError):
        EmbeddingConfig(model="   ")
    with pytest.raises(ValueError):
        EmbeddingConfig(model="m", batch_size=0)
    with pytest.raises(ValueError):
        EmbeddingConfig(model="m", request_timeout_s=0)
    with pytest.raises(ValueError):
        EmbeddingConfig(model="m", max_tokens=0)
    with pytest.raises(ValueError):
        EmbeddingConfig(model="m", max_bytes=0)


def test_embedding_request_rejects_none_fields() -> None:
    with pytest.raises(ValueError):
        EmbeddingRequest(text=None, metadata={})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        EmbeddingRequest(text="ok", metadata=None)  # type: ignore[arg-type]


def test_embedding_result_requires_matching_lengths() -> None:
    with pytest.raises(ValueError):
        EmbeddingResult(vectors=[[0.1]], metadata=[])

# Embedding Batcher

def test_batch_requests_empty_input_returns_empty() -> None:
    config = EmbeddingConfig(model="test")
    assert batch_requests([], config) == []


def test_batches_by_batch_size() -> None:
    config = EmbeddingConfig(model="test", batch_size=2)
    requests = [
        EmbeddingRequest(text="a", metadata={"i": 0}),
        EmbeddingRequest(text="b", metadata={"i": 1}),
        EmbeddingRequest(text="c", metadata={"i": 2}),
    ]

    batches = batch_requests(requests, config)

    assert [len(batch) for batch in batches] == [2, 1]
    assert batches[0][0].metadata["i"] == 0
    assert batches[1][0].metadata["i"] == 2


def test_enforces_max_bytes() -> None:
    config = EmbeddingConfig(model="test", max_bytes=3)
    requests = [EmbeddingRequest(text="abcd", metadata={})]

    with pytest.raises(ValueError):
        batch_requests(requests, config)


def test_enforces_max_tokens() -> None:
    config = EmbeddingConfig(model="test", max_tokens=2)
    requests = [EmbeddingRequest(text="one two three", metadata={})]

    with pytest.raises(ValueError):
        batch_requests(requests, config, token_counter=_token_counter)


def test_total_token_limit_splits_batches() -> None:
    config = EmbeddingConfig(model="test", batch_size=10, max_tokens=5)
    requests = [
        EmbeddingRequest(text="one two", metadata={"i": 0}),
        EmbeddingRequest(text="three four", metadata={"i": 1}),
        EmbeddingRequest(text="five six", metadata={"i": 2}),
    ]

    batches = batch_requests(
        requests,
        config,
        token_counter=_token_counter,
        max_total_tokens=4,
    )

    assert [len(batch) for batch in batches] == [2, 1]


def test_total_token_limit_applies_without_per_item_max() -> None:
    config = EmbeddingConfig(model="test", batch_size=10, max_tokens=None)
    requests = [
        EmbeddingRequest(text="one two", metadata={"i": 0}),
        EmbeddingRequest(text="three four", metadata={"i": 1}),
        EmbeddingRequest(text="five six", metadata={"i": 2}),
    ]

    batches = batch_requests(
        requests,
        config,
        token_counter=_token_counter,
        max_total_tokens=4,
    )

    assert [len(batch) for batch in batches] == [2, 1]


def test_requires_token_counter_when_max_tokens_set() -> None:
    config = EmbeddingConfig(model="test", max_tokens=2)
    requests = [EmbeddingRequest(text="a b", metadata={})]

    with pytest.raises(ValueError):
        batch_requests(requests, config)


def test_batch_requests_rejects_item_over_total_token_limit() -> None:
    config = EmbeddingConfig(model="test")
    requests = [EmbeddingRequest(text="one two three", metadata={})]

    with pytest.raises(ValueError):
        batch_requests(
            requests,
            config,
            token_counter=_token_counter,
            max_total_tokens=2,
        )


def test_batch_requests_rejects_item_over_total_byte_limit() -> None:
    config = EmbeddingConfig(model="test")
    requests = [EmbeddingRequest(text="abcd", metadata={})]

    with pytest.raises(ValueError):
        batch_requests(requests, config, max_total_bytes=3)

# Local provider

def test_local_provider_returns_deterministic_vectors() -> None:
    provider = LocalEmbeddingProvider()
    config = EmbeddingConfig(model="local")
    requests = [
        EmbeddingRequest(text="alpha", metadata={"i": 0}),
        EmbeddingRequest(text="alpha", metadata={"i": 1}),
    ]

    result = provider.embed(requests, config)

    assert result.vectors[0] == result.vectors[1]
    assert result.metadata == [{"i": 0}, {"i": 1}]
    assert len(result.vectors[0]) == 8
    assert all(0.0 <= value <= 1.0 for value in result.vectors[0])
    assert provider.name == "local"

# OpenAI provider

def test_openai_provider_embed_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyOpenAI:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout
            self.embeddings = self

        def create(self, model: str, input: list[str], encoding_format: str) -> SimpleNamespace:
            data = [
                SimpleNamespace(index=i, embedding=[float(i), float(i + 1)])
                for i, _ in enumerate(input)
            ]
            return SimpleNamespace(data=data)

    openai_module = ModuleType("openai")
    openai_module.OpenAI = _DummyOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    provider = OpenAIEmbeddingProvider()
    config = EmbeddingConfig(model="test", request_timeout_s=5)
    requests = [
        EmbeddingRequest(text="hello", metadata={"i": 0}),
        EmbeddingRequest(text="world", metadata={"i": 1}),
    ]

    result = provider.embed(requests, config)

    assert result.vectors == [[0.0, 1.0], [1.0, 2.0]]
    assert result.metadata == [{"i": 0}, {"i": 1}]


def test_openai_provider_embed_without_requests() -> None:
    provider = OpenAIEmbeddingProvider()
    config = EmbeddingConfig(model="test")

    result = provider.embed([], config)

    assert result.vectors == []
    assert result.metadata == []


def test_openai_provider_missing_sdk_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def _blocked_import(name: str, globals_: object, locals_: object, fromlist: object, level: int) -> object:
        if name == "openai":
            raise ImportError("blocked")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    provider = OpenAIEmbeddingProvider()
    config = EmbeddingConfig(model="test")
    requests = [EmbeddingRequest(text="hello", metadata={})]

    with pytest.raises(RuntimeError):
        provider.embed(requests, config)


def test_openai_provider_count_tokens_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyTikEncoding:
        def encode(self, text: str) -> list[int]:
            return [0, 1, 2]

    class _DummyTiktoken:
        @staticmethod
        def encoding_for_model(model: str) -> _DummyTikEncoding:
            raise Exception("no model")

        @staticmethod
        def get_encoding(name: str) -> _DummyTikEncoding:
            return _DummyTikEncoding()

    monkeypatch.setitem(sys.modules, "tiktoken", _DummyTiktoken())

    assert OpenAIEmbeddingProvider._count_tokens("hi", "model") == 3


def test_openai_provider_validate_inputs_errors() -> None:
    provider = OpenAIEmbeddingProvider()
    requests = [EmbeddingRequest(text="hello", metadata={})]

    provider._count_tokens = lambda text, model: 5  # type: ignore[assignment]
    with pytest.raises(ValueError):
        provider._validate_inputs(requests, EmbeddingConfig(model="test", max_tokens=3))

    with pytest.raises(ValueError):
        provider._validate_inputs(requests, EmbeddingConfig(model="test", max_bytes=2))


def test_openai_provider_extract_vectors_fallback() -> None:
    provider = OpenAIEmbeddingProvider()
    data = [
        {"index": None, "embedding": [1.0, 2.0]},
        {"index": None, "embedding": [3.0, 4.0]},
    ]

    vectors = provider._extract_vectors(data)

    assert vectors == [[1.0, 2.0], [3.0, 4.0]]


def test_openai_provider_extract_vectors_ordering() -> None:
    provider = OpenAIEmbeddingProvider()
    data = [
        SimpleNamespace(index=1, embedding=[2.0]),
        SimpleNamespace(index=0, embedding=[1.0]),
    ]

    vectors = provider._extract_vectors(data)

    assert vectors == [[1.0], [2.0]]
    assert provider.name == "openai"


def test_openai_provider_extract_vectors_empty_returns_empty() -> None:
    provider = OpenAIEmbeddingProvider()
    assert provider._extract_vectors([]) == []


# HuggingFace provider

def test_huggingface_provider_embed_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def _sentence_transformer(model_id: str) -> _DummyHFModel:
        calls["count"] += 1
        return _DummyHFModel([[0.1, 0.2], [0.3, 0.4]])

    st_module = ModuleType("sentence_transformers")
    st_module.SentenceTransformer = _sentence_transformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", st_module)

    provider = HuggingFaceEmbeddingProvider()
    config = EmbeddingConfig(model="hf-model", batch_size=2)
    requests = [
        EmbeddingRequest(text="a", metadata={"i": 0}),
        EmbeddingRequest(text="b", metadata={"i": 1}),
    ]

    result = provider.embed(requests, config)

    assert result.vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert result.metadata == [{"i": 0}, {"i": 1}]
    assert provider._get_model("hf-model") is provider._get_model("hf-model")
    assert calls["count"] == 1
    assert provider.name == "huggingface"


def test_huggingface_provider_empty_requests_returns_empty() -> None:
    provider = HuggingFaceEmbeddingProvider()
    config = EmbeddingConfig(model="hf-model")

    result = provider.embed([], config)

    assert result.vectors == []
    assert result.metadata == []


def test_huggingface_provider_missing_tokenizer_raises() -> None:
    provider = HuggingFaceEmbeddingProvider()
    config = EmbeddingConfig(model="hf", max_tokens=1)
    requests = [EmbeddingRequest(text="hello", metadata={})]

    model = SimpleNamespace(tokenizer=None)
    with pytest.raises(RuntimeError):
        provider._validate_inputs(requests, config, model)


def test_huggingface_provider_max_tokens_raises() -> None:
    provider = HuggingFaceEmbeddingProvider()
    config = EmbeddingConfig(model="hf", max_tokens=1)
    requests = [EmbeddingRequest(text="hello", metadata={})]

    model = _DummyHFModel([[0.1, 0.2]])
    with pytest.raises(ValueError):
        provider._validate_inputs(requests, config, model)


def test_huggingface_provider_max_bytes_raises() -> None:
    provider = HuggingFaceEmbeddingProvider()
    config = EmbeddingConfig(model="hf", max_bytes=2)
    requests = [EmbeddingRequest(text="hello", metadata={})]

    model = _DummyHFModel([[0.1, 0.2]])
    with pytest.raises(ValueError):
        provider._validate_inputs(requests, config, model)


def test_huggingface_provider_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    empty_module = ModuleType("sentence_transformers")
    monkeypatch.setitem(sys.modules, "sentence_transformers", empty_module)

    provider = HuggingFaceEmbeddingProvider()
    with pytest.raises(RuntimeError):
        provider._get_model("hf-model")
