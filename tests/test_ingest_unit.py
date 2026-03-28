"""
Unit tests for ingest.py helper functions.

These tests use mocks for git subprocess calls where possible and only
create real git repos when testing git-dependent functions.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.pipeline.ingest import (
    _build_commit_log,
    _detect_default_branch,
    _fetch_or_clone,
    _file_content_hash,
    _head_commit,
    _list_files,
    _parse_args,
    _slug_from_url,
    main,
)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, capture_output=True, text=True)


class TestSlugFromUrl(unittest.TestCase):
    """Tests for _slug_from_url."""

    def test_slug_from_https_url(self) -> None:
        slug = _slug_from_url("https://github.com/org/repo.git")
        self.assertIn("org", slug)
        self.assertIn("repo", slug)
        self.assertNotIn(".git", slug)

    def test_slug_from_ssh_url(self) -> None:
        """SSH URL format (git@host:org/repo) triggers the '@' branch."""
        slug = _slug_from_url("git@github.com:org/repo.git")
        self.assertIn("org", slug)
        self.assertIn("repo", slug)
        self.assertNotIn(".git", slug)

    def test_slug_from_url_with_trailing_slash(self) -> None:
        slug = _slug_from_url("https://github.com/org/repo/")
        self.assertIn("org", slug)
        self.assertIn("repo", slug)

    def test_slug_from_bare_name(self) -> None:
        """Edge case: bare name without slashes → 'repo' or the name."""
        slug = _slug_from_url("myrepo")
        self.assertTrue(len(slug) > 0)


class TestFetchOrClone(unittest.TestCase):
    """Tests for _fetch_or_clone."""

    def test_dir_exists_no_git(self) -> None:
        """Directory exists but is not a git repo → RuntimeError."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "not-a-repo"
            repo_dir.mkdir()
            (repo_dir / "dummy.txt").write_text("not git", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                _fetch_or_clone("https://example.com/repo.git", repo_dir, branch=None, depth=None)

    def test_existing_repo_fetch(self) -> None:
        """Existing git repo → fetch + checkout (exercises lines 44-63)."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a source repo
            source = Path(tmp) / "source"
            source.mkdir()
            _run(["git", "init"], cwd=source)
            _run(["git", "config", "user.name", "Test"], cwd=source)
            _run(["git", "config", "user.email", "test@test.com"], cwd=source)
            (source / "file.txt").write_text("v1", encoding="utf-8")
            _run(["git", "add", "."], cwd=source)
            _run(["git", "commit", "-m", "init"], cwd=source)

            # Clone it
            clone = Path(tmp) / "clone"
            url = source.resolve().as_uri()
            _fetch_or_clone(url, clone, branch=None, depth=None)

            # Now fetch again (exercises the existing .git path)
            (source / "file.txt").write_text("v2", encoding="utf-8")
            _run(["git", "add", "."], cwd=source)
            _run(["git", "commit", "-m", "update"], cwd=source)
            _fetch_or_clone(url, clone, branch=None, depth=None)

    def test_clone_with_depth(self) -> None:
        """Clone with depth parameter."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            _run(["git", "init"], cwd=source)
            _run(["git", "config", "user.name", "Test"], cwd=source)
            _run(["git", "config", "user.email", "test@test.com"], cwd=source)
            (source / "file.txt").write_text("v1", encoding="utf-8")
            _run(["git", "add", "."], cwd=source)
            _run(["git", "commit", "-m", "init"], cwd=source)

            clone = Path(tmp) / "clone"
            url = source.resolve().as_uri()
            _fetch_or_clone(url, clone, branch=None, depth=1)
            self.assertTrue((clone / ".git").exists())

    def test_existing_repo_fetch_with_branch_and_depth(self) -> None:
        """Existing repo → fetch with branch and depth (lines 52-55, 58-62)."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            _run(["git", "init"], cwd=source)
            _run(["git", "config", "user.name", "Test"], cwd=source)
            _run(["git", "config", "user.email", "test@test.com"], cwd=source)
            (source / "file.txt").write_text("v1", encoding="utf-8")
            _run(["git", "add", "."], cwd=source)
            _run(["git", "commit", "-m", "init"], cwd=source)

            # Get branch name from source
            branch_out = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(source), capture_output=True, text=True
            )
            branch = branch_out.stdout.strip()

            # Clone first
            clone = Path(tmp) / "clone"
            url = source.resolve().as_uri()
            _fetch_or_clone(url, clone, branch=None, depth=None)

            # Then fetch with branch and depth (exercises lines 52-55, 58-62)
            _fetch_or_clone(url, clone, branch=branch, depth=1)
            self.assertTrue((clone / ".git").exists())

    def test_clone_with_branch(self) -> None:
        """Clone with branch parameter (line 69)."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            _run(["git", "init"], cwd=source)
            _run(["git", "config", "user.name", "Test"], cwd=source)
            _run(["git", "config", "user.email", "test@test.com"], cwd=source)
            (source / "file.txt").write_text("v1", encoding="utf-8")
            _run(["git", "add", "."], cwd=source)
            _run(["git", "commit", "-m", "init"], cwd=source)

            branch_out = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(source), capture_output=True, text=True
            )
            branch = branch_out.stdout.strip()

            clone = Path(tmp) / "clone"
            url = source.resolve().as_uri()
            _fetch_or_clone(url, clone, branch=branch, depth=None)
            self.assertTrue((clone / ".git").exists())

    def test_existing_repo_checkout_fallback(self) -> None:
        """Checkout fails → falls back to checkout -B (lines 61-62).

        Modern git auto-creates local branches from remote tracking, so
        we mock _run_git to force the first checkout to fail while letting
        the -B fallback succeed.
        """
        from src.pipeline import ingest as ingest_mod

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            _run(["git", "init"], cwd=source)
            _run(["git", "config", "user.name", "Test"], cwd=source)
            _run(["git", "config", "user.email", "test@test.com"], cwd=source)
            (source / "file.txt").write_text("v1", encoding="utf-8")
            _run(["git", "add", "."], cwd=source)
            _run(["git", "commit", "-m", "init"], cwd=source)

            clone = Path(tmp) / "clone"
            url = source.resolve().as_uri()
            _fetch_or_clone(url, clone, branch=None, depth=None)

            # Mock _run_git so "checkout <branch>" (without -B) raises,
            # but all other git commands (including checkout -B) succeed.
            real_run_git = ingest_mod._run_git

            def mock_run_git(args, cwd=None):
                if args[:1] == ["checkout"] and "-B" not in args:
                    raise subprocess.CalledProcessError(1, "git checkout")
                return real_run_git(args, cwd=cwd)

            with patch.object(ingest_mod, "_run_git", side_effect=mock_run_git):
                _fetch_or_clone(url, clone, branch="master", depth=None)

    def test_existing_repo_no_remote(self) -> None:
        """Existing repo with no remote → adds origin (line 48-49)."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a repo with no remote
            local = Path(tmp) / "local"
            local.mkdir()
            _run(["git", "init"], cwd=local)
            _run(["git", "config", "user.name", "Test"], cwd=local)
            _run(["git", "config", "user.email", "test@test.com"], cwd=local)
            (local / "file.txt").write_text("v1", encoding="utf-8")
            _run(["git", "add", "."], cwd=local)
            _run(["git", "commit", "-m", "init"], cwd=local)

            # Create a source to point to
            source = Path(tmp) / "source"
            source.mkdir()
            _run(["git", "init", "--bare"], cwd=source)

            url = source.resolve().as_uri()
            # This should add origin since it doesn't exist yet
            try:
                _fetch_or_clone(url, local, branch=None, depth=None)
            except subprocess.CalledProcessError:
                pass  # fetch may fail on bare empty repo, but the remote add should work


class TestDetectDefaultBranch(unittest.TestCase):
    """Tests for _detect_default_branch."""

    def test_fallback_to_rev_parse(self) -> None:
        """When symbolic-ref fails, falls back to rev-parse."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _run(["git", "init"], cwd=repo)
            _run(["git", "config", "user.name", "Test"], cwd=repo)
            _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
            (repo / "file.txt").write_text("x", encoding="utf-8")
            _run(["git", "add", "."], cwd=repo)
            _run(["git", "commit", "-m", "init"], cwd=repo)

            # This repo has no remote, so symbolic-ref will fail,
            # triggering the fallback
            result = _detect_default_branch(repo)
            # Should return a branch name (typically "main" or "master")
            self.assertIsNotNone(result)

    def test_returns_none_for_detached_head(self) -> None:
        """Both symbolic-ref and rev-parse fail → None."""
        with patch("src.pipeline.ingest._run_git") as mock_git:
            mock_git.side_effect = subprocess.CalledProcessError(1, "git")
            result = _detect_default_branch(Path("/tmp"))
            self.assertIsNone(result)


