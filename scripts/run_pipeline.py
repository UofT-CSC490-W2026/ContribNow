#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, env=env)


def _python_bin() -> str:
    candidate = Path(".venv/bin/python")
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ContribNow ETL pipeline end-to-end.")
    parser.add_argument("--repo", action="append", required=True, help="Repository URL to ingest (repeatable).")
    parser.add_argument(
        "--run-id",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Custom run id (default: timestamp).",
    )
    parser.add_argument("--top-n-hotspots", type=int, default=20, help="Hotspot count (default: 20).")
    parser.add_argument(
        "--cloud-sync",
        action="store_true",
        help="Enable cloud-safe Postgres sync in load step.",
    )
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Apply DB migration before cloud sync (requires --cloud-sync).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.apply_schema and not args.cloud_sync:
        print("error: --apply-schema requires --cloud-sync", file=sys.stderr)
        return 2

    py = _python_bin()
    run_id = args.run_id
    raw_root = f"data/raw_{run_id}"
    transform_root = f"data/transform_{run_id}"
    output_root = f"data/output_{run_id}"

    ingest_cmd = [py, "-m", "src.pipeline.ingest", "--raw-root", raw_root]
    for repo in args.repo:
        ingest_cmd.extend(["--repo", repo])

    print(f"[run] ingest: {', '.join(args.repo)}")
    _run(ingest_cmd)

    print("[run] transform")
    _run(
        [
            py,
            "-m",
            "src.pipeline.transform",
            "--raw-root",
            raw_root,
            "--transform-root",
            transform_root,
            "--top-n-hotspots",
            str(args.top_n_hotspots),
        ]
    )

    print("[run] load")
    load_cmd = [py, "-m", "src.pipeline.load", "--transform-root", transform_root, "--output-root", output_root]
    load_env = os.environ.copy()
    # Keep local-only runs deterministic even if ENABLE_CLOUD_SYNC=true exists in .env.
    if not args.cloud_sync:
        load_env["ENABLE_CLOUD_SYNC"] = "false"
    if args.cloud_sync:
        load_cmd.append("--sync-cloud")
        if args.apply_schema:
            load_cmd.append("--apply-schema")
    _run(load_cmd, env=load_env)

    print("[run] done")
    print(f"  run_id:          {run_id}")
    print(f"  raw_root:        {raw_root}")
    print(f"  transform_root:  {transform_root}")
    print(f"  output_root:     {output_root}")
    print(f"  index:           {output_root}/index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
