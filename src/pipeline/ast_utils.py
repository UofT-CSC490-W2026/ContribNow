"""
Shared tree-sitter infrastructure for AST-based code analysis.

This module is used by both ast_imports (dependency graph) and by the
chunking/embedding pipeline. It handles language detection, parser setup,
and graceful degradation when tree-sitter is not installed.

Install the optional [ast] extra to enable:
    pip install "contribnow[ast]"
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Language detection by file extension
# ---------------------------------------------------------------------------

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
}


def language_for_file(file_path: str | Path) -> str | None:
    """Return the tree-sitter language name for *file_path*, or None if unsupported."""
    return _EXTENSION_TO_LANGUAGE.get(Path(file_path).suffix.lower())


# ---------------------------------------------------------------------------
# Tree-sitter parser factory (lazy, cached)
# ---------------------------------------------------------------------------

_parser_cache: dict[str, object] = {}
_TS_AVAILABLE: bool | None = None  # None = not yet checked


def _check_ts_available() -> bool:
    global _TS_AVAILABLE
    if _TS_AVAILABLE is None:
        try:
            import tree_sitter  # noqa: F401

            _TS_AVAILABLE = True
        except ImportError:
            _TS_AVAILABLE = False
    return bool(_TS_AVAILABLE)


def get_parser(language: str) -> object | None:
    """
    Return a configured tree-sitter Parser for *language*, or None if
    tree-sitter (or the language grammar) is not installed.

    Results are cached so each language's parser is only built once.
    """
    if not _check_ts_available():
        return None

    if language in _parser_cache:
        return _parser_cache[language]

    try:
        from tree_sitter import Language, Parser

        if language == "python":
            import tree_sitter_python as ts_lang  # type: ignore[import]
        elif language in ("javascript", "typescript"):
            # Use the javascript grammar for both JS and TS imports (sufficient for analysis)
            import tree_sitter_javascript as ts_lang  # type: ignore[import]
        elif language == "java":
            import tree_sitter_java as ts_lang  # type: ignore[import]
        else:
            return None

        lang_obj = Language(ts_lang.language())
        parser = Parser(lang_obj)
        _parser_cache[language] = parser
        return parser
    except (ImportError, Exception):
        return None


def parse_file(file_path: str | Path, language: str) -> object | None:
    """
    Parse *file_path* with tree-sitter and return the syntax tree, or None on
    failure (parser unavailable, parse error, or file unreadable).
    """
    parser = get_parser(language)
    if parser is None:
        return None
    try:
        source = Path(file_path).read_bytes()
        tree = parser.parse(source)  # type: ignore[union-attr]
        return tree
    except (OSError, Exception):
        return None
