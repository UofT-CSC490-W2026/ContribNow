import unittest

from src.pipeline.chunking import (
    ChunkingConfig,
    FileChunkRequest,
    NaiveChunkingStrategy,
)


class TestNaiveChunking(unittest.TestCase):
    def test_returns_empty_for_empty_content(self) -> None:
        strategy = NaiveChunkingStrategy()
        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo", file_path="src/app.py", content=""
            ),
            language="python",
            config=ChunkingConfig(max_chars=100, overlap_chars=10, min_split_chars=20),
        )
        self.assertEqual(chunks, [])

    def test_chunking_uses_overlap(self) -> None:
        strategy = NaiveChunkingStrategy()
        text = "".join(f"line-{idx}-abcdefghijklmnopqrstuvwxyz\n" for idx in range(120))
        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo", file_path="src/app.py", content=text
            ),
            language="python",
            config=ChunkingConfig(max_chars=200, overlap_chars=30, min_split_chars=80),
        )

        self.assertGreater(len(chunks), 1)
        for idx, chunk in enumerate(chunks):
            self.assertEqual(chunk.strategy, "naive")
            self.assertLess(chunk.start_offset, chunk.end_offset)
            self.assertLessEqual(chunk.start_line, chunk.end_line)
            if idx > 0:
                prev = chunks[idx - 1]
                self.assertLess(prev.start_offset, chunk.start_offset)
                self.assertGreater(prev.end_offset, chunk.start_offset)

    def test_last_chunk_ends_at_content_end(self) -> None:
        strategy = NaiveChunkingStrategy()
        text = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n"
        chunks = strategy.chunk(
            request=FileChunkRequest(
                repo_slug="repo", file_path="notes.txt", content=text
            ),
            language=None,
            config=ChunkingConfig(max_chars=8, overlap_chars=2, min_split_chars=3),
        )

        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(chunks[-1].end_offset, len(text))


if __name__ == "__main__":
    unittest.main()
