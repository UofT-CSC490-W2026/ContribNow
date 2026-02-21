#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


def _run_terraform_output(terraform_dir: Path) -> dict[str, object]:
    proc = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=str(terraform_dir),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "terraform output failed")
    raw = json.loads(proc.stdout)
    return {k: v.get("value") for k, v in raw.items() if isinstance(v, dict)}


def _read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _write_env(path: Path, values: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in sorted(values.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_db_password(cli_value: str | None) -> str:
    if cli_value:
        return cli_value
    env_value = os.getenv("DB_PASSWORD")
    if env_value:
        return env_value
    if sys.stdin.isatty():
        return getpass.getpass("DB password: ")
    raise RuntimeError("DB password is required. Pass --db-password or set DB_PASSWORD in environment.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync .env CLOUD_DB_URL from Terraform outputs.")
    parser.add_argument(
        "--terraform-dir",
        type=Path,
        default=Path("terraform/environments/prod"),
        help="Terraform directory containing state and outputs.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="Target env file.")
    parser.add_argument(
        "--db-password",
        default=None,
        help="DB password used in URL construction (optional if DB_PASSWORD env var is set).",
    )
    parser.add_argument("--tenant-id", default=None, help="Optional TENANT_ID value.")
    parser.add_argument("--user-id", default=None, help="Optional USER_ID value.")
    parser.add_argument("--tenant-salt", default=None, help="Optional TENANT_SALT value.")
    args = parser.parse_args()
    db_password = _resolve_db_password(args.db_password)

    tf = _run_terraform_output(args.terraform_dir)
    endpoint = tf.get("db_endpoint")
    port = tf.get("db_port")
    db_name = tf.get("db_name")
    db_username = tf.get("db_username")
    if not all([endpoint, port, db_name, db_username]):
        raise RuntimeError(
            "Missing required Terraform outputs. Ensure db_endpoint, db_port, db_name, db_username exist."
        )

    password_encoded = quote(str(db_password), safe="")
    db_url = f"postgresql://{db_username}:{password_encoded}@{endpoint}:{port}/{db_name}"

    env = _read_env(args.env_file)
    env["ENABLE_CLOUD_SYNC"] = "true"
    env["CLOUD_DB_URL"] = db_url
    if args.tenant_id is not None:
        env["TENANT_ID"] = args.tenant_id
    if args.user_id is not None:
        env["USER_ID"] = args.user_id
    if args.tenant_salt is not None:
        env["TENANT_SALT"] = args.tenant_salt

    _write_env(args.env_file, env)
    print(f"Wrote {args.env_file} with CLOUD_DB_URL from {args.terraform_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
