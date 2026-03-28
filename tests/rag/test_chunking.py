import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from src.pipeline.chunking import (
    ChunkingConfig,
    FileChunkRequest,
    NaiveChunkingStrategy,
    TSJavaChunkingStrategy,
    TSJavaScriptChunkingStrategy,
    TSJSXChunkingStrategy,
    TSPyChunkingStrategy,
)
from src.pipeline.chunking.registry import (
    DefaultLanguageRegistry,
    get_language_registry,
    reset_language_registry,
)
from src.pipeline.chunking.strategies import _build_chunk_id, _offset_to_line
from src.pipeline.chunking.ts_base_strategy import (
    BaseTSChunkingStrategy,
    collect_nodes_by_type,
    _semantic_spans_with_gaps,
    _split_byte_span,
)


def randomized_file_name() -> str:
    """
    Return a synthetic path that does not exist in the current workspace.
    """
    root = Path.cwd()
    attempts = 0
    while True:
        attempts += 1
        if attempts > 1000:
            raise RuntimeError("Failed to generate a non-existent randomized file name")
        candidate = f"sandbox/__fixtures__/unit_{uuid4().hex}.zzz"
        if not (root / candidate).exists():
            return candidate


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


class _FakeBytes:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, item):
        if isinstance(item, slice):
            return b""
        return self._data[item]

    def rfind(self, sub: bytes, start: int, end: int) -> int:
        return self._data.rfind(sub, start, end)


class _TestTSStrategy(BaseTSChunkingStrategy):
    language_id = "python"
    strategy_id = "ts_test"
    grammar_module = "fake"

    def __init__(self, parser: _FakeParser, nodes: list[_FakeNode]) -> None:
        self._parser = parser
        self._nodes = nodes

    def _collect_semantic_nodes(self, root: _FakeNode) -> list[_FakeNode]:
        return self._nodes


class _NoCollectStrategy(BaseTSChunkingStrategy):
    language_id = "python"
    strategy_id = "ts_none"
    grammar_module = "fake"

    def __init__(self, parser: _FakeParser) -> None:
        self._parser = parser


class TestChunkingInterfaces(unittest.TestCase):
    def test_chunking_config_validation(self) -> None:
        with self.assertRaises(ValueError):
            ChunkingConfig(max_bytes=0)
        with self.assertRaises(ValueError):
            ChunkingConfig(max_bytes=10, overlap_bytes=-1)
        with self.assertRaises(ValueError):
            ChunkingConfig(max_bytes=100, overlap_bytes=100)
        with self.assertRaises(ValueError):
            ChunkingConfig(max_bytes=100, overlap_bytes=0, min_split_bytes=-1)
        with self.assertRaises(ValueError):
            ChunkingConfig(max_bytes=100, overlap_bytes=0, min_split_bytes=101)


class TestChunkingRegistry(unittest.TestCase):
    def test_detects_by_name_extension_and_shebang(self) -> None:
        registry = DefaultLanguageRegistry()
        self.assertEqual(registry.detect("Dockerfile"), "dockerfile")
        self.assertEqual(registry.detect("src/mod.PY"), "python")
        self.assertEqual(
            registry.detect("bin/run", content_head="#!/usr/bin/env python\nprint(1)\n"),
            "python",
        )
        self.assertEqual(
            registry.detect("bin/run", content_head="#!/usr/bin/env node\n"),
            "javascript",
        )

    def test_register_strategy_validation_and_clear(self) -> None:
        registry = DefaultLanguageRegistry()
        with self.assertRaises(ValueError):
            registry.register_strategy("  ", NaiveChunkingStrategy())
        registry.register_strategy("Python", NaiveChunkingStrategy())
        self.assertIsNotNone(registry.get_strategy("python"))
        registry.clear_strategies()
        self.assertIsNone(registry.get_strategy("python"))

    def test_global_language_registry(self) -> None:
        reset_language_registry()
        registry = get_language_registry()
        self.assertIsInstance(registry, DefaultLanguageRegistry)
        with patch("src.pipeline.chunking.registry._GLOBAL_LANGUAGE_REGISTRY", None):
            registry = get_language_registry()
        self.assertIsInstance(registry, DefaultLanguageRegistry)


