import argparse
import os
import sys
import uuid
from pathlib import Path

from src.pipeline.cloud_sync import is_cloud_sync_enabled, sync_cloud_safe
from src.pipeline.utils import read_json, utc_now, write_json


def _load_env_file(path: Path, override: bool = False) -> None:
    """Load KEY=VALUE pairs from a dotenv-style file into os.environ."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


def load_artifact(transform_json_path: Path, output_root: Path) -> Path:
    """Write final onboarding snapshot and update output index.json."""
    transform_json_path = Path(transform_json_path)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    transformed = read_json(transform_json_path)
    repo_slug = str(transformed.get("repo_slug") or transform_json_path.parent.name)
    timestamp = utc_now()

    repo_out_dir = output_root / repo_slug
    repo_out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = repo_out_dir / "onboarding_snapshot.json"

    snapshot = {
        "repo_slug": repo_slug,
        "repo_url": transformed.get("repo_url"),
        "head_commit": transformed.get("head_commit"),
        "structure_summary": transformed.get("structure_summary", {}),
        "hotspots": transformed.get("hotspots", []),
        "risk_matrix": transformed.get("risk_levels", {}),
        "co_change_pairs": transformed.get("co_change_pairs", []),
        "authorship_summary": transformed.get("authorship", {}),
        "dependency_graph": transformed.get("dependency_graph", {}),
        "conventions": transformed.get("conventions", {}),
        "transform_metadata": transformed.get("transform_metadata", {}),
        "load_metadata": {
            "generated_at": timestamp,
            "source_transform_path": str(transform_json_path),
        },
    }
    write_json(snapshot_path, snapshot)

    index_path = output_root / "index.json"
    if index_path.exists():
        current_index = read_json(index_path)
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
    write_json(index_path, {"generated_at": timestamp, "artifacts": artifacts})
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
    parser.add_argument(
        "--sync-cloud",
        action="store_true",
        help="Sync cloud-safe metadata to Postgres after writing local artifacts.",
    )
    parser.add_argument("--tenant-id", default=None, help="Workspace tenant identifier.")
    parser.add_argument("--user-id", default=None, help="Producer user identifier.")
    parser.add_argument("--tenant-salt", default=None, help="Tenant-scoped hashing salt.")
    parser.add_argument("--db-url", default=None, help="Postgres connection URL.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Optional dotenv file with TENANT_ID/USER_ID/TENANT_SALT/CLOUD_DB_URL/ENABLE_CLOUD_SYNC.",
    )
    parser.add_argument(
        "--schema-sql-path",
        type=Path,
        default=Path("db/migrations/001_cloud_safe_sync.sql"),
        help="Migration SQL path for cloud sync schema.",
    )
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Apply migration SQL before syncing (no-op unless cloud sync is enabled).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _load_env_file(args.env_file)
    transforms = sorted(args.transform_root.glob("*/transform.json"), key=lambda path: str(path))
    success_count = 0
    sync_enabled = args.sync_cloud or is_cloud_sync_enabled()
    local_run_id = str(uuid.uuid4())
    tenant_id = args.tenant_id or os.getenv("TENANT_ID")
    user_id = args.user_id or os.getenv("USER_ID", "unknown-user")
    tenant_salt = args.tenant_salt or os.getenv("TENANT_SALT")
    db_url = args.db_url or os.getenv("CLOUD_DB_URL")

    for transform_path in transforms:
        try:
            snapshot_path = load_artifact(transform_path, args.output_root)
            print(f"[load] wrote {snapshot_path}")
            if sync_enabled:
                if not tenant_id or not tenant_salt or not db_url:
                    raise ValueError(
                        "Cloud sync enabled but required values are missing: tenant_id, tenant_salt, db_url."
                    )
                sync_result = sync_cloud_safe(
                    transform_json_path=transform_path,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    tenant_salt=tenant_salt,
                    db_url=db_url,
                    local_run_id=local_run_id,
                    schema_sql_path=args.schema_sql_path,
                    apply_schema=args.apply_schema,
                )
                print(
                    f"[load] cloud-sync status={sync_result.status} "
                    f"version_key={sync_result.version_key} synced_at={sync_result.synced_at}"
                )
            success_count += 1
        except Exception as exc:
            print(f"[load] failed for {transform_path}: {exc}", file=sys.stderr)

    print(f"[load] completed {success_count} / {len(transforms)} repositories")
    return 0 if success_count else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
