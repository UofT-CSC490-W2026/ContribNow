import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from src.pipeline.chunking import (
    ChunkingConfig,
    FileChunkRequest,
    TSGoChunkingStrategy,
    TSJavaChunkingStrategy,
    TSJavaScriptChunkingStrategy,
    TSJSXChunkingStrategy,
    TSTypeScriptChunkingStrategy,
)


@dataclass
class _FakeNode:
    type: str
    start_byte: int
    end_byte: int
    children: list["_FakeNode"] = field(default_factory=list)


@dataclass
class _FakeTree:
    root_node: _FakeNode


class _FakeParser:
    def __init__(self, root_node: _FakeNode) -> None:
        self._tree = _FakeTree(root_node=root_node)

    def parse(self, source_bytes: bytes) -> _FakeTree:
        return self._tree


class TestTSCodeChunking(unittest.TestCase):
    def test_semantic_javascript_chunking(self) -> None:
        content = (
            "import x from 'x'\n\n"
            "function run() {\n  return 1;\n}\n\n"
            "class App {\n  start() {}\n}\n"
        )
        source = content.encode("utf-8")
        fn_start = source.index(b"function run")
        class_start = source.index(b"class App")

        root = _FakeNode(
            type="program",
            start_byte=0,
            end_byte=len(source),
            children=[
                _FakeNode(type="import_statement", start_byte=0, end_byte=fn_start),
                _FakeNode(
                    type="function_declaration",
                    start_byte=fn_start,
                    end_byte=class_start,
                ),
                _FakeNode(
                    type="class_declaration",
                    start_byte=class_start,
                    end_byte=len(source),
                ),
            ],
        )
        parser = _FakeParser(root)

        with patch.object(
            TSJavaScriptChunkingStrategy, "_build_parser", return_value=parser
        ):
            strategy = TSJavaScriptChunkingStrategy()

        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo", file_path="pkg/main.js", content=source
            ),
            language="javascript",
            config=ChunkingConfig(max_bytes=90, overlap_bytes=15, min_split_bytes=30),
        )

        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunk.strategy == "ts_javascript" for chunk in chunks))
        joined = b"\n".join(chunk.content for chunk in chunks).decode(
            "utf-8", errors="replace"
        )
        self.assertIn("function run", joined)
        self.assertIn("class App", joined)

    def test_semantic_java_chunking(self) -> None:
        content = (
            "package demo;\n\nclass Util {\n  Util() {}\n  int one() { return 1; }\n}\n"
        )
        source = content.encode("utf-8")
        class_start = source.index(b"class Util")

        root = _FakeNode(
            type="program",
            start_byte=0,
            end_byte=len(source),
            children=[
                _FakeNode(
                    type="package_declaration", start_byte=0, end_byte=class_start
                ),
                _FakeNode(
                    type="class_declaration",
                    start_byte=class_start,
                    end_byte=len(source),
                ),
            ],
        )
        parser = _FakeParser(root)

        with patch.object(TSJavaChunkingStrategy, "_build_parser", return_value=parser):
            strategy = TSJavaChunkingStrategy()

        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo", file_path="src/Util.java", content=source
            ),
            language="java",
            config=ChunkingConfig(max_bytes=85, overlap_bytes=12, min_split_bytes=25),
        )

        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(all(chunk.strategy == "ts_java" for chunk in chunks))
        joined = b"\n".join(chunk.content for chunk in chunks).decode(
            "utf-8", errors="replace"
        )
        self.assertIn("class Util", joined)

    def test_semantic_jsx_chunking(self) -> None:
        content = "function View() { return <div />; }\n"
        source = content.encode("utf-8")
        root = _FakeNode(
            type="program",
            start_byte=0,
            end_byte=len(source),
            children=[
                _FakeNode(
                    type="function_declaration", start_byte=0, end_byte=len(source)
                )
            ],
        )
        parser = _FakeParser(root)

        with patch.object(TSJSXChunkingStrategy, "_build_parser", return_value=parser):
            strategy = TSJSXChunkingStrategy()

        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo", file_path="src/View.jsx", content=source
            ),
            language="jsx",
            config=ChunkingConfig(max_bytes=80, overlap_bytes=10, min_split_bytes=20),
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].strategy, "ts_jsx")

    def test_semantic_typescript_chunking(self) -> None:
        content = (
            "type User = { id: string }\n\n"
            "interface Repository { getById(id: string): User }\n\n"
            "class Service {}\n"
        )
        source = content.encode("utf-8")
        interface_start = source.index(b"interface Repository")
        class_start = source.index(b"class Service")

        root = _FakeNode(
            type="program",
            start_byte=0,
            end_byte=len(source),
            children=[
                _FakeNode(
                    type="type_alias_declaration",
                    start_byte=0,
                    end_byte=interface_start,
                ),
                _FakeNode(
                    type="interface_declaration",
                    start_byte=interface_start,
                    end_byte=class_start,
                ),
                _FakeNode(
                    type="class_declaration",
                    start_byte=class_start,
                    end_byte=len(source),
                ),
            ],
        )
        parser = _FakeParser(root)

        with patch.object(
            TSTypeScriptChunkingStrategy, "_build_parser", return_value=parser
        ):
            strategy = TSTypeScriptChunkingStrategy()

        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo", file_path="src/service.ts", content=source
            ),
            language="typescript",
            config=ChunkingConfig(max_bytes=85, overlap_bytes=12, min_split_bytes=25),
        )

        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunk.strategy == "ts_typescript" for chunk in chunks))
        joined = b"\n".join(chunk.content for chunk in chunks).decode(
            "utf-8", errors="replace"
        )
        self.assertIn("interface Repository", joined)
        self.assertIn("class Service", joined)

    def test_semantic_go_chunking(self) -> None:
        content = (
            "package service\n\n"
            "type Repo struct {}\n\n"
            "func NewRepo() Repo { return Repo{} }\n"
        )
        source = content.encode("utf-8")
        type_start = source.index(b"type Repo")
        func_start = source.index(b"func NewRepo")

        root = _FakeNode(
            type="source_file",
            start_byte=0,
            end_byte=len(source),
            children=[
                _FakeNode(type="package_clause", start_byte=0, end_byte=type_start),
                _FakeNode(
                    type="type_declaration",
                    start_byte=type_start,
                    end_byte=func_start,
                ),
                _FakeNode(
                    type="function_declaration",
                    start_byte=func_start,
                    end_byte=len(source),
                ),
            ],
        )
        parser = _FakeParser(root)

        with patch.object(TSGoChunkingStrategy, "_build_parser", return_value=parser):
            strategy = TSGoChunkingStrategy()

        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo", file_path="src/repo.go", content=source
            ),
            language="go",
            config=ChunkingConfig(max_bytes=80, overlap_bytes=10, min_split_bytes=20),
        )

        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(all(chunk.strategy == "ts_go" for chunk in chunks))
        joined = b"\n".join(chunk.content for chunk in chunks).decode(
            "utf-8", errors="replace"
        )
        self.assertIn("func NewRepo", joined)

    def test_rejects_language_mismatch(self) -> None:
        parser = _FakeParser(_FakeNode(type="program", start_byte=0, end_byte=1))
        with patch.object(
            TSJavaScriptChunkingStrategy, "_build_parser", return_value=parser
        ):
            strategy = TSJavaScriptChunkingStrategy()

        with self.assertRaises(ValueError):
            strategy.chunk(
                request=FileChunkRequest(
                    repo_slug="repo", file_path="pkg/main.js", content=b"x\n"
                ),
                language="java",
                config=ChunkingConfig(
                    max_bytes=60, overlap_bytes=10, min_split_bytes=20
                ),
            )


if __name__ == "__main__":
    unittest.main()