class TestNaiveChunking(unittest.TestCase):
    def test_supports_language(self) -> None:
        strategy = NaiveChunkingStrategy()
        self.assertTrue(strategy.supports_language(None))

    def test_returns_empty_for_empty_content(self) -> None:
        strategy = NaiveChunkingStrategy()
        file_name = randomized_file_name()
        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo",
                file_path=file_name,
                content=b"",
            ),
            language="python",
            config=ChunkingConfig(max_bytes=100, overlap_bytes=10, min_split_bytes=20),
        )
        self.assertEqual(chunks, [])

    def test_chunking_uses_overlap(self) -> None:
        strategy = NaiveChunkingStrategy()
        file_name = randomized_file_name()
        text = "".join(f"line-{idx}-abcdefghijklmnopqrstuvwxyz\n" for idx in range(120))
        source = text.encode("utf-8")
        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo",
                file_path=file_name,
                content=source,
            ),
            language="python",
            config=ChunkingConfig(max_bytes=200, overlap_bytes=30, min_split_bytes=80),
        )

        self.assertGreater(len(chunks), 1)
        for idx, chunk in enumerate(chunks):
            self.assertEqual(chunk.strategy, "naive")
            self.assertLess(chunk.start_byte, chunk.end_byte)
            self.assertLessEqual(chunk.start_line, chunk.end_line)
            if idx > 0:
                prev = chunks[idx - 1]
                self.assertLess(prev.start_byte, chunk.start_byte)
                self.assertGreater(prev.end_byte, chunk.start_byte)

    def test_last_chunk_ends_at_content_end(self) -> None:
        strategy = NaiveChunkingStrategy()
        file_name = randomized_file_name()
        text = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n"
        source = text.encode("utf-8")
        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo",
                file_path=file_name,
                content=source,
            ),
            language=None,
            config=ChunkingConfig(max_bytes=8, overlap_bytes=2, min_split_bytes=3),
        )

        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(chunks[-1].end_byte, len(source))

    def test_handles_zero_byte_config(self) -> None:
        class _UnsafeConfig:
            max_bytes = 0
            overlap_bytes = 0
            min_split_bytes = 0

        strategy = NaiveChunkingStrategy()
        file_name = randomized_file_name()
        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo",
                file_path=file_name,
                content=b"data",
            ),
            language="python",
            config=_UnsafeConfig(),
        )
        self.assertEqual(chunks, [])

    def test_breaks_on_empty_chunk_content(self) -> None:
        class _UnsafeConfig:
            max_bytes = 2
            overlap_bytes = 0
            min_split_bytes = 0

        strategy = NaiveChunkingStrategy()
        file_name = randomized_file_name()
        request = FileChunkRequest(
            repo_slug="repo",
            file_path=file_name,
            content=_FakeBytes(b"abcd"),
        )
        chunks = strategy.chunk(
            request=request,
            language="python",
            config=_UnsafeConfig(),
        )
        self.assertEqual(chunks, [])


class TestChunkingHelpers(unittest.TestCase):
    def test_offset_to_line_and_chunk_id(self) -> None:
        self.assertEqual(_offset_to_line([], 0), 1)
        self.assertEqual(_offset_to_line([3, 7], 4), 2)
        first = _build_chunk_id("repo", "file", 0, 3, b"abc")
        second = _build_chunk_id("repo", "file", 0, 3, b"abc")
        different = _build_chunk_id("repo", "file", 0, 3, b"abcd")
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)


class TestTSBaseUtilities(unittest.TestCase):
    def test_collect_nodes_by_type_sorted(self) -> None:
        root = _FakeNode(
            type="root",
            start_byte=0,
            end_byte=10,
            children=[
                _FakeNode(type="b", start_byte=5, end_byte=6),
                _FakeNode(type="a", start_byte=1, end_byte=2),
            ],
        )
        nodes = collect_nodes_by_type(root, {"a", "b"})
        self.assertEqual([node.type for node in nodes], ["a", "b"])

    def test_semantic_spans_with_gaps_handles_invalid_nodes(self) -> None:
        nodes = [
            _FakeNode(type="a", start_byte=5, end_byte=5),
            _FakeNode(type="b", start_byte=1, end_byte=3),
        ]
        spans = _semantic_spans_with_gaps(nodes, total_bytes=8)
        self.assertIn((0, 1), spans)
        self.assertIn((1, 3), spans)
        self.assertIn((3, 8), spans)

    def test_split_byte_span_respects_newlines_and_overlap(self) -> None:
        source = b"line1\nline2\nline3\n"
        config = ChunkingConfig(max_bytes=10, overlap_bytes=2, min_split_bytes=3)
        spans = _split_byte_span(source, start=0, end=len(source), config=config)
        self.assertGreaterEqual(len(spans), 2)
        self.assertLess(spans[0][0], spans[0][1])
        self.assertGreater(spans[1][0], spans[0][0])

    def test_split_byte_span_handles_zero_limit(self) -> None:
        class _UnsafeConfig:
            max_bytes = 0
            overlap_bytes = 0
            min_split_bytes = 0

        spans = _split_byte_span(b"abc", start=0, end=3, config=_UnsafeConfig())
        self.assertEqual(spans, [])