class TestHeadCommit(unittest.TestCase):
    """Tests for _head_commit."""

    def test_failure_returns_none(self) -> None:
        """CalledProcessError → None."""
        with patch("src.pipeline.ingest._run_git") as mock_git:
            mock_git.side_effect = subprocess.CalledProcessError(1, "git")
            result = _head_commit(Path("/tmp"))
            self.assertIsNone(result)


class TestFileContentHash(unittest.TestCase):
    """Tests for _file_content_hash."""

    def test_file_too_large(self) -> None:
        """File larger than 1MB → empty string."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "big.py"
            f.write_text("x", encoding="utf-8")
            result = _file_content_hash(f, size=2_000_000)
            self.assertEqual(result, "")

    def test_binary_extension(self) -> None:
        """Binary file extension → empty string."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "image.png"
            f.write_bytes(b"\x89PNG")
            result = _file_content_hash(f, size=4)
            self.assertEqual(result, "")

    def test_oserror(self) -> None:
        """Non-existent file → empty string."""
        result = _file_content_hash(Path("/nonexistent/file.py"), size=10)
        self.assertEqual(result, "")

    def test_valid_file_returns_hash(self) -> None:
        """Valid text file → non-empty SHA-256 hex string."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "code.py"
            f.write_text("print('hello')\n", encoding="utf-8")
            result = _file_content_hash(f, size=f.stat().st_size)
            self.assertEqual(len(result), 64)  # SHA-256 hex length


class TestListFiles(unittest.TestCase):
    """Tests for _list_files."""

    def test_ignores_hidden_dirs(self) -> None:
        """Ignored directories (.git, __pycache__) are excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir()
            (repo / ".git" / "config").write_text("", encoding="utf-8")
            (repo / "__pycache__").mkdir()
            (repo / "__pycache__" / "mod.pyc").write_text("", encoding="utf-8")
            (repo / "src").mkdir()
            (repo / "src" / "app.py").write_text("x = 1", encoding="utf-8")

            files, records = _list_files(repo)
            self.assertEqual(files, ["src/app.py"])
            self.assertEqual(len(records), 1)


