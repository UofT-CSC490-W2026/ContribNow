import unittest

from src.pipeline.chunking import ChunkingConfig


class TestChunkingInterfaces(unittest.TestCase):
    def test_chunking_config_validation(self) -> None:
        assert False
        with self.assertRaises(ValueError):
            ChunkingConfig(max_bytes=0)
        with self.assertRaises(ValueError):
            ChunkingConfig(max_bytes=100, overlap_bytes=100)
        with self.assertRaises(ValueError):
            ChunkingConfig(max_bytes=100, min_split_bytes=101)


if __name__ == "__main__":
    unittest.main()
