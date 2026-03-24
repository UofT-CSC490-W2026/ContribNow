# Chunking Library

This package provides chunking primitives for RAG indexing.  
It is designed as a library (not an ETL stage by itself).

## Public API

Import from:

```python
from src.pipeline.chunking import (
    ChunkingConfig,
    FileChunkRequest,
    Chunk,
    ChunkingStrategy,
    DefaultLanguageRegistry,
    get_language_registry,
    reset_language_registry,
    NaiveChunkingStrategy,
    TSJavaChunkingStrategy,
    TSJavaScriptChunkingStrategy,
    TSJSXChunkingStrategy,
    TSPyChunkingStrategy,
)
```

## Core Types

### `ChunkingConfig`

- `max_bytes`: maximum bytes per chunk window.
- `overlap_bytes`: bytes repeated between adjacent chunks.
- `min_split_bytes`: minimum span before newline split is attempted.

### `FileChunkRequest`

- `repo_slug`: stable repository identifier used in chunk metadata/IDs.
- `file_path`: source-relative path for the file being chunked.
- `content`: full file bytes to split.

### `Chunk`

- `chunk_id`: deterministic ID for this chunk.
- `repo_slug`: source repo slug copied from request.
- `file_path`: source file path copied from request.
- `language`: detected language (or `None` if unknown).
- `strategy`: strategy name that produced the chunk (`naive`, `ts_py`, etc.).
- `start_byte`: inclusive byte offset into original file bytes.
- `end_byte`: exclusive byte offset into original file bytes.
- `start_line`: 1-based start line for this span.
- `end_line`: 1-based end line for this span.
- `content`: materialized chunk bytes.

### `ChunkingResult`

- `language`: resolved language for the chunking operation.
- `strategy`: selected strategy name.
- `chunks`: list of produced `Chunk` objects.
- `fallback_reason`: optional reason when caller-level fallback occurred.

## Strategy Contract

A strategy must implement:

- `name: str`
- `supports_language(language: str | None) -> bool`
- `chunk(request, language, config) -> list[Chunk]`

Important:

- Strategies are leaf processors.
- They should not do routing/fallback orchestration.
- The caller (usually indexing code) decides fallback behavior.

## Included Strategies

- `NaiveChunkingStrategy`
  - line-aware fixed-window chunking
  - overlap support
- `TSPyChunkingStrategy`
  - Python-only Tree-sitter chunking
  - semantic boundaries from Python AST node types
- `TSJavaScriptChunkingStrategy`
  - JavaScript Tree-sitter chunking
  - semantic boundaries from JS definition node types
- `TSJSXChunkingStrategy`
  - JSX Tree-sitter chunking (JS grammar)
  - semantic boundaries from JS definition node types
- `TSJavaChunkingStrategy`
  - Java Tree-sitter chunking
  - semantic boundaries from Java declaration node types

## Language Registry

`DefaultLanguageRegistry` provides:

- language detection (`detect`) from extension/filename/shebang
- strategy registration per language (`register_strategy`)
- strategy lookup (`get_strategy`)

Use singleton helpers:

- `get_language_registry()` for shared process-level registry
- `reset_language_registry()` for tests

## Example Usage

```python
from src.pipeline.chunking import (
    ChunkingConfig,
    FileChunkRequest,
    NaiveChunkingStrategy,
    TSJavaChunkingStrategy,
    TSJavaScriptChunkingStrategy,
    TSJSXChunkingStrategy,
    TSPyChunkingStrategy,
    get_language_registry,
)

registry = get_language_registry()
registry.register_strategy("python", TSPyChunkingStrategy())
registry.register_strategy("javascript", TSJavaScriptChunkingStrategy())
registry.register_strategy("jsx", TSJSXChunkingStrategy())
registry.register_strategy("java", TSJavaChunkingStrategy())
default_strategy = NaiveChunkingStrategy()
config = ChunkingConfig()

def chunk_one(repo_slug: str, file_path: str, content: bytes):
    # Detect using a small decoded head for shebang support.
    language = registry.detect(file_path, content[:1024].decode("utf-8", errors="replace"))
    strategy = registry.get_strategy(language or "") or default_strategy
    request = FileChunkRequest(repo_slug=repo_slug, file_path=file_path, content=content)
    return strategy.chunk(request, language, config)
```

This keeps chunking + embedding + vector upsert in one indexing flow.

## Dependencies

For Python Tree-sitter strategy:

- `tree-sitter`
- `tree-sitter-python`
- `tree-sitter-javascript`
- `tree-sitter-java`

If these are unavailable, `TSPyChunkingStrategy` initialization will fail.  
Use `NaiveChunkingStrategy` as the default fallback in your index orchestration.
