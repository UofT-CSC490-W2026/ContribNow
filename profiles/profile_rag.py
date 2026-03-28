#!/usr/bin/env python3
import argparse
import cProfile
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import pstats

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.chunking import ChunkingConfig, FileChunkRequest, NaiveChunkingStrategy
from src.pipeline.embedding import EmbeddingConfig, LocalEmbeddingProvider
from src.pipeline.indexing.indexer import build_language_registry, index_repo
from src.pipeline.vector_store import InMemoryVectorStore


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile RAG indexing (chunking + embedding + vector upsert) in-process."
    )
    parser.add_argument(
        "--run-id",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Run id for output folders (default: timestamp).",
    )
    parser.add_argument("--profiles-root", type=Path, help="Override profiles output folder.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Path to the repo checkout to index. If omitted, a small sample repo is created.",
    )
    parser.add_argument(
        "--ingest-path",
        type=Path,
        help="Path to ingest.json. If omitted, a sample ingest.json is created.",
    )
    parser.add_argument("--top-n-stats", type=int, default=20, help="Profiler rows to print.")
    parser.add_argument(
        "--profile",
        choices=("index", "chunking", "both"),
        default="index",
        help="Which profiler(s) to run: index, chunking, or both.",
    )
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size.")
    parser.add_argument("--chunk-max-bytes", type=int, default=1200, help="Chunk size in bytes.")
    parser.add_argument("--chunk-overlap-bytes", type=int, default=120, help="Overlap between chunks.")
    parser.add_argument(
        "--chunk-min-split-bytes",
        type=int,
        default=300,
        help="Minimum bytes before newline split.",
    )
    return parser.parse_args()


def _profile_call(label: str, func, *args, top_n: int, profile_dir: Path, **kwargs):
    profiler = cProfile.Profile()
    start = time.perf_counter()
    result = profiler.runcall(func, *args, **kwargs)
    elapsed = time.perf_counter() - start

    profile_path = profile_dir / f"{label}.prof"
    profiler.dump_stats(str(profile_path))

    print(f"[profile] {label}: {elapsed:.2f}s -> {profile_path}")
    stats = pstats.Stats(profiler).sort_stats("cumulative")
    print(f"[profile] top {top_n} cumulative for {label}")
    stats.print_stats(top_n)
    return result


def _write_sample_repo(repo_root: Path, ingest_path: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    files = {
        "app.py": "def greet(name):\n    return f\"hello {name}\"\n",
        "utils.py": "def add(a, b):\n    return a + b\n",
        "README.md": "# Sample Repo\n\nThis is a small repo for profiling.\n",
    }
    for rel_path, content in files.items():
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    ingest = {
        "repo_slug": "sample-repo",
        "head_commit": "profile-run",
        "files": list(files.keys()),
    }
    ingest_path.parent.mkdir(parents=True, exist_ok=True)
    ingest_path.write_text(
        __import__("json").dumps(ingest, indent=2), encoding="utf-8"
    )


def _load_chunk_inputs(repo_root: Path, ingest_path: Path) -> list[FileChunkRequest]:
    manifest = __import__("json").loads(ingest_path.read_text(encoding="utf-8"))
    repo_slug = str(manifest.get("repo_slug") or repo_root.name)
    inputs: list[FileChunkRequest] = []
    for rel_path in manifest.get("files", []):
        path = repo_root / rel_path
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        inputs.append(
            FileChunkRequest(repo_slug=repo_slug, file_path=str(rel_path), content=content)
        )
    return inputs


def main() -> int:
    args = _parse_args()

    run_id = args.run_id
    profiles_root = args.profiles_root or Path(f"data/profiles_{run_id}")
    profiles_root.mkdir(parents=True, exist_ok=True)

    repo_root = args.repo_root or Path(f"data/rag_repo_{run_id}/repo")
    ingest_path = args.ingest_path or Path(f"data/rag_repo_{run_id}/ingest.json")

    if not repo_root.exists() or not ingest_path.exists():
        _write_sample_repo(repo_root, ingest_path)

    chunking_config = ChunkingConfig(
        max_bytes=args.chunk_max_bytes,
        overlap_bytes=args.chunk_overlap_bytes,
        min_split_bytes=args.chunk_min_split_bytes,
    )

    stats = None

    if args.profile in ("index", "both"):
        store = InMemoryVectorStore()
        registry = build_language_registry()
        embedding_provider = LocalEmbeddingProvider()
        embedding_config = EmbeddingConfig(model="local-test", batch_size=args.batch_size)

        def _run_index():
            return index_repo(
                ingest_json_path=ingest_path,
                repo_root=repo_root,
                store=store,
                embedding_provider=embedding_provider,
                embedding_config=embedding_config,
                chunking_config=chunking_config,
                registry=registry,
            )

        stats = _profile_call(
            "index_repo",
            _run_index,
            top_n=args.top_n_stats,
            profile_dir=profiles_root,
        )

    if args.profile in ("chunking", "both"):
        requests = _load_chunk_inputs(repo_root, ingest_path)
        strategy = NaiveChunkingStrategy()

        def _run_chunking():
            total_chunks = 0
            for request in requests:
                total_chunks += len(strategy.chunk(request, None, chunking_config))
            return total_chunks

        _profile_call(
            "chunking_naive",
            _run_chunking,
            top_n=args.top_n_stats,
            profile_dir=profiles_root,
        )

    print("[profile] done")
    print(f"  run_id:         {run_id}")
    print(f"  profiles_root:  {profiles_root}")
    print(f"  repo_root:      {repo_root}")
    print(f"  ingest_path:    {ingest_path}")
    if stats is not None:
        print(
            "  stats: files_seen={files_seen} files_indexed={files_indexed} "
            "chunks_indexed={chunks_indexed} batches_sent={batches_sent} "
            "vectors_upserted={vectors_upserted}".format(
                files_seen=stats.files_seen,
                files_indexed=stats.files_indexed,
                chunks_indexed=stats.chunks_indexed,
                batches_sent=stats.batches_sent,
                vectors_upserted=stats.vectors_upserted,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
