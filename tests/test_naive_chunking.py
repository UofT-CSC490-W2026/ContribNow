import unittest
from pathlib import Path
from uuid import uuid4

from src.pipeline.chunking import (
    ChunkingConfig,
    FileChunkRequest,
    NaiveChunkingStrategy,
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


class TestNaiveChunking(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
