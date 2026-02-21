import argparse
import re
import sys
from pathlib import Path
from typing import Any, Protocol

from src.pipeline.utils import read_json, sha256_hex, utc_now, write_json

import json


def _tokenize(text: str) -> list[str]:
    """Tokenize text for a basic lowercase keyword index."""
    return [t for t in re.split(r"[^a-zA-Z0-9_]+", text.lower()) if t]


def build_index_documents(snapshot_path: Path, max_hotspots: int = 20) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Convert one onboarding snapshot into normalized local index documents."""
    snapshot = read_json(snapshot_path)
    repo_slug = str(snapshot.get("repo_slug") or snapshot_path.parent.name)
    head_commit = str(snapshot.get("head_commit") or "unknown")
    structure = snapshot.get("structure_summary", {})
    hotspots = snapshot.get("hotspots", [])
    start_here = structure.get("start_here_candidates", [])

    top_ext = []
    for item in structure.get("file_type_counts", [])[:5]:
        if isinstance(item, dict):
            top_ext.append(f"{item.get('extension')}:{item.get('count')}")

    docs: list[dict[str, Any]] = []
    overview_text = (
        f"Repository {repo_slug} at commit {head_commit}. "
        f"Total files: {structure.get('total_files', 0)}. "
        f"Top extensions: {', '.join(top_ext) if top_ext else 'none'}."
    )
    docs.append(
        {
            "chunk_id": sha256_hex(f"{repo_slug}:{head_commit}:overview"),
            "chunk_type": "overview",
            "text": overview_text,
            "metadata": {"repo_slug": repo_slug, "head_commit": head_commit},
        }
    )

    for idx, item in enumerate(hotspots[:max_hotspots]):
        if not isinstance(item, dict):
            continue
        docs.append(
            {
                "chunk_id": sha256_hex(f"{repo_slug}:{head_commit}:hotspot:{idx}:{item.get('path')}"),
                "chunk_type": "hotspot",
                "text": (
                    f"Hotspot file {item.get('path')} has touch_count {item.get('touch_count', 0)} "
                    f"and last_touched {item.get('last_touched')}."
                ),
                "metadata": {
                    "repo_slug": repo_slug,
                    "head_commit": head_commit,
                    "touch_count": int(item.get("touch_count") or 0),
                },
            }
        )

    for idx, item in enumerate(start_here[:10]):
        if not isinstance(item, dict):
            continue
        docs.append(
            {
                "chunk_id": sha256_hex(f"{repo_slug}:{head_commit}:start_here:{idx}:{item.get('path')}"),
                "chunk_type": "start_here",
                "text": (
                    f"Recommended starting file {item.get('path')} "
                    f"with score {item.get('score')} and reasons {item.get('reasons')}."
                ),
                "metadata": {"repo_slug": repo_slug, "head_commit": head_commit},
            }
        )

    meta = {
        "repo_slug": repo_slug,
        "head_commit": head_commit,
        "version_key": sha256_hex(f"{repo_slug}:{head_commit}"),
        "generated_at": utc_now(),
        "source_snapshot_path": str(snapshot_path),
    }
    return meta, docs


class IndexerBackend(Protocol):
    def upsert_documents(self, meta: dict[str, Any], docs: list[dict[str, Any]]) -> Path: ...


class LocalJsonIndexer:
    """Local JSON-backed index writer used by the experimental stage."""

    def __init__(self, index_root: Path) -> None:
        self.index_root = Path(index_root)
        self.index_root.mkdir(parents=True, exist_ok=True)

    def upsert_documents(self, meta: dict[str, Any], docs: list[dict[str, Any]]) -> Path:
        """Write docs + inverted index and upsert registry entry by version key."""
        repo_slug = str(meta["repo_slug"])
        head_commit = str(meta["head_commit"])
        out_dir = self.index_root / repo_slug / head_commit
        out_dir.mkdir(parents=True, exist_ok=True)

        docs_path = out_dir / "documents.jsonl"
        with docs_path.open("w", encoding="utf-8") as f:
            for doc in docs:
                f.write(json.dumps(doc))
                f.write("\n")

        inverted: dict[str, list[str]] = {}
        for doc in docs:
            chunk_id = str(doc["chunk_id"])
            for token in set(_tokenize(str(doc["text"]))):
                inverted.setdefault(token, []).append(chunk_id)
        for token in inverted:
            inverted[token] = sorted(set(inverted[token]))
        write_json(out_dir / "inverted_index.json", {"token_to_chunk_ids": inverted})

        write_json(
            out_dir / "metadata.json",
            {
                **meta,
                "doc_count": len(docs),
                "index_backend": "local_json",
            },
        )

        registry_path = self.index_root / "index_registry.json"
        if registry_path.exists():
            registry = read_json(registry_path)
            entries = list(registry.get("entries", []))
        else:
            entries = []
        version_key = str(meta["version_key"])
        entries = [e for e in entries if isinstance(e, dict) and str(e.get("version_key")) != version_key]
        entries.append(
            {
                "repo_slug": repo_slug,
                "head_commit": head_commit,
                "version_key": version_key,
                "documents_path": str(docs_path.relative_to(self.index_root)),
                "updated_at": utc_now(),
            }
        )
        entries.sort(key=lambda e: (str(e["repo_slug"]), str(e["head_commit"])))
        write_json(registry_path, {"generated_at": utc_now(), "entries": entries})
        return docs_path


def index_snapshot(snapshot_path: Path, index_root: Path, max_hotspots: int = 20) -> Path:
    """Index one snapshot with the local JSON backend and return docs path."""
    meta, docs = build_index_documents(snapshot_path, max_hotspots=max_hotspots)
    backend = LocalJsonIndexer(index_root=index_root)
    return backend.upsert_documents(meta, docs)


def _parse_args() -> argparse.Namespace:
    """Parse CLI args for indexing snapshots under one output root."""
    parser = argparse.ArgumentParser(description="Experimental local indexing stage for RAG-like retrieval.")
    parser.add_argument("--output-root", type=Path, required=True, help="Output directory containing snapshots.")
    parser.add_argument("--index-root", type=Path, required=True, help="Index output directory.")
    parser.add_argument("--max-hotspots", type=int, default=20, help="Max hotspots to include as index chunks.")
    return parser.parse_args()


def main() -> int:
    """Index all snapshots under output root and report per-repo status."""
    args = _parse_args()
    snapshots = sorted(args.output_root.glob("*/onboarding_snapshot.json"), key=lambda p: str(p))
    success = 0
    for snapshot in snapshots:
        try:
            out = index_snapshot(snapshot, index_root=args.index_root, max_hotspots=args.max_hotspots)
            print(f"[index] wrote {out}")
            success += 1
        except Exception as exc:
            print(f"[index] failed for {snapshot}: {exc}", file=sys.stderr)
    print(f"[index] completed {success} / {len(snapshots)} repositories")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
