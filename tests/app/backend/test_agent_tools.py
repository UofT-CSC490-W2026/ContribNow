import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.backend.agent.agent import run_local_tool
from app.backend.agent.tools import build_tool_definitions


class TestAgentTools(unittest.TestCase):
    def test_tool_definitions_are_exported_from_tools(self) -> None:
        definitions = build_tool_definitions()

        self.assertEqual(
            [definition["name"] for definition in definitions],
            ["listRepoFiles", "readRepoFile", "searchRepoText"],
        )

    def test_list_repo_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha.txt").write_text("hello", encoding="utf-8")
            (root / "beta.py").write_text("print('x')\n", encoding="utf-8")

            with patch("app.backend.agent.agent.REPO_ROOTS", {"default": root}):
                result = run_local_tool(
                    "listRepoFiles",
                    {"repoSlug": "default", "path": "."},
                )

            self.assertEqual(result.splitlines(), ["alpha.txt", "beta.py"])

    def test_read_repo_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_path = root / "pkg.py"
            file_path.write_text("print('hello')\n", encoding="utf-8")

            with patch("app.backend.agent.agent.REPO_ROOTS", {"default": root}):
                result = run_local_tool(
                    "readRepoFile",
                    {"repoSlug": "default", "path": "pkg.py"},
                )

            self.assertEqual(result, "print('hello')\n")

    def test_search_repo_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pkg.py").write_text("needle = 1\n", encoding="utf-8")
            (root / "notes.txt").write_text("Needle again\n", encoding="utf-8")

            with patch("app.backend.agent.agent.REPO_ROOTS", {"default": root}):
                result = run_local_tool(
                    "searchRepoText",
                    {"repoSlug": "default", "query": "needle"},
                )

            self.assertIn("notes.txt:1: Needle again", result)
            self.assertIn("pkg.py:1: needle = 1", result)
