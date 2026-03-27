import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from src.pipeline.utils import utc_now

COMMIT_LOG_LIMIT = 500
INGEST_SCHEMA_VERSION = 2


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return process.stdout


def _slug_from_url(url: str) -> str:
    trimmed = re.sub(r"\.git$", "", url.strip().rstrip("/"))
    if ":" in trimmed and "@" in trimmed.split(":", 1)[0]:
        tail = trimmed.split(":", 1)[1]
    else:
        tail = trimmed.split("://", 1)[-1]
        tail = tail.split("/", 1)[1] if "/" in tail else tail
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", tail.replace("/", "__"))
    return slug or "repo"


def _fetch_or_clone(url: str, repo_dir: Path, branch: str | None, depth: int | None) -> None:
    if repo_dir.exists() and not (repo_dir / ".git").exists():
        raise RuntimeError(f"{repo_dir} exists but is not a git repository")

    if (repo_dir / ".git").exists():
        try:
            _run_git(["remote", "get-url", "origin"], cwd=repo_dir)
            _run_git(["remote", "set-url", "origin", url], cwd=repo_dir)
        except subprocess.CalledProcessError:
            _run_git(["remote", "add", "origin", url], cwd=repo_dir)

        fetch_cmd = ["fetch", "origin"]
        if branch:
            fetch_cmd.append(branch)
        if depth is not None:
            fetch_cmd.extend(["--depth", str(depth)])
        _run_git(fetch_cmd, cwd=repo_dir)

        if branch:
            try:
                _run_git(["checkout", branch], cwd=repo_dir)
            except subprocess.CalledProcessError:
                _run_git(["checkout", "-B", branch, f"origin/{branch}"], cwd=repo_dir)
        return

    clone_cmd = ["clone"]
    if depth is not None:
        clone_cmd.extend(["--depth", str(depth)])
    if branch:
        clone_cmd.extend(["--branch", branch])
    clone_cmd.extend([url, str(repo_dir)])
    _run_git(clone_cmd)


def _detect_default_branch(repo_dir: Path) -> str | None:
    try:
        ref = _run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_dir).strip()
        return ref.rsplit("/", 1)[-1] if ref else None
    except subprocess.CalledProcessError:
        try:
            branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir).strip()
            return None if branch == "HEAD" else branch
        except subprocess.CalledProcessError:
            return None


def _head_commit(repo_dir: Path) -> str | None:
    try:
        return _run_git(["rev-parse", "HEAD"], cwd=repo_dir).strip() or None
    except subprocess.CalledProcessError:
        return None


_MAX_HASH_FILE_SIZE = 1 * 1024 * 1024  # skip hashing files larger than 1 MB

_IGNORED_DIR_NAMES: set[str] = {
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
}

_BINARY_EXTENSIONS: set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg", ".tiff",
    # Video / audio
    ".mp4", ".avi", ".mov", ".mkv", ".mp3", ".wav", ".flac", ".ogg",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    # Compiled / binary
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".class", ".o", ".a",
    # Fonts
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    # Documents / data
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Other
    ".bin", ".dat", ".db", ".sqlite", ".wasm",
}


def _file_content_hash(file_path: Path, size: int) -> str:
    """Compute SHA-256 of a file's contents for change detection.

    Returns empty string for binary files (by extension) or files larger
    than _MAX_HASH_FILE_SIZE — these are not meaningful for pipeline analysis.
    """
    if size > _MAX_HASH_FILE_SIZE:
        return ""
    if file_path.suffix.lower() in _BINARY_EXTENSIONS:
        return ""
    try:
        with file_path.open("rb") as fh:
            return hashlib.file_digest(fh, "sha256").hexdigest()
    except OSError:
        return ""


def _list_files(repo_dir: Path) -> tuple[list[str], list[dict[str, object]]]:
    """
    Walk the repo and return both a flat path list and per-file metadata.

    Returns:
        files              — posix-style relative paths (backward-compatible)
        files_with_hashes  — [{path, content_hash, size_bytes}] for each file
    """
    repo_dir = Path(repo_dir)
    records: list[dict[str, object]] = []

    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [
            d
            for d in dirnames
            if d.lower() not in _IGNORED_DIR_NAMES
        ]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(repo_dir).as_posix()
            try:
                size: int = path.stat().st_size
            except OSError:
                size = 0
            records.append(
                {
                    "path": rel,
                    "content_hash": _file_content_hash(path, size),
                    "size_bytes": size,
                }
            )

    records.sort(key=lambda r: str(r["path"]))
    files = [str(r["path"]) for r in records]
    return files, records