class TestBaseTSChunkingStrategy(unittest.TestCase):
    def test_supports_language(self) -> None:
        parser = _FakeParser(_FakeNode(type="module", start_byte=0, end_byte=1))
        strategy = _TestTSStrategy(parser=parser, nodes=[])
        self.assertTrue(strategy.supports_language("python"))
        self.assertFalse(strategy.supports_language("javascript"))

    def test_returns_empty_for_empty_source(self) -> None:
        parser = _FakeParser(_FakeNode(type="module", start_byte=0, end_byte=1))
        strategy = _TestTSStrategy(parser=parser, nodes=[])
        request = FileChunkRequest(
            repo_slug="repo",
            file_path="pkg/empty.py",
            content=b"",
        )
        chunks = strategy.chunk(
            request=request,
            language="python",
            config=ChunkingConfig(max_bytes=10, overlap_bytes=0, min_split_bytes=0),
        )
        self.assertEqual(chunks, [])

    def test_falls_back_when_no_semantic_nodes(self) -> None:
        content = b"print('ok')\n"
        root = _FakeNode(type="module", start_byte=0, end_byte=len(content))
        parser = _FakeParser(root)
        strategy = _TestTSStrategy(parser=parser, nodes=[])
        request = FileChunkRequest(
            repo_slug="repo",
            file_path="pkg/mod.py",
            content=content,
        )
        chunks = strategy.chunk(
            request=request,
            language="python",
            config=ChunkingConfig(max_bytes=50, overlap_bytes=0, min_split_bytes=0),
        )
        self.assertGreaterEqual(len(chunks), 1)

        with patch(
            "src.pipeline.chunking.ts_base_strategy._semantic_spans_with_gaps",
            return_value=[],
        ):
            chunks = strategy.chunk(
                request=request,
                language="python",
                config=ChunkingConfig(max_bytes=50, overlap_bytes=0, min_split_bytes=0),
            )
        self.assertGreaterEqual(len(chunks), 1)

    def test_skips_invalid_spans_and_empty_chunks(self) -> None:
        content = b"print('ok')\n"
        root = _FakeNode(type="module", start_byte=0, end_byte=len(content))
        parser = _FakeParser(root)
        strategy = _TestTSStrategy(parser=parser, nodes=[])
        request = FileChunkRequest(
            repo_slug="repo",
            file_path="pkg/mod.py",
            content=content,
        )

        with patch(
            "src.pipeline.chunking.ts_base_strategy._semantic_spans_with_gaps",
            return_value=[(5, 5), (0, len(content))],
        ):
            with patch(
                "src.pipeline.chunking.ts_base_strategy._split_byte_span",
                return_value=[(0, 0), (0, len(content))],
            ):
                chunks = strategy.chunk(
                    request=request,
                    language="python",
                    config=ChunkingConfig(
                        max_bytes=50, overlap_bytes=0, min_split_bytes=0
                    ),
                )
        self.assertEqual(len(chunks), 1)

    def test_collect_semantic_nodes_not_implemented(self) -> None:
        parser = _FakeParser(_FakeNode(type="module", start_byte=0, end_byte=1))
        strategy = _NoCollectStrategy(parser=parser)
        with self.assertRaises(NotImplementedError):
            strategy._collect_semantic_nodes(_FakeNode(type="module", start_byte=0, end_byte=1))

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

        with patch.object(TSPyChunkingStrategy, "_build_parser", return_value=parser):
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

        with patch.object(
            TSPyChunkingStrategy,
            "_build_parser",
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
        with patch.object(TSPyChunkingStrategy, "_build_parser", return_value=parser):
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
