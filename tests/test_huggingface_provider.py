import os
import unittest

from src.pipeline.embedding import EmbeddingConfig, EmbeddingRequest
from src.pipeline.embedding.providers.huggingface_provider import (
    HuggingFaceEmbeddingProvider,
)


@unittest.skipUnless(
    os.getenv("RUN_HF_TESTS") == "1",
    "Set RUN_HF_TESTS=1 to run Hugging Face model download tests.",
)
class TestHuggingFaceProvider(unittest.TestCase):
    def test_bge_code_v1_embeddings(self) -> None:
        provider = HuggingFaceEmbeddingProvider()
        config = EmbeddingConfig(model="BAAI/bge-code-v1", batch_size=2)
        requests = [
            EmbeddingRequest(text="def add(a, b): return a + b", metadata={"i": 0}),
            EmbeddingRequest(text="class Greeter: pass", metadata={"i": 1}),
        ]

        result = provider.embed(requests, config)

        self.assertEqual(len(result.vectors), 2)
        self.assertEqual(len(result.metadata), 2)
        self.assertGreater(len(result.vectors[0]), 0)
        self.assertEqual(result.metadata[0]["i"], 0)


if __name__ == "__main__":
    unittest.main()
