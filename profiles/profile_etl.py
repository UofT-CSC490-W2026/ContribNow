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

from src.pipeline.ingest import ingest_repos
from src.pipeline.load import load_artifact
from src.pipeline.transform import transform_repo


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile ETL stages (ingest, transform, load) in-process."
    )
    parser.add_argument("--repo", action="append", help="Repository URL to ingest (repeatable).")
    parser.add_argument(
        "--run-id",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Run id for output folders (default: timestamp).",
    )
    parser.add_argument("--raw-root", type=Path, help="Use an existing raw root folder.")
    parser.add_argument("--transform-root", type=Path, help="Override transform output folder.")
    parser.add_argument("--output-root", type=Path, help="Override load output folder.")
    parser.add_argument("--profiles-root", type=Path, help="Override profiles output folder.")
    parser.add_argument("--branch", default=None, help="Optional branch name for ingest.")
    parser.add_argument("--depth", type=int, default=None, help="Optional shallow clone depth.")
    parser.add_argument("--top-n-hotspots", type=int, default=20, help="Max hotspots per repo.")
    parser.add_argument("--top-n-stats", type=int, default=20, help="Profiler rows to print.")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip ingest and reuse raw artifacts.")
    parser.add_argument("--skip-transform", action="store_true", help="Skip transform stage.")
    parser.add_argument("--skip-load", action="store_true", help="Skip load stage.")
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


def _collect_raw_dirs(raw_root: Path) -> list[Path]:
    if not raw_root.exists():
        return []
    return sorted(
        [path for path in raw_root.iterdir() if path.is_dir() and (path / "ingest.json").exists()],
        key=lambda path: path.name,
    )


def _collect_transform_paths(transform_root: Path) -> list[Path]:
    if not transform_root.exists():
        return []
    return sorted(transform_root.glob("*/transform.json"), key=lambda path: str(path))


def main() -> int:
    args = _parse_args()

    run_id = args.run_id
    raw_root = args.raw_root or Path(f"data/raw_{run_id}")
    transform_root = args.transform_root or Path(f"data/transform_{run_id}")
    output_root = args.output_root or Path(f"data/output_{run_id}")
    profiles_root = args.profiles_root or Path(f"data/profiles_{run_id}")
    profiles_root.mkdir(parents=True, exist_ok=True)

    # Keep profiling deterministic and local-only.
    os.environ["ENABLE_CLOUD_SYNC"] = "false"

    if not args.skip_ingest:
        if not args.repo:
            print("error: --repo is required unless --skip-ingest is set", file=sys.stderr)
            return 2
        _profile_call(
            "ingest",
            ingest_repos,
            repo_urls=args.repo,
            raw_root=raw_root,
            branch=args.branch,
            depth=args.depth,
            top_n=args.top_n_stats,
            profile_dir=profiles_root,
        )

    if args.skip_ingest and not raw_root.exists():
        print(f"error: raw root does not exist: {raw_root}", file=sys.stderr)
        return 2

    if not args.skip_transform:
        raw_dirs = _collect_raw_dirs(raw_root)
        if not raw_dirs:
            print(f"error: no ingest artifacts found under {raw_root}", file=sys.stderr)
            return 2

        def _run_transform():
            outputs: list[Path] = []
            for raw_repo_dir in raw_dirs:
                outputs.append(transform_repo(raw_repo_dir, transform_root, top_n_hotspots=args.top_n_hotspots))
            return outputs

        _profile_call(
            "transform",
            _run_transform,
            top_n=args.top_n_stats,
            profile_dir=profiles_root,
        )

    if not args.skip_load:
        transform_paths = _collect_transform_paths(transform_root)
        if not transform_paths:
            print(f"error: no transform artifacts found under {transform_root}", file=sys.stderr)
            return 2

        def _run_load():
            outputs: list[Path] = []
            for transform_path in transform_paths:
                outputs.append(load_artifact(transform_path, output_root))
            return outputs

        _profile_call(
            "load",
            _run_load,
            top_n=args.top_n_stats,
            profile_dir=profiles_root,
        )

    print("[profile] done")
    print(f"  run_id:         {run_id}")
    print(f"  raw_root:       {raw_root}")
    print(f"  transform_root: {transform_root}")
    print(f"  output_root:    {output_root}")
    print(f"  profiles_root:  {profiles_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
