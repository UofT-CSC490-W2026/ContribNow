from __future__ import annotations

from pathlib import Path

from src.pipeline.chunking.interfaces import LanguageRegistry


class DefaultLanguageRegistry(LanguageRegistry):
    """
    Resolve canonical language ids from filename, extension, and shebang.
    """

    def __init__(self) -> None:
        self._extension_to_language = {
            ".py": "python",
            ".pyi": "python",
            ".js": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".jsx": "jsx",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "shell",
            ".bash": "shell",
            ".zsh": "shell",
            ".sql": "sql",
            ".tf": "hcl",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".md": "markdown",
        }
        self._name_to_language = {
            "Dockerfile": "dockerfile",
            "Makefile": "makefile",
            "CMakeLists.txt": "cmake",
        }

    def detect(self, file_path: str, content_head: str | None = None) -> str | None:
        path = Path(file_path)
        base_name = path.name

        if base_name in self._name_to_language:
            return self._name_to_language[base_name]

        suffix = path.suffix.lower()
        if suffix in self._extension_to_language:
            return self._extension_to_language[suffix]

        if content_head:
            first_line = (
                content_head.splitlines()[0] if content_head.splitlines() else ""
            )
            if first_line.startswith("#!"):
                return self._detect_from_shebang(first_line)

        return None

    def _detect_from_shebang(self, first_line: str) -> str | None:
        if "python" in first_line:
            return "python"
        if "bash" in first_line or "sh" in first_line or "zsh" in first_line:
            return "shell"
        if "node" in first_line:
            return "javascript"
        return None
