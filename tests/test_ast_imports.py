"""
Tests for ast_imports.py — AST-based import extraction and dependency graph.

This module has the lowest coverage in the project (45%). Tests use real
tree-sitter parsers (installed as project dependencies) with temp files.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.pipeline.ast_imports import (
    _extract_java_imports_ast,
    _extract_js_imports_ast,
    _extract_python_imports_ast,
    _resolve_relative_python_import,
    build_dependency_graph,
    extract_imports,
)
from src.pipeline.ast_utils import get_parser


class TestExtractPythonImportsAst(unittest.TestCase):
    """Tests for _extract_python_imports_ast using real tree-sitter."""

    def _parse_python(self, code: str):
        parser = get_parser("python")
        self.assertIsNotNone(parser, "tree-sitter-python must be installed")
        source = code.encode("utf-8")
        tree = parser.parse(source)
        return tree, source

    def test_python_import_dotted_name(self) -> None:
        """import os.path → ['os.path']"""
        tree, source = self._parse_python("import os.path\n")
        result = _extract_python_imports_ast(tree, source)
        self.assertIn("os.path", result)

    def test_python_import_aliased(self) -> None:
        """import numpy as np → ['numpy']"""
        tree, source = self._parse_python("import numpy as np\n")
        result = _extract_python_imports_ast(tree, source)
        self.assertIn("numpy", result)

    def test_python_import_multiple(self) -> None:
        """import os, sys → ['os', 'sys']"""
        tree, source = self._parse_python("import os, sys\n")
        result = _extract_python_imports_ast(tree, source)
        self.assertIn("os", result)
        self.assertIn("sys", result)

    def test_python_from_import_absolute(self) -> None:
        """from os.path import join → module name captured."""
        tree, source = self._parse_python("from os.path import join\n")
        result = _extract_python_imports_ast(tree, source)
        self.assertTrue(
            any("os.path" in imp for imp in result), f"Got: {result}"
        )

    def test_python_from_relative_import(self) -> None:
        """from ..utils import helper → ['..utils']"""
        tree, source = self._parse_python("from ..utils import helper\n")
        result = _extract_python_imports_ast(tree, source)
        self.assertTrue(any("utils" in imp for imp in result), f"Got: {result}")

    def test_python_from_dots_only(self) -> None:
        """from . import x → dots-only relative import captured."""
        tree, source = self._parse_python("from . import x\n")
        result = _extract_python_imports_ast(tree, source)
        # Should capture at least the dots or the import name
        self.assertTrue(len(result) > 0, f"Expected non-empty imports, got: {result}")

    def test_python_from_double_dots_only(self) -> None:
        """from .. import y → ['..y'] (dots with module name)"""
        tree, source = self._parse_python("from .. import y\n")
        result = _extract_python_imports_ast(tree, source)
        self.assertTrue(
            any(imp.startswith(".") for imp in result),
            f"Expected dots-prefixed import, got: {result}",
        )

    def test_python_from_dots_wildcard(self) -> None:
        """from . import * → ['.'] (dots only, no dotted_name child).

        This triggers lines 58-59: wildcard_import is not a dotted_name,
        so module_parts is empty but dots is '.'.
        """
        tree, source = self._parse_python("from . import *\n")
        result = _extract_python_imports_ast(tree, source)
        self.assertIn(".", result)

    def test_python_from_double_dots_wildcard(self) -> None:
        """from .. import * → ['..']"""
        tree, source = self._parse_python("from .. import *\n")
        result = _extract_python_imports_ast(tree, source)
        self.assertIn("..", result)


class TestExtractJsImportsAst(unittest.TestCase):
    """Tests for _extract_js_imports_ast using real tree-sitter."""

    def _parse_js(self, code: str):
        parser = get_parser("javascript")
        self.assertIsNotNone(parser, "tree-sitter-javascript must be installed")
        source = code.encode("utf-8")
        tree = parser.parse(source)
        return tree, source

    def test_js_import_statement(self) -> None:
        """import React from 'react' → ['react']"""
        tree, source = self._parse_js("import React from 'react';\n")
        result = _extract_js_imports_ast(tree, source)
        self.assertIn("react", result)

    def test_js_import_bare(self) -> None:
        """import 'polyfill' → ['polyfill']"""
        tree, source = self._parse_js("import 'polyfill';\n")
        result = _extract_js_imports_ast(tree, source)
        self.assertIn("polyfill", result)

    def test_js_require_expression(self) -> None:
        """const fs = require('fs') → ['fs']"""
        tree, source = self._parse_js("const fs = require('fs');\n")
        result = _extract_js_imports_ast(tree, source)
        self.assertIn("fs", result)

    def test_js_import_and_require_combined(self) -> None:
        """File with both import and require → both extracted."""
        code = "import lodash from 'lodash';\nconst path = require('path');\n"
        tree, source = self._parse_js(code)
        result = _extract_js_imports_ast(tree, source)
        self.assertIn("lodash", result)
        self.assertIn("path", result)


class TestExtractJavaImportsAst(unittest.TestCase):
    """Tests for _extract_java_imports_ast using real tree-sitter."""

    def _parse_java(self, code: str):
        parser = get_parser("java")
        self.assertIsNotNone(parser, "tree-sitter-java must be installed")
        source = code.encode("utf-8")
        tree = parser.parse(source)
        return tree, source

    def test_java_import_declaration(self) -> None:
        """import java.util.List; → ['java.util.List']"""
        code = "import java.util.List;\npublic class Foo {}\n"
        tree, source = self._parse_java(code)
        result = _extract_java_imports_ast(tree, source)
        self.assertTrue(
            any("java.util.List" in imp for imp in result), f"Got: {result}"
        )

    def test_java_multiple_imports(self) -> None:
        """Multiple import declarations → all extracted."""
        code = "import java.util.List;\nimport java.io.File;\npublic class Foo {}\n"
        tree, source = self._parse_java(code)
        result = _extract_java_imports_ast(tree, source)
        self.assertTrue(len(result) >= 2, f"Expected >=2 imports, got: {result}")


class TestExtractImports(unittest.TestCase):
    """Tests for the extract_imports dispatcher function."""

    def test_unsupported_language(self) -> None:
        """Unsupported file extension → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "file.rb"
            f.write_text("require 'json'", encoding="utf-8")
            self.assertEqual(extract_imports(f), [])

    def test_oserror_on_stat(self) -> None:
        """Non-existent .py file → empty list (OSError on stat)."""
        result = extract_imports(Path("/nonexistent/path/module.py"))
        self.assertEqual(result, [])

    def test_file_too_large(self) -> None:
        """File larger than 1MB → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "big.py"
            f.write_text("import os\n", encoding="utf-8")
            with patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value = MagicMock(st_size=2 * 1024 * 1024)
                result = extract_imports(f)
            self.assertEqual(result, [])

    def test_oserror_on_read(self) -> None:
        """OSError when reading file bytes → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "unreadable.py"
            f.write_text("import os\n", encoding="utf-8")
            with patch.object(Path, "read_bytes", side_effect=OSError("denied")):
                result = extract_imports(f)
            self.assertEqual(result, [])

    def test_js_prefilter_no_import_keyword(self) -> None:
        """JS file without 'import' or 'require' → empty list (pre-filter)."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plain.js"
            f.write_text("let x = 1;\nconsole.log(x);\n", encoding="utf-8")
            result = extract_imports(f)
            self.assertEqual(result, [])

    def test_java_prefilter_no_import_keyword(self) -> None:
        """Java file without 'import' → empty list (pre-filter)."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "NoImport.java"
            f.write_text("public class NoImport { }\n", encoding="utf-8")
            result = extract_imports(f)
            self.assertEqual(result, [])

    def test_python_prefilter_no_import_keyword(self) -> None:
        """Python file without 'import' or 'from' → empty list (pre-filter)."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "noops.py"
            f.write_text("x = 1\nprint(x)\n", encoding="utf-8")
            result = extract_imports(f)
            self.assertEqual(result, [])

    def test_parser_none(self) -> None:
        """Parser returns None → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.py"
            f.write_text("import os\n", encoding="utf-8")
            with patch("src.pipeline.ast_imports.get_parser", return_value=None):
                result = extract_imports(f)
            self.assertEqual(result, [])

    def test_parse_exception(self) -> None:
        """Parser.parse() raises → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.py"
            f.write_text("import os\n", encoding="utf-8")
            mock_parser = MagicMock()
            mock_parser.parse.side_effect = Exception("parse error")
            with patch("src.pipeline.ast_imports.get_parser", return_value=mock_parser):
                result = extract_imports(f)
            self.assertEqual(result, [])

    def test_dispatches_to_js(self) -> None:
        """Full integration: .js file → JS imports extracted."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "app.js"
            f.write_text("import 'lodash';\n", encoding="utf-8")
            result = extract_imports(f)
            self.assertIn("lodash", result)

    def test_dispatches_to_java(self) -> None:
        """Full integration: .java file → Java imports extracted."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "App.java"
            f.write_text(
                "import java.io.File;\npublic class App {}\n", encoding="utf-8"
            )
            result = extract_imports(f)
            self.assertTrue(len(result) > 0, f"Expected Java imports, got: {result}")

    def test_dispatches_to_typescript(self) -> None:
        """Full integration: .ts file → uses JS parser for imports."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "app.ts"
            f.write_text("import { Component } from 'react';\n", encoding="utf-8")
            result = extract_imports(f)
            self.assertIn("react", result)

    def test_exception_in_extractor(self) -> None:
        """Exception in language-specific extractor → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.py"
            f.write_text("import os\n", encoding="utf-8")
            with patch(
                "src.pipeline.ast_imports._extract_python_imports_ast",
                side_effect=Exception("boom"),
            ):
                result = extract_imports(f)
            self.assertEqual(result, [])


class TestResolveRelativePythonImport(unittest.TestCase):
    """Tests for _resolve_relative_python_import."""

    def test_basic_relative(self) -> None:
        """from .utils import x in src/app.py → 'src/utils'"""
        result = _resolve_relative_python_import("src/app.py", ".utils")
        self.assertEqual(result, "src/utils")

    def test_non_relative_returns_none(self) -> None:
        """Absolute module (no dots) → None."""
        result = _resolve_relative_python_import("src/app.py", "os.path")
        self.assertIsNone(result)

    def test_too_many_dots(self) -> None:
        """More dots than directory depth → None."""
        result = _resolve_relative_python_import("app.py", "....foo")
        self.assertIsNone(result)

    def test_dots_only_no_remainder(self) -> None:
        """from .. import x → resolves to parent directory."""
        result = _resolve_relative_python_import("a/b/c.py", "..")
        self.assertIsNotNone(result)

    def test_double_dot_with_module(self) -> None:
        """from ..utils import x in a/b/c.py → 'a/utils'"""
        result = _resolve_relative_python_import("a/b/c.py", "..utils")
        self.assertEqual(result, "a/utils")


class TestBuildDependencyGraph(unittest.TestCase):
    """Tests for build_dependency_graph."""

    def test_empty_files(self) -> None:
        """No files → empty graph."""
        result = build_dependency_graph([], Path("/tmp"))
        self.assertEqual(result["imports_map"], {})
        self.assertEqual(result["imported_by"], {})

    def test_with_python_files(self) -> None:
        """Python files with imports → populated graph."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "app.py").write_text(
                "from os.path import join\nimport sys\n", encoding="utf-8"
            )
            result = build_dependency_graph(["app.py"], repo)
            self.assertIn("app.py", result["imports_map"])
            self.assertTrue(len(result["imports_map"]["app.py"]) >= 2)


if __name__ == "__main__":
    unittest.main()
