#!/usr/bin/env python3
import argparse
import cProfile
import sys
import time
from datetime import datetime
from pathlib import Path
import pstats

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Template profiler (copy and customize).")
    parser.add_argument(
        "--run-id",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Run id for output folders (default: timestamp).",
    )
    parser.add_argument("--top-n-stats", type=int, default=20, help="Profiler rows to print.")
    # Add domain-specific inputs here (e.g., --query, --dataset, --model, --tenant-id).
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


def main() -> int:
    args = _parse_args()
    profiles_root = Path(f"data/profiles_{args.run_id}")
    profiles_root.mkdir(parents=True, exist_ok=True)

    # TODO: import your target functions and call them under _profile_call.
    # Example:
    # from src.rag.pipeline import run_query
    # _profile_call(
    #     "rag_query",
    #     run_query,
    #     query=args.query,
    #     top_n=args.top_n_stats,
    #     profile_dir=profiles_root,
    # )

    print("[profile] done")
    print(f"  run_id:        {args.run_id}")
    print(f"  profiles_root: {profiles_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
