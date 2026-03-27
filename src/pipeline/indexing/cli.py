import argparse
from pathlib import Path

from src.pipeline.chunking import ChunkingConfig
from src.pipeline.embedding import (
    EmbeddingConfig,
    HuggingFaceEmbeddingProvider,
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from src.pipeline.indexing.indexer import index_repo_in_memory

_PROVIDERS = ("local", "huggingface", "openai")

def _build_provider(name: str):
    normalized = name.strip().lower()
    if normalized == "huggingface":
        return HuggingFaceEmbeddingProvider()
    if normalized == "openai":
        return OpenAIEmbeddingProvider()
    if normalized == "local":
        return LocalEmbeddingProvider()
    raise ValueError(f"Unknown provider: {name}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index a repo into an in-memory vector store.")
    parser.add_argument("--ingest-path", type=Path, required=True, help="Path to ingest.json.")
    parser.add_argument("--repo-root", type=Path, required=True, help="Path to the repo checkout.")
    parser.add_argument("--provider", default="local", choices=_PROVIDERS, help="Embedding provider: local|huggingface|openai.")
    parser.add_argument("--model", required=True, help="Embedding model id.")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size.")
    parser.add_argument("--request-timeout-s", type=float, default=30.0, help="Embedding request timeout.")
    parser.add_argument("--max-tokens", type=int, default=None, help="Optional per-input token cap.")
    parser.add_argument("--max-bytes", type=int, default=None, help="Optional per-input byte cap.")
    parser.add_argument("--chunk-max-bytes", type=int, default=1200, help="Chunk size in bytes.")
    parser.add_argument("--chunk-overlap-bytes", type=int, default=120, help="Overlap between chunks.")
    parser.add_argument("--chunk-min-split-bytes", type=int, default=300, help="Minimum bytes before newline split.")
    parser.add_argument("--file-limit", type=int, default=None, help="Optional limit on files processed.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    provider = _build_provider(args.provider)
    embedding_config = EmbeddingConfig(
        model=args.model,
        batch_size=args.batch_size,
        request_timeout_s=args.request_timeout_s,
        max_tokens=args.max_tokens,
        max_bytes=args.max_bytes,
    )
    chunking_config = ChunkingConfig(
        max_bytes=args.chunk_max_bytes,
        overlap_bytes=args.chunk_overlap_bytes,
        min_split_bytes=args.chunk_min_split_bytes,
    )
    _, stats = index_repo_in_memory(
        ingest_json_path=args.ingest_path,
        repo_root=args.repo_root,
        embedding_provider=provider,
        embedding_config=embedding_config,
        chunking_config=chunking_config,
        file_limit=args.file_limit,
    )
    print(
        "[indexing] files_seen="
        f"{stats.files_seen} files_indexed={stats.files_indexed} "
        f"chunks_indexed={stats.chunks_indexed} batches_sent={stats.batches_sent} "
        f"vectors_upserted={stats.vectors_upserted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
