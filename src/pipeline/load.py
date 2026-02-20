import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_artifact(transform_json_path: Path, output_root: Path) -> Path:
    transform_json_path = Path(transform_json_path)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    transformed = _read_json(transform_json_path)
    repo_slug = str(transformed.get("repo_slug") or transform_json_path.parent.name)
    timestamp = _utc_now()

    repo_out_dir = output_root / repo_slug
    repo_out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = repo_out_dir / "onboarding_snapshot.json"

    snapshot = {
        "repo_slug": repo_slug,
        "repo_url": transformed.get("repo_url"),
        "head_commit": transformed.get("head_commit"),
        "structure_summary": transformed.get("structure_summary", {}),
        "hotspots": transformed.get("hotspots", []),
        "transform_metadata": transformed.get("transform_metadata", {}),
        "load_metadata": {
            "generated_at": timestamp,
            "source_transform_path": str(transform_json_path),
        },
    }
    _write_json(snapshot_path, snapshot)

    index_path = output_root / "index.json"
    if index_path.exists():
        current_index = _read_json(index_path)
        artifacts = list(current_index.get("artifacts", []))
    else:
        artifacts = []

    artifacts = [entry for entry in artifacts if isinstance(entry, dict) and entry.get("repo_slug") != repo_slug]
    artifacts.append(
        {
            "repo_slug": repo_slug,
            "artifact_path": str(snapshot_path.relative_to(output_root)),
            "updated_at": timestamp,
        }
    )
    artifacts.sort(key=lambda entry: str(entry["repo_slug"]))
    _write_json(index_path, {"generated_at": timestamp, "artifacts": artifacts})
    return snapshot_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load transformed artifacts into final onboarding snapshots.")
    parser.add_argument(
        "--transform-root",
        type=Path,
        required=True,
        help="Directory containing transformed repo artifacts.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Directory for final output artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    transforms = sorted(args.transform_root.glob("*/transform.json"), key=lambda path: str(path))
    success_count = 0

    for transform_path in transforms:
        try:
            snapshot_path = load_artifact(transform_path, args.output_root)
            print(f"[load] wrote {snapshot_path}")
            success_count += 1
        except Exception as exc:
            print(f"[load] failed for {transform_path}: {exc}", file=sys.stderr)

    print(f"[load] completed {success_count} / {len(transforms)} repositories")
    return 0 if success_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