def _build_commit_log(repo_dir: Path, max_count: int = COMMIT_LOG_LIMIT) -> list[dict[str, object]]:
    """
    Build a rich commit log with author info and per-file change stats.

    Uses two git passes joined by SHA to avoid fragile parsing of multi-line
    commit message bodies:
      - Pass 1: SHA, date, author name/email, full message body
      - Pass 2: per-file addition/deletion counts via --numstat
    """
    # Pass 1: commit metadata
    meta_output = _run_git(
        ["log", f"-n{max_count}", "--date=iso-strict",
         "--pretty=format:%H%x1f%cI%x1f%aN%x1f%aE%x1f%B%x1e"],
        cwd=repo_dir,
    )
    sha_order: list[str] = []
    meta_by_sha: dict[str, dict[str, object]] = {}
    for record in meta_output.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f", 4)
        if len(parts) < 5:
            continue
        sha = parts[0].strip()
        if not sha:
            continue
        sha_order.append(sha)
        meta_by_sha[sha] = {
            "sha": sha,
            "author_date": parts[1].strip(),
            "author_name": parts[2].strip(),
            "author_email": parts[3].strip(),
            "message": parts[4].strip(),
            "files_changed": [],
        }

    # Pass 2: per-file addition/deletion counts
    numstat_output = _run_git(
        ["log", f"-n{max_count}", "--numstat", "--pretty=format:__COMMIT__%H"],
        cwd=repo_dir,
    )
    current_sha: str | None = None
    for raw_line in numstat_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("__COMMIT__"):
            current_sha = line[len("__COMMIT__"):]
        elif current_sha and "\t" in line:
            tab_parts = line.split("\t", 2)
            if len(tab_parts) != 3:
                continue
            add_str, del_str, path_str = tab_parts
            try:
                additions = int(add_str) if add_str.strip() not in ("", "-") else 0
                deletions = int(del_str) if del_str.strip() not in ("", "-") else 0
            except ValueError:
                continue
            if current_sha in meta_by_sha:
                meta_by_sha[current_sha]["files_changed"].append(  # type: ignore[union-attr]
                    {
                        "path": path_str.strip().replace("\\", "/"),
                        "additions": additions,
                        "deletions": deletions,
                    }
                )

    return [meta_by_sha[sha] for sha in sha_order if sha in meta_by_sha]


def ingest_repos(
    repo_urls: list[str],
    raw_root: Path,
    branch: str | None = None,
    depth: int | None = None,
) -> list[Path]:
    """Clone/fetch repos and write per-repo raw ingest manifests."""
    raw_root = Path(raw_root)
    raw_root.mkdir(parents=True, exist_ok=True)
    completed: list[Path] = []

    for repo_url in repo_urls:
        slug = _slug_from_url(repo_url)
        raw_repo_dir = raw_root / slug
        repo_checkout_dir = raw_repo_dir / "repo"
        raw_repo_dir.mkdir(parents=True, exist_ok=True)

        try:
            _fetch_or_clone(repo_url, repo_checkout_dir, branch=branch, depth=depth)
            files, files_with_hashes = _list_files(repo_checkout_dir)
            manifest = {
                "ingest_schema_version": INGEST_SCHEMA_VERSION,
                "repo_slug": slug,
                "repo_url": repo_url,
                "default_branch": _detect_default_branch(repo_checkout_dir),
                "head_commit": _head_commit(repo_checkout_dir),
                "generated_at": utc_now(),
                "files": files,
                "files_with_hashes": files_with_hashes,
                "commit_log": _build_commit_log(repo_checkout_dir),
            }
            (raw_repo_dir / "ingest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            completed.append(raw_repo_dir)
        except Exception as exc:
            print(f"[ingest] failed for {repo_url}: {exc}", file=sys.stderr)

    return completed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest GitHub repositories into raw ETL artifacts.")
    parser.add_argument("--repo", action="append", required=True, help="Repository URL (repeatable).")
    parser.add_argument("--raw-root", type=Path, required=True, help="Directory for raw artifacts.")
    parser.add_argument("--branch", default=None, help="Optional branch name.")
    parser.add_argument("--depth", type=int, default=None, help="Optional shallow clone depth.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    successful = ingest_repos(
        repo_urls=args.repo,
        raw_root=args.raw_root,
        branch=args.branch,
        depth=args.depth,
    )
    print(f"[ingest] completed {len(successful)} / {len(args.repo)} repositories")
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