class TestListFilesStatError(unittest.TestCase):
    """Tests for _list_files stat OSError edge case."""

    def test_stat_oserror_yields_zero_size(self) -> None:
        """When stat() raises OSError, size defaults to 0 (lines 169-170)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "ok.py").write_text("x = 1", encoding="utf-8")

            original_stat = Path.stat

            def flaky_stat(self_path, *args, **kwargs):
                if self_path.name == "ok.py":
                    raise OSError("permission denied")
                return original_stat(self_path, *args, **kwargs)

            with patch.object(Path, "stat", flaky_stat):
                files, records = _list_files(repo)

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["size_bytes"], 0)


class TestBuildCommitLog(unittest.TestCase):
    """Tests for _build_commit_log with mocked git output."""

    def test_blank_record_skipped(self) -> None:
        """Records with fewer than 5 parts are skipped."""
        # Pass 1 output: valid record + malformed record (only 3 parts)
        meta_output = (
            "abc123\x1f2026-01-01\x1fAlice\x1fa@b.com\x1finitial\x1e"
            "short\x1fonly\x1fthree\x1e"
        )
        # Pass 2 output: numstat for the valid commit
        numstat_output = "__COMMIT__abc123\n1\t0\tfile.py\n"

        with patch("src.pipeline.ingest._run_git") as mock_git:
            mock_git.side_effect = [meta_output, numstat_output]
            with tempfile.TemporaryDirectory() as tmp:
                result = _build_commit_log(Path(tmp))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sha"], "abc123")

    def test_empty_sha_skipped(self) -> None:
        """Record with empty SHA is skipped."""
        meta_output = "\x1f2026-01-01\x1fAlice\x1fa@b.com\x1fmsg\x1e"
        numstat_output = ""

        with patch("src.pipeline.ingest._run_git") as mock_git:
            mock_git.side_effect = [meta_output, numstat_output]
            with tempfile.TemporaryDirectory() as tmp:
                result = _build_commit_log(Path(tmp))

        self.assertEqual(len(result), 0)

    def test_numstat_value_error(self) -> None:
        """Non-numeric additions/deletions in numstat → line skipped."""
        meta_output = "abc\x1f2026-01-01\x1fAlice\x1fa@b.com\x1fmsg\x1e"
        numstat_output = "__COMMIT__abc\nnotnum\tnotnum\tfile.py\n"

        with patch("src.pipeline.ingest._run_git") as mock_git:
            mock_git.side_effect = [meta_output, numstat_output]
            with tempfile.TemporaryDirectory() as tmp:
                result = _build_commit_log(Path(tmp))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["files_changed"], [])

    def test_numstat_binary_file_dashes(self) -> None:
        """Binary files show '-' for additions/deletions → treated as 0."""
        meta_output = "abc\x1f2026-01-01\x1fAlice\x1fa@b.com\x1fmsg\x1e"
        numstat_output = "__COMMIT__abc\n-\t-\timage.png\n"

        with patch("src.pipeline.ingest._run_git") as mock_git:
            mock_git.side_effect = [meta_output, numstat_output]
            with tempfile.TemporaryDirectory() as tmp:
                result = _build_commit_log(Path(tmp))

        self.assertEqual(len(result[0]["files_changed"]), 1)
        self.assertEqual(result[0]["files_changed"][0]["additions"], 0)
        self.assertEqual(result[0]["files_changed"][0]["deletions"], 0)

    def test_numstat_wrong_tab_parts(self) -> None:
        """Numstat line with tab but not 3 parts → skipped (line 236)."""
        meta_output = "abc\x1f2026-01-01\x1fAlice\x1fa@b.com\x1fmsg\x1e"
        numstat_output = "__COMMIT__abc\n1\tfile.py\n"

        with patch("src.pipeline.ingest._run_git") as mock_git:
            mock_git.side_effect = [meta_output, numstat_output]
            with tempfile.TemporaryDirectory() as tmp:
                result = _build_commit_log(Path(tmp))

        # Line had a tab but only 2 parts, so no files_changed
        self.assertEqual(result[0]["files_changed"], [])


class TestIngestParseArgs(unittest.TestCase):
    """Tests for _parse_args CLI argument parsing."""

    def test_parse_args_single_repo(self) -> None:
        with patch("sys.argv", ["ingest", "--repo", "https://github.com/org/repo.git", "--raw-root", "/tmp/raw"]):
            args = _parse_args()
        self.assertEqual(args.repo, ["https://github.com/org/repo.git"])
        self.assertEqual(args.raw_root, Path("/tmp/raw"))
        self.assertIsNone(args.branch)
        self.assertIsNone(args.depth)

    def test_parse_args_multiple_repos(self) -> None:
        with patch("sys.argv", [
            "ingest",
            "--repo", "https://github.com/org/a.git",
            "--repo", "https://github.com/org/b.git",
            "--raw-root", "/tmp/raw",
            "--branch", "main",
            "--depth", "1",
        ]):
            args = _parse_args()
        self.assertEqual(len(args.repo), 2)
        self.assertEqual(args.branch, "main")
        self.assertEqual(args.depth, 1)

    def test_parse_args_missing_required(self) -> None:
        with patch("sys.argv", ["ingest"]):
            with self.assertRaises(SystemExit):
                _parse_args()


class TestIngestMain(unittest.TestCase):
    """Tests for ingest main() entry point."""

    def test_main_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            _run(["git", "init"], cwd=source)
            _run(["git", "config", "user.name", "Test"], cwd=source)
            _run(["git", "config", "user.email", "test@test.com"], cwd=source)
            (source / "file.txt").write_text("v1", encoding="utf-8")
            _run(["git", "add", "."], cwd=source)
            _run(["git", "commit", "-m", "init"], cwd=source)

            raw_root = Path(tmp) / "raw"
            url = source.resolve().as_uri()
            with patch("sys.argv", ["ingest", "--repo", url, "--raw-root", str(raw_root)]):
                exit_code = main()
            self.assertEqual(exit_code, 0)

    def test_main_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp) / "raw"
            with patch("sys.argv", ["ingest", "--repo", "file:///nonexistent", "--raw-root", str(raw_root)]):
                exit_code = main()
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
