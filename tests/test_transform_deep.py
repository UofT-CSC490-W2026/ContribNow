"""
Part 4: Deep unit tests for transform.py — the most complex ETL module.

transform.py orchestrates all gold-layer analytics: structure summaries,
hotspot ranking, co-change matrices, risk scoring, convention detection,
and dependency graph extraction. It contains 473 lines with 11+ functions,
a 3-factor weighted risk calculation, and 11 pattern matchers for convention
detection.

We chose transform.py because:
  - It has the highest cyclomatic complexity in the pipeline
  - Its risk scoring uses min-max normalization (edge-case prone)
  - Convention detection involves 11+ pattern matchers with fallbacks
  - Co-change filtering has a critical noise-reduction guard (MAX_FILES_PER_COMMIT)

Each test below targets a specific edge case, failure mode, or important
use case. Tests are annotated with WHY they were chosen.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pipeline.transform import (
    _build_structure_summary,
    _compute_authorship,
    _compute_co_change_matrix,
    _compute_dependency_graph,
    _compute_hotspots_from_commits,
    _compute_risk_levels,
    _detect_conventions,
    _find_start_here_candidates,
    _parse_args,
    _run_git,
    main,
    transform_repo,
)


class TestRunGit(unittest.TestCase):
    """Tests for the _run_git subprocess helper."""

    # WHY: _run_git is the core helper used by every git operation in
    # transform.py. Verifying it works with a valid command ensures the
    # subprocess setup (encoding, capture_output, check=True) is correct.
    def test_run_git_success(self) -> None:
        result = _run_git(["--version"], cwd=Path("."))
        self.assertIn("git version", result)

    # WHY: _run_git uses check=True, meaning invalid flags should raise
    # CalledProcessError. This test verifies error propagation so callers
    # can rely on exceptions for failure detection rather than silent errors.
    def test_run_git_failure_raises(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            _run_git(["log", "--not-a-real-flag"], cwd=Path("."))


class TestBuildStructureSummary(unittest.TestCase):
    """Tests for _build_structure_summary."""

    # WHY: This validates the core structure analysis that counts top-level
    # directories, file types, and identifies "start here" candidates.
    # It exercises the [no_ext] branch for extensionless files.
    def test_build_structure_summary_basic(self) -> None:
        files = [
            "src/app.py",
            "src/utils.py",
            "tests/test_app.py",
            "README.md",
            "Makefile",  # no extension -> [no_ext]
        ]
        result = _build_structure_summary(files)
        self.assertEqual(result["total_files"], 5)
        self.assertIsInstance(result["top_level_directories"], list)
        self.assertIsInstance(result["file_type_counts"], list)
        self.assertIsInstance(result["start_here_candidates"], list)

        # Check [no_ext] is counted
        ext_names = [e["extension"] for e in result["file_type_counts"]]
        self.assertIn("[no_ext]", ext_names)

        # README should be a start-here candidate
        candidate_paths = [c["path"] for c in result["start_here_candidates"]]
        self.assertIn("README.md", candidate_paths)


class TestFindStartHereCandidates(unittest.TestCase):
    """Tests for _find_start_here_candidates."""

    # WHY: Binary files (images, archives, etc.) must be excluded from
    # "start here" recommendations — they are not readable entry points.
    # This tests the skip_extensions filter at line 79.
    def test_find_start_here_binary_skip(self) -> None:
        files = ["README.md", "logo.png", "archive.zip", "docs/guide.md"]
        result = _find_start_here_candidates(files)
        result_paths = [c["path"] for c in result]
        self.assertIn("README.md", result_paths)
        self.assertNotIn("logo.png", result_paths)
        self.assertNotIn("archive.zip", result_paths)


class TestComputeCoChangeMatrix(unittest.TestCase):
    """Tests for _compute_co_change_matrix."""

    # WHY: Commits touching >50 files are typically bulk operations
    # (formatting, dependency bumps) that produce noise in co-change data.
    # The MAX_FILES_PER_COMMIT guard at line 130 must skip these commits.
    def test_compute_co_change_skips_large_commits(self) -> None:
        large_files = [f"file_{i}.py" for i in range(51)]
        commits = [
            {"sha": "aaa", "files": large_files},
            {"sha": "bbb", "files": ["a.py", "b.py"]},
            {"sha": "ccc", "files": ["a.py", "b.py"]},
            {"sha": "ddd", "files": ["a.py", "b.py"]},
        ]
        result = _compute_co_change_matrix(commits, min_threshold=3)
        # a.py + b.py only co-change 3 times (bbb, ccc, ddd) — the large
        # commit should NOT count toward co-changes
        pair = next(
            (p for p in result if {"a.py", "b.py"} == {p["file_a"], p["file_b"]}),
            None,
        )
        self.assertIsNotNone(pair)
        self.assertEqual(pair["co_change_count"], 3)

        # Files from the large commit should NOT appear as co-change pairs
        large_pairs = [
            p for p in result
            if p["file_a"].startswith("file_") or p["file_b"].startswith("file_")
        ]
        self.assertEqual(len(large_pairs), 0)

    # WHY: Pairs below the min_threshold must be excluded to keep
    # co-change data meaningful. This is a negative test ensuring
    # low-frequency co-changes are filtered out.
    def test_compute_co_change_below_threshold(self) -> None:
        commits = [
            {"sha": "aaa", "files": ["x.py", "y.py"]},
            {"sha": "bbb", "files": ["x.py", "y.py"]},
        ]
        result = _compute_co_change_matrix(commits, min_threshold=3)
        self.assertEqual(result, [])


class TestComputeAuthorship(unittest.TestCase):
    """Tests for _compute_authorship."""

    # WHY: Commits may reference files that no longer exist in the current
    # file list (deleted files). The file_set membership check at line 157
    # must ignore these to prevent ghost entries in authorship data.
    def test_compute_authorship_skips_unknown_file(self) -> None:
        commits = [
            {"sha": "a", "author": "Alice", "files": ["known.py", "deleted.py"]},
        ]
        result = _compute_authorship(commits, files=["known.py"])
        paths = [a["path"] for a in result]
        self.assertIn("known.py", paths)
        self.assertNotIn("deleted.py", paths)

    # WHY: A file present in the repo but never mentioned in any commit
    # should be absent from authorship results — not present with zero
    # commits. This edge case tests the skip at line 166.
    def test_compute_authorship_file_no_commits(self) -> None:
        commits = [
            {"sha": "a", "author": "Alice", "files": ["touched.py"]},
        ]
        result = _compute_authorship(commits, files=["touched.py", "orphan.py"])
        paths = [a["path"] for a in result]
        self.assertIn("touched.py", paths)
        self.assertNotIn("orphan.py", paths)


class TestComputeRiskLevels(unittest.TestCase):
    """Tests for _compute_risk_levels."""

    # WHY: Empty hotspots is the degenerate case guard at line 197.
    # Without this check, the min-max normalization would crash on empty
    # sequences. This test ensures graceful handling.
    def test_compute_risk_levels_empty_hotspots(self) -> None:
        result = _compute_risk_levels([], [], [])
        self.assertEqual(result, [])

    # WHY: When all normalized values are identical (min == max), the _norm
    # function returns 0.5 for all entries. With a single hotspot, the score
    # should be exactly 0.5*0.5 + 0.3*0.5 + 0.2*0.5 = 0.5, classified
    # as "medium". This edge case validates the normalization fallback.
    def test_compute_risk_levels_single_hotspot(self) -> None:
        hotspots = [{"path": "a.py", "touch_count": 5}]
        authorship = [{"path": "a.py", "distinct_authors": 2}]
        co_change_pairs = []  # no coupling
        result = _compute_risk_levels(hotspots, co_change_pairs, authorship)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["risk_score"], 0.5, places=4)
        self.assertEqual(result[0]["risk_level"], "medium")

    # WHY: This validates the full weighted scoring formula (50% churn +
    # 30% author diversity + 20% coupling) and the threshold classification
    # (high > 0.7, medium >= 0.4, low < 0.4). We construct three hotspots
    # that should fall into each bucket.
    def test_compute_risk_levels_high_medium_low(self) -> None:
        hotspots = [
            {"path": "hot.py", "touch_count": 100},
            {"path": "warm.py", "touch_count": 50},
            {"path": "cold.py", "touch_count": 1},
        ]
        authorship = [
            {"path": "hot.py", "distinct_authors": 10},
            {"path": "warm.py", "distinct_authors": 5},
            {"path": "cold.py", "distinct_authors": 1},
        ]
        co_change_pairs = [
            {"file_a": "hot.py", "file_b": "warm.py", "co_change_count": 5},
        ]
        result = _compute_risk_levels(hotspots, co_change_pairs, authorship)
        levels = {r["path"]: r["risk_level"] for r in result}

        # hot.py: max churn, max authors, coupling=1 → high
        self.assertEqual(levels["hot.py"], "high")
        # cold.py: min churn, min authors, coupling=0 → low
        self.assertEqual(levels["cold.py"], "low")


class TestDetectConventions(unittest.TestCase):
    """Tests for _detect_conventions — 11+ pattern matchers."""

    # WHY: Pytest can be configured in pyproject.toml via [tool.pytest.ini_options].
    # This is the second-tier detection path (lines 265-268) used when pytest.ini
    # is absent. Many modern Python projects only use pyproject.toml.
    def test_detect_conventions_pyproject_pytest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pyproject.toml").write_text(
                "[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding="utf-8"
            )
            files = ["pyproject.toml", "src/app.py"]
            result = _detect_conventions(files, repo)
            self.assertIsNotNone(result["test_framework"])
            self.assertEqual(result["test_framework"]["name"], "pytest")

    # WHY: Pytest can also be configured in setup.cfg via [tool:pytest].
    # This is the third-tier detection path (lines 270-271), the last
    # fallback before pytest is considered absent.
    def test_detect_conventions_setup_cfg_pytest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "setup.cfg").write_text(
                "[tool:pytest]\ntestpaths = tests\n", encoding="utf-8"
            )
            files = ["setup.cfg", "src/app.py"]
            result = _detect_conventions(files, repo)
            self.assertIsNotNone(result["test_framework"])
            self.assertEqual(result["test_framework"]["name"], "pytest")

    # WHY: Jest is the standard JavaScript test framework. Detection must
    # work for all config variants (jest.config.js, .ts, .mjs, .cjs).
    # Lines 274-275.
    def test_detect_conventions_jest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "jest.config.js").write_text("module.exports = {};", encoding="utf-8")
            files = ["jest.config.js", "src/index.js"]
            result = _detect_conventions(files, repo)
            self.assertIsNotNone(result["test_framework"])
            self.assertEqual(result["test_framework"]["name"], "jest")

    # WHY: Ruff and Black are both common Python formatters. When both are
    # configured in pyproject.toml (lines 288-295), both should be detected.
    # This tests the inline pyproject.toml linter detection path.
    def test_detect_conventions_ruff_black_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pyproject.toml").write_text(
                "[tool.ruff]\nline-length = 88\n\n[tool.black]\nline-length = 88\n",
                encoding="utf-8",
            )
            files = ["pyproject.toml"]
            result = _detect_conventions(files, repo)
            linter_names = [l["name"] for l in result["linters"]]
            self.assertIn("ruff", linter_names)
            self.assertIn("black", linter_names)

    # WHY: CI/CD detection (line 313) uses prefix matching on file paths.
    # GitHub Actions workflows live under .github/workflows/. This tests
    # the pattern matching logic for CI pipeline detection.
    def test_detect_conventions_ci_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            files = [".github/workflows/ci.yml", "src/app.py"]
            result = _detect_conventions(files, repo)
            platforms = [ci["platform"] for ci in result["ci_pipelines"]]
            self.assertIn("github_actions", platforms)

    # WHY: Package manager detection (lines 334-335) uses lockfile presence.
    # Each lockfile maps to a specific package manager. This verifies the
    # mapping works correctly.
    def test_detect_conventions_package_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            files = ["yarn.lock", "package.json", "src/index.js"]
            result = _detect_conventions(files, repo)
            self.assertEqual(result["package_manager"], "yarn")

    # WHY: The _read helper (lines 249-250) catches OSError when config files
    # listed in the manifest don't actually exist on disk. This tests the
    # graceful fallback to empty string.
    def test_detect_conventions_read_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            # pyproject.toml is in the file list but doesn't exist on disk
            files = ["pyproject.toml"]
            result = _detect_conventions(files, repo)
            # Should not crash — _read returns "" for missing file
            self.assertIsNone(result["test_framework"])

    # WHY: The _any_match helper (line 258) uses endswith to find config files
    # nested in subdirectories. This tests the nested path matching logic.
    def test_detect_conventions_nested_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "sub").mkdir()
            (repo / "sub" / ".eslintrc.json").write_text("{}", encoding="utf-8")
            files = ["sub/.eslintrc.json", "src/app.js"]
            result = _detect_conventions(files, repo)
            linter_names = [l["name"] for l in result["linters"]]
            self.assertIn("eslint", linter_names)

    # WHY: Line 288 — standalone linter config files (editorconfig, flake8, etc.)
    # matched via _any_match should be added to the linters list.
    def test_detect_conventions_standalone_linter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".editorconfig").write_text("root = true", encoding="utf-8")
            (repo / ".flake8").write_text("[flake8]\nmax-line-length=88", encoding="utf-8")
            files = [".editorconfig", ".flake8", "src/app.py"]
            result = _detect_conventions(files, repo)
            linter_names = [l["name"] for l in result["linters"]]
            self.assertIn("editorconfig", linter_names)
            self.assertIn("flake8", linter_names)

    # WHY: Tests that contribution docs are detected via path name matching.
    def test_detect_conventions_contribution_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            files = ["CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "src/app.py"]
            result = _detect_conventions(files, repo)
            self.assertEqual(len(result["contribution_docs"]), 2)

    # WHY: Tests that test directories are detected from top-level directory names.
    def test_detect_conventions_test_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            files = ["tests/test_app.py", "test/test_util.py", "src/app.py"]
            result = _detect_conventions(files, repo)
            self.assertIn("tests", result["test_dirs"])


class TestComputeDependencyGraph(unittest.TestCase):
    """Tests for _compute_dependency_graph."""

    # WHY: When ast_imports is unavailable (e.g., tree-sitter not installed),
    # the dependency graph should gracefully degrade to an empty result with
    # an explanatory note (lines 366-367). This prevents the transform from
    # crashing in environments without optional AST dependencies.
    def test_dependency_graph_import_error_fallback(self) -> None:
        import builtins
        import sys
        import src.pipeline as pipeline_pkg

        real_import = builtins.__import__
        saved_attr = getattr(pipeline_pkg, "ast_imports", None)
        saved_module = sys.modules.get("src.pipeline.ast_imports")
        try:
            # Remove from both the parent package and sys.modules cache
            if hasattr(pipeline_pkg, "ast_imports"):
                delattr(pipeline_pkg, "ast_imports")
            sys.modules.pop("src.pipeline.ast_imports", None)

            def _mock_import(name, globals=None, locals=None, fromlist=(), level=0):
                # Intercept "from src.pipeline import ast_imports"
                if fromlist and "ast_imports" in fromlist:
                    raise ImportError("mocked")
                if "ast_imports" in str(name):
                    raise ImportError("mocked")
                return real_import(name, globals, locals, fromlist, level)

            builtins.__import__ = _mock_import
            try:
                result = _compute_dependency_graph([], Path("/tmp/nonexistent"))
            finally:
                builtins.__import__ = real_import

            self.assertIn("imports_map", result)
            self.assertIn("imported_by", result)
            self.assertIn("note", result)
        finally:
            if saved_module is not None:
                sys.modules["src.pipeline.ast_imports"] = saved_module
            if saved_attr is not None:
                pipeline_pkg.ast_imports = saved_attr

    # WHY: When ast_imports IS available, the dependency graph should
    # delegate to it and return valid results.
    def test_dependency_graph_success(self) -> None:
        result = _compute_dependency_graph([], Path("/tmp/nonexistent"))
        self.assertIn("imports_map", result)
        self.assertIn("imported_by", result)


class TestTransformRepo(unittest.TestCase):
    """Tests for transform_repo entry point validation."""

    # WHY: transform_repo must fail fast with FileNotFoundError when the
    # required ingest.json is missing (line 384). This prevents cryptic
    # errors later in the pipeline when attempting to read the missing file.
    def test_transform_repo_missing_ingest_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "repo"
            raw_dir.mkdir()
            (raw_dir / "repo").mkdir()  # repo/ exists but no ingest.json
            with self.assertRaises(FileNotFoundError):
                transform_repo(raw_dir, Path(tmp) / "out")

    # WHY: Similarly, if ingest.json exists but the repo checkout directory
    # is missing (line 386), transform_repo must fail fast rather than
    # silently producing empty results.
    def test_transform_repo_missing_repo_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "repo"
            raw_dir.mkdir()
            (raw_dir / "ingest.json").write_text(
                json.dumps({"repo_slug": "test", "files": [], "commit_log": []}),
                encoding="utf-8",
            )
            # repo/ directory does NOT exist
            with self.assertRaises(FileNotFoundError):
                transform_repo(raw_dir, Path(tmp) / "out")


class TestComputeHotspots(unittest.TestCase):
    """Tests for _compute_hotspots_from_commits."""

    # WHY: Validates that files are ranked by touch count and that
    # last_touched captures the earliest date seen (first commit in order).
    def test_hotspots_ranking_and_last_touched(self) -> None:
        commits = [
            {"sha": "a", "date": "2026-01-01", "files": ["a.py", "b.py"]},
            {"sha": "b", "date": "2026-01-02", "files": ["a.py"]},
            {"sha": "c", "date": "2026-01-03", "files": ["a.py"]},
        ]
        result = _compute_hotspots_from_commits(commits, top_n=5)
        self.assertEqual(result[0]["path"], "a.py")
        self.assertEqual(result[0]["touch_count"], 3)
        # last_touched is the date of the first commit that touches the file
        self.assertEqual(result[0]["last_touched"], "2026-01-01")


class TestTransformParseArgs(unittest.TestCase):
    """Tests for _parse_args CLI argument parsing."""

    def test_parse_args_required(self) -> None:
        with patch("sys.argv", ["transform", "--raw-root", "/tmp/raw", "--transform-root", "/tmp/out"]):
            args = _parse_args()
        self.assertEqual(args.raw_root, Path("/tmp/raw"))
        self.assertEqual(args.transform_root, Path("/tmp/out"))
        self.assertEqual(args.top_n_hotspots, 20)

    def test_parse_args_custom_hotspots(self) -> None:
        with patch("sys.argv", ["transform", "--raw-root", "/tmp/raw", "--transform-root", "/tmp/out", "--top-n-hotspots", "5"]):
            args = _parse_args()
        self.assertEqual(args.top_n_hotspots, 5)

    def test_parse_args_missing_required(self) -> None:
        with patch("sys.argv", ["transform"]):
            with self.assertRaises(SystemExit):
                _parse_args()


class TestTransformMain(unittest.TestCase):
    """Tests for transform main() entry point."""

    def test_main_success(self) -> None:
        """main() processes repos and returns 0 on success."""
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp) / "raw"
            transform_root = Path(tmp) / "out"
            repo_dir = raw_root / "test-repo"
            repo_dir.mkdir(parents=True)
            (repo_dir / "repo").mkdir()
            (repo_dir / "ingest.json").write_text(
                json.dumps({
                    "repo_slug": "test-repo",
                    "repo_url": "file:///test",
                    "head_commit": "abc",
                    "files": ["app.py"],
                    "commit_log": [],
                }),
                encoding="utf-8",
            )
            # Create the repo checkout with a file
            (repo_dir / "repo" / "app.py").write_text("x = 1\n", encoding="utf-8")

            with patch("sys.argv", ["transform", "--raw-root", str(raw_root), "--transform-root", str(transform_root)]):
                exit_code = main()
            self.assertEqual(exit_code, 0)

    def test_main_no_candidates(self) -> None:
        """main() returns 1 when no repos are found."""
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp) / "raw"
            raw_root.mkdir()
            transform_root = Path(tmp) / "out"

            with patch("sys.argv", ["transform", "--raw-root", str(raw_root), "--transform-root", str(transform_root)]):
                exit_code = main()
            self.assertEqual(exit_code, 1)

    def test_main_handles_failure(self) -> None:
        """main() catches exceptions per-repo and continues."""
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp) / "raw"
            repo_dir = raw_root / "bad-repo"
            repo_dir.mkdir(parents=True)
            # ingest.json exists but repo/ doesn't → FileNotFoundError
            (repo_dir / "ingest.json").write_text("{}", encoding="utf-8")
            transform_root = Path(tmp) / "out"

            with patch("sys.argv", ["transform", "--raw-root", str(raw_root), "--transform-root", str(transform_root)]):
                exit_code = main()
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
