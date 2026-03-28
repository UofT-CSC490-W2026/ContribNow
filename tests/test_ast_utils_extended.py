"""
Extended tests for ast_utils.py — tree-sitter parser infrastructure.

These tests cover the parser cache, language detection, graceful degradation
when tree-sitter is unavailable, and the parse_file utility.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.pipeline.ast_utils as ast_utils_mod
from src.pipeline.ast_utils import (
    _check_ts_available,
    get_parser,
    language_for_file,
    parse_file,
)


class TestLanguageForFile(unittest.TestCase):
    """Tests for language_for_file (already covered but included for completeness)."""

    def test_python(self) -> None:
        self.assertEqual(language_for_file("app.py"), "python")

    def test_typescript(self) -> None:
        self.assertEqual(language_for_file("app.ts"), "typescript")

    def test_unsupported(self) -> None:
        self.assertIsNone(language_for_file("app.rb"))


class TestCheckTsAvailable(unittest.TestCase):
    """Tests for _check_ts_available."""

    def test_ts_unavailable(self) -> None:
        """When tree-sitter import fails → returns False."""
        saved_ts = ast_utils_mod._TS_AVAILABLE
        saved_cache = ast_utils_mod._parser_cache.copy()
        try:
            ast_utils_mod._TS_AVAILABLE = None  # reset to force re-check
            with patch.dict("sys.modules", {"tree_sitter": None}):
                result = _check_ts_available()
            self.assertFalse(result)
        finally:
            ast_utils_mod._TS_AVAILABLE = saved_ts
            ast_utils_mod._parser_cache = saved_cache

    def test_ts_available(self) -> None:
        """When tree-sitter is installed → returns True."""
        saved_ts = ast_utils_mod._TS_AVAILABLE
        try:
            ast_utils_mod._TS_AVAILABLE = None  # force re-check
            result = _check_ts_available()
            self.assertTrue(result)
        finally:
            ast_utils_mod._TS_AVAILABLE = saved_ts


class TestGetParser(unittest.TestCase):
    """Tests for get_parser."""

    def test_get_parser_ts_unavailable(self) -> None:
        """When tree-sitter is unavailable → returns None."""
        saved_ts = ast_utils_mod._TS_AVAILABLE
        saved_cache = ast_utils_mod._parser_cache.copy()
        try:
            ast_utils_mod._TS_AVAILABLE = False
            ast_utils_mod._parser_cache = {}
            result = get_parser("python")
            self.assertIsNone(result)
        finally:
            ast_utils_mod._TS_AVAILABLE = saved_ts
            ast_utils_mod._parser_cache = saved_cache

    def test_get_parser_javascript(self) -> None:
        """JavaScript parser → returns a parser object."""
        parser = get_parser("javascript")
        self.assertIsNotNone(parser)

    def test_get_parser_java(self) -> None:
        """Java parser → returns a parser object."""
        parser = get_parser("java")
        self.assertIsNotNone(parser)

    def test_get_parser_unsupported_language(self) -> None:
        """Unsupported language (e.g. 'rust') → returns None."""
        saved_cache = ast_utils_mod._parser_cache.copy()
        try:
            result = get_parser("rust")
            self.assertIsNone(result)
        finally:
            ast_utils_mod._parser_cache = saved_cache

    def test_get_parser_import_error(self) -> None:
        """Grammar import fails → returns None."""
        saved_ts = ast_utils_mod._TS_AVAILABLE
        saved_cache = ast_utils_mod._parser_cache.copy()
        try:
            ast_utils_mod._TS_AVAILABLE = True
            ast_utils_mod._parser_cache = {}
            with patch.dict(
                "sys.modules",
                {"tree_sitter_python": None},
            ):
                result = get_parser("python")
            self.assertIsNone(result)
        finally:
            ast_utils_mod._TS_AVAILABLE = saved_ts
            ast_utils_mod._parser_cache = saved_cache

    def test_get_parser_caches_result(self) -> None:
        """Second call returns cached parser."""
        p1 = get_parser("python")
        p2 = get_parser("python")
        self.assertIs(p1, p2)


class TestParseFile(unittest.TestCase):
    """Tests for parse_file."""

    def test_parse_file_success(self) -> None:
        """Valid Python file → returns a tree object."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.py"
            f.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")
            tree = parse_file(f, "python")
            self.assertIsNotNone(tree)

    def test_parse_file_parser_unavailable(self) -> None:
        """Parser returns None → parse_file returns None."""
        with patch("src.pipeline.ast_utils.get_parser", return_value=None):
            result = parse_file(Path("/tmp/test.py"), "python")
        self.assertIsNone(result)

    def test_parse_file_unreadable(self) -> None:
        """Non-existent file → returns None (OSError caught)."""
        result = parse_file(Path("/nonexistent/test.py"), "python")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
