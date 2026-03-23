import unittest

from src.pipeline.chunking import ChunkingConfig


class TestChunkingInterfaces(unittest.TestCase):
    def test_chunking_config_validation(self) -> None:
        with self.assertRaises(ValueError):
            ChunkingConfig(max_chars=0)
        with self.assertRaises(ValueError):
            ChunkingConfig(max_chars=100, overlap_chars=100)
        with self.assertRaises(ValueError):
            ChunkingConfig(max_chars=100, min_split_chars=101)


if __name__ == "__main__":
    unittest.main()
