import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

COMMIT_LOG_LIMIT = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _list_files(repo_dir: Path) -> list[str]:
    files: list[str] = []
    for path in repo_dir.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            files.append(path.relative_to(repo_dir).as_posix())
    files.sort()
    return files


def _files_changed_count(repo_dir: Path, sha: str) -> int:
    out = _run_git(["show", "--pretty=format:", "--name-only", sha], cwd=repo_dir)
    return len({line.strip() for line in out.splitlines() if line.strip()})


def _build_commit_log(repo_dir: Path, max_count: int = COMMIT_LOG_LIMIT) -> list[dict[str, object]]:
    output = _run_git(
        ["log", f"-n{max_count}", "--date=iso-strict", "--pretty=format:%H%x1f%cI%x1f%B%x1e"],
        cwd=repo_dir,
    )
    records = [chunk for chunk in output.split("\x1e") if chunk.strip()]
    commit_log: list[dict[str, object]] = []

    for record in records:
        parts = record.split("\x1f", 2)
        if len(parts) < 3:
            continue
        sha = parts[0].strip()
        author_date = parts[1].strip()
        message = parts[2].strip()
        if not sha:
            continue
        commit_log.append(
            {
                "sha": sha,
                "author_date": author_date,
                "message": message,
                "files_changed_count": _files_changed_count(repo_dir, sha),
            }
        )
    return commit_log


def ingest_repos(
    repo_urls: list[str],
    raw_root: Path,
    branch: str | None = None,
    depth: int | None = None,
) -> list[Path]:
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
            manifest = {
                "repo_slug": slug,
                "repo_url": repo_url,
                "default_branch": _detect_default_branch(repo_checkout_dir),
                "head_commit": _head_commit(repo_checkout_dir),
                "generated_at": _utc_now(),
                "files": _list_files(repo_checkout_dir),
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
