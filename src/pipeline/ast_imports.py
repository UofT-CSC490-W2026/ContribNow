"""
AST-based import/export extraction for building a dependency graph.

Supports Python, JavaScript/TypeScript, and Java via tree-sitter grammars.
Falls back to lightweight regex extraction for unsupported languages or when
tree-sitter is not installed.

Public entry point used by transform.py:
    build_dependency_graph(files, repo_checkout) -> {imports_map, imported_by}
"""
from __future__ import annotations

import re
from pathlib import Path

from src.pipeline.ast_utils import language_for_file, parse_file

# ---------------------------------------------------------------------------
# Per-language AST extractors
# ---------------------------------------------------------------------------

_MAX_FILE_SIZE = 1 * 1024 * 1024  # skip files larger than 1 MB


def _extract_python_imports_ast(tree: object, source: bytes) -> list[str]:
    """Walk a Python AST and collect imported module names."""
    imports: list[str] = []

    def walk(node: object) -> None:
        node_type: str = node.type  # type: ignore[attr-defined]
        children: list[object] = node.children  # type: ignore[attr-defined]

        if node_type == "import_statement":
            # import a, import a.b.c, import a as x
            for child in children:
                if child.type == "dotted_name":  # type: ignore[attr-defined]
                    imports.append(source[child.start_byte:child.end_byte].decode("utf-8", errors="replace"))  # type: ignore[attr-defined]
                elif child.type == "aliased_import":  # type: ignore[attr-defined]
                    for subchild in child.children:  # type: ignore[attr-defined]
                        if subchild.type == "dotted_name":  # type: ignore[attr-defined]
                            imports.append(source[subchild.start_byte:subchild.end_byte].decode("utf-8", errors="replace"))  # type: ignore[attr-defined]
                            break
        elif node_type == "import_from_statement":
            # from a.b import c, from . import d
            module_parts: list[str] = []
            dots = ""
            for child in children:
                ct: str = child.type  # type: ignore[attr-defined]
                if ct == "relative_import":
                    # relative import — collect dots + optional module
                    for rchild in child.children:  # type: ignore[attr-defined]
                        if rchild.type == "import_prefix":  # type: ignore[attr-defined]
                            dots = source[rchild.start_byte:rchild.end_byte].decode("utf-8", errors="replace")  # type: ignore[attr-defined]
                        elif rchild.type == "dotted_name":  # type: ignore[attr-defined]
                            module_parts.append(source[rchild.start_byte:rchild.end_byte].decode("utf-8", errors="replace"))  # type: ignore[attr-defined]
                elif ct == "dotted_name":
                    module_parts.append(source[child.start_byte:child.end_byte].decode("utf-8", errors="replace"))  # type: ignore[attr-defined]
            if module_parts:
                imports.append(dots + ".".join(module_parts))
            elif dots:
                imports.append(dots)

        for child in children:
            walk(child)

    walk(tree.root_node)  # type: ignore[attr-defined]
    return imports


def _extract_js_imports_ast(tree: object, source: bytes) -> list[str]:
    """Walk a JavaScript/TypeScript AST and collect import/require sources."""
    imports: list[str] = []

    def walk(node: object) -> None:
        node_type: str = node.type  # type: ignore[attr-defined]
        children: list[object] = node.children  # type: ignore[attr-defined]

        if node_type == "import_statement":
            # import X from 'module'  /  import 'module'
            for child in children:
                if child.type in ("string", "string_fragment"):  # type: ignore[attr-defined]
                    raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")  # type: ignore[attr-defined]
                    imports.append(raw.strip("'\""))
        elif node_type == "call_expression":
            # require('module')
            func = children[0] if children else None
            args_node = next((c for c in children if c.type == "arguments"), None)  # type: ignore[attr-defined]
            if (
                func is not None
                and source[func.start_byte:func.end_byte] == b"require"  # type: ignore[attr-defined]
                and args_node is not None
            ):
                for arg in args_node.children:  # type: ignore[attr-defined]
                    if arg.type == "string":  # type: ignore[attr-defined]
                        raw = source[arg.start_byte:arg.end_byte].decode("utf-8", errors="replace")  # type: ignore[attr-defined]
                        imports.append(raw.strip("'\""))

        for child in children:
            walk(child)

    walk(tree.root_node)  # type: ignore[attr-defined]
    return imports


