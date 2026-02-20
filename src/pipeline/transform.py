import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from src.pipeline.utils import utc_now


def _run_git(args: list[str], cwd: Path) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return process.stdout


def _build_structure_summary(files: list[str]) -> dict[str, object]:
    top_level_counts: Counter[str] = Counter()
    file_type_counts: Counter[str] = Counter()

    for file_path in files:
        path = Path(file_path)
        top_level = path.parts[0] if len(path.parts) > 1 else "."
        top_level_counts[top_level] += 1
        ext = path.suffix.lower()
        file_type_counts[ext if ext else "[no_ext]"] += 1

    return {
        "total_files": len(files),
        "top_level_directories": [
            {"path": path, "file_count": count}
            for path, count in sorted(top_level_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "file_type_counts": [
            {"extension": ext, "count": count}
            for ext, count in sorted(file_type_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "start_here_candidates": _find_start_here_candidates(files),
    }


def _find_start_here_candidates(files: list[str]) -> list[dict[str, object]]:
    patterns: list[tuple[re.Pattern[str], str, int]] = [
        (re.compile(r"(?i)^readme(\..+)?$"), "project_overview", 100),
        (re.compile(r"(?i)^contributing(\..+)?$"), "contribution_guidelines", 95),
        (re.compile(r"(?i)^docs?/"), "documentation", 90),
        (re.compile(r"(?i)^pyproject\.toml$"), "python_project_config", 85),
        (re.compile(r"(?i)^package\.json$"), "node_project_config", 85),
        (re.compile(r"(?i)^makefile$"), "build_entrypoint", 80),
        (re.compile(r"(?i)^dockerfile$"), "runtime_entrypoint", 75),
        (re.compile(r"(?i)^src/main\."), "application_entrypoint", 75),
        (re.compile(r"(?i)^src/app\."), "application_entrypoint", 70),
        (re.compile(r"(?i)^tests?/"), "test_suite", 70),
        (re.compile(r"(?i)^\.github/workflows/"), "ci_workflow", 68),
    ]

    scored: list[tuple[int, str, list[str]]] = []
    for file_path in files:
        norm = file_path.replace("\\", "/")
        reasons: list[str] = []
        score = 0
        for pattern, reason, points in patterns:
            if pattern.search(norm):
                reasons.append(reason)
                score = max(score, points)
        if reasons:
            scored.append((score, norm, sorted(set(reasons))))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{"path": path, "score": score, "reasons": reasons} for score, path, reasons in scored[:15]]


def _compute_hotspots(repo_checkout: Path, top_n: int) -> tuple[list[dict[str, object]], int]:
    output = _run_git(
        ["log", "--date=iso-strict", "--name-only", "--pretty=format:__COMMIT__%x1f%cI"],
        cwd=repo_checkout,
    )

    touch_counter: Counter[str] = Counter()
    last_touched: dict[str, str] = {}
    current_date: str | None = None
    current_files: set[str] = set()
    commits_analyzed = 0

    def flush_commit() -> None:
        if current_date is None:
            return
        for file_path in current_files:
            touch_counter[file_path] += 1
            if file_path not in last_touched:
                last_touched[file_path] = current_date

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("__COMMIT__\x1f"):
            flush_commit()
            current_files = set()
            current_date = line.split("\x1f", 1)[1].strip() or None
            commits_analyzed += 1
            continue
        current_files.add(line.replace("\\", "/"))

    flush_commit()
    ranked = sorted(touch_counter.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    hotspots = [
        {"path": path, "touch_count": touches, "last_touched": last_touched.get(path)}
        for path, touches in ranked
    ]
    return hotspots, commits_analyzed


def transform_repo(raw_repo_dir: Path, transform_root: Path, top_n_hotspots: int = 20) -> Path:
    """Build structure summary + hotspot ranking from a raw ingest directory."""
    raw_repo_dir = Path(raw_repo_dir)
    transform_root = Path(transform_root)

    ingest_path = raw_repo_dir / "ingest.json"
    repo_checkout = raw_repo_dir / "repo"
    if not ingest_path.exists():
        raise FileNotFoundError(f"Missing ingest artifact: {ingest_path}")
    if not repo_checkout.exists():
        raise FileNotFoundError(f"Missing repo checkout: {repo_checkout}")

    ingest_data = json.loads(ingest_path.read_text(encoding="utf-8"))
    repo_slug = str(ingest_data.get("repo_slug") or raw_repo_dir.name)

    structure_summary = _build_structure_summary(list(ingest_data.get("files", [])))
    try:
        hotspots, commits_analyzed = _compute_hotspots(repo_checkout, top_n=top_n_hotspots)
    except subprocess.CalledProcessError:
        hotspots, commits_analyzed = [], 0

    transformed = {
        "repo_slug": repo_slug,
        "repo_url": ingest_data.get("repo_url"),
        "head_commit": ingest_data.get("head_commit"),
        "structure_summary": structure_summary,
        "hotspots": hotspots,
        "transform_metadata": {
            "generated_at": utc_now(),
            "top_n_hotspots": top_n_hotspots,
            "commits_analyzed": commits_analyzed,
            "source_ingest_path": str(ingest_path),
        },
    }

    out_dir = transform_root / repo_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "transform.json"
    out_path.write_text(json.dumps(transformed, indent=2), encoding="utf-8")
    return out_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transform raw ingest data into structure + hotspots.")
    parser.add_argument("--raw-root", type=Path, required=True, help="Directory containing raw repo folders.")
    parser.add_argument(
        "--transform-root",
        type=Path,
        required=True,
        help="Directory to write transformed artifacts.",
    )
    parser.add_argument("--top-n-hotspots", type=int, default=20, help="Max hotspots to emit per repo.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    candidates = sorted(
        [path for path in args.raw_root.iterdir() if path.is_dir() and (path / "ingest.json").exists()],
        key=lambda path: path.name,
    )

    success_count = 0
    for raw_repo_dir in candidates:
        try:
            out_path = transform_repo(raw_repo_dir, args.transform_root, top_n_hotspots=args.top_n_hotspots)
            print(f"[transform] wrote {out_path}")
            success_count += 1
        except Exception as exc:
            print(f"[transform] failed for {raw_repo_dir}: {exc}", file=sys.stderr)

    print(f"[transform] completed {success_count} / {len(candidates)} repositories")
    return 0 if success_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
