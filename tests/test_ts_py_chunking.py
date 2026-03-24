import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from src.pipeline.chunking import (
    ChunkingConfig,
    FileChunkRequest,
    TSPyChunkingStrategy,
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


class TestTSPyChunking(unittest.TestCase):
    def test_semantic_python_chunking(self) -> None:
        content = "import os\n\ndef util():\n    return 1\n\nclass Foo:\n    pass\n"
        source = content.encode("utf-8")
        def_start = source.index(b"def util")
        class_start = source.index(b"class Foo")

        root = _FakeNode(
            type="module",
            start_byte=0,
            end_byte=len(source),
            children=[
                _FakeNode(type="import_statement", start_byte=0, end_byte=def_start),
                _FakeNode(
                    type="function_definition",
                    start_byte=def_start,
                    end_byte=class_start,
                ),
                _FakeNode(
                    type="class_definition",
                    start_byte=class_start,
                    end_byte=len(source),
                ),
            ],
        )
        parser = _FakeParser(root)

        with patch(
            "src.pipeline.chunking.ts_py_strategy._build_ts_py_parser",
            return_value=parser,
        ):
            strategy = TSPyChunkingStrategy()
        request = FileChunkRequest(
            repo_slug="repo", file_path="pkg/mod.py", content=content.encode("utf-8")
        )

        chunks = strategy.chunk(
            request=request,
            language="python",
            config=ChunkingConfig(max_bytes=120, overlap_bytes=20, min_split_bytes=40),
        )

        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunk.strategy == "ts_py" for chunk in chunks))
        joined = b"\n".join(chunk.content for chunk in chunks).decode(
            "utf-8", errors="replace"
        )
        self.assertIn("def util", joined)
        self.assertIn("class Foo", joined)

    def test_raises_when_parser_build_fails(self) -> None:
        request = FileChunkRequest(
            repo_slug="repo",
            file_path="pkg/mod.py",
            content=b"def f():\n    return 1\n",
        )

        with patch(
            "src.pipeline.chunking.ts_py_strategy._build_ts_py_parser",
            side_effect=RuntimeError("parser unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                strategy = TSPyChunkingStrategy()
                strategy.chunk(
                    request=request,
                    language="python",
                    config=ChunkingConfig(
                        max_bytes=80, overlap_bytes=10, min_split_bytes=20
                    ),
                )

    def test_rejects_non_python_language(self) -> None:
        parser = _FakeParser(_FakeNode(type="module", start_byte=0, end_byte=1))
        with patch(
            "src.pipeline.chunking.ts_py_strategy._build_ts_py_parser",
            return_value=parser,
        ):
            strategy = TSPyChunkingStrategy()
        request = FileChunkRequest(
            repo_slug="repo",
            file_path="pkg/mod.js",
            content=b"console.log('x')\n",
        )

        with self.assertRaises(ValueError):
            strategy.chunk(
                request=request,
                language="javascript",
                config=ChunkingConfig(
                    max_bytes=80, overlap_bytes=10, min_split_bytes=20
                ),
            )


if __name__ == "__main__":
    unittest.main()