def _extract_java_imports_ast(tree: object, source: bytes) -> list[str]:
    """Walk a Java AST and collect import declaration names."""
    imports: list[str] = []

    def walk(node: object) -> None:
        if node.type == "import_declaration":  # type: ignore[attr-defined]
            # Collect the full dotted name
            for child in node.children:  # type: ignore[attr-defined]
                if child.type in ("scoped_identifier", "identifier"):  # type: ignore[attr-defined]
                    imports.append(
                        source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")  # type: ignore[attr-defined]
                    )
        for child in node.children:  # type: ignore[attr-defined]
            walk(child)

    walk(tree.root_node)  # type: ignore[attr-defined]
    return imports


# ---------------------------------------------------------------------------
# Regex fallback extractors (no tree-sitter required)
# ---------------------------------------------------------------------------

_PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.,\s]+))",
    re.MULTILINE,
)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)
_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+(?:\.\*)?)\s*;", re.MULTILINE)


def _extract_imports_regex(file_path: Path, language: str) -> list[str]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if language == "python":
        return [m.group(1) or m.group(2).strip() for m in _PY_IMPORT_RE.finditer(text)]
    if language in ("javascript", "typescript"):
        return [m.group(1) or m.group(2) for m in _JS_IMPORT_RE.finditer(text)]
    if language == "java":
        return [m.group(1) for m in _JAVA_IMPORT_RE.finditer(text)]
    return []


# ---------------------------------------------------------------------------
# Per-file extraction dispatcher
# ---------------------------------------------------------------------------

def extract_imports(file_path: str | Path) -> list[str]:
    """
    Return a list of imported module/path names for *file_path*.

    Tries AST-based extraction first; falls back to regex if tree-sitter is
    unavailable or parsing fails.
    """
    fp = Path(file_path)
    language = language_for_file(fp)
    if language is None:
        return []

    try:
        size = fp.stat().st_size
    except OSError:
        return []
    if size > _MAX_FILE_SIZE:
        return []

    # Try AST
    tree = parse_file(fp, language)
    if tree is not None:
        try:
            source = fp.read_bytes()
            if language == "python":
                return _extract_python_imports_ast(tree, source)
            if language in ("javascript", "typescript"):
                return _extract_js_imports_ast(tree, source)
            if language == "java":
                return _extract_java_imports_ast(tree, source)
        except Exception:
            pass  # fall through to regex

    # Regex fallback
    return _extract_imports_regex(fp, language)


# ---------------------------------------------------------------------------
# Dependency graph builder (called from transform.py)
# ---------------------------------------------------------------------------

def _resolve_relative_python_import(importing_file: str, module: str) -> str | None:
    """
    Attempt to resolve a relative Python import (leading dots) to a file path
    relative to the repo root. Returns None if it cannot be resolved.
    """
    if not module.startswith("."):
        return None
    dots = len(module) - len(module.lstrip("."))
    remainder = module.lstrip(".")
    parts = Path(importing_file).parent.parts
    if dots > len(parts):
        return None
    base_parts = parts[:len(parts) - (dots - 1)]
    if remainder:
        resolved = "/".join(base_parts) + "/" + remainder.replace(".", "/")
    else:
        resolved = "/".join(base_parts)
    return resolved


def build_dependency_graph(
    files: list[str], repo_checkout: Path
) -> dict[str, object]:
    """
    Build an import dependency graph for all supported source files.

    Returns:
        imports_map  — {file_path: [imported_module_or_path, ...]}
        imported_by  — reverse index: {module_or_file: [importing_file, ...]}
    """
    imports_map: dict[str, list[str]] = {}
    imported_by: dict[str, list[str]] = {}

    supported_files = [f for f in files if language_for_file(f) is not None]

    for rel_path in supported_files:
        full_path = repo_checkout / rel_path
        raw_imports = extract_imports(full_path)
        if not raw_imports:
            continue

        imports_map[rel_path] = raw_imports

        for imp in raw_imports:
            # Try to resolve relative Python imports to actual repo files
            resolved = _resolve_relative_python_import(rel_path, imp)
            key = resolved if resolved else imp
            if key not in imported_by:
                imported_by[key] = []
            imported_by[key].append(rel_path)

    return {
        "imports_map": imports_map,
        "imported_by": imported_by,
    }
