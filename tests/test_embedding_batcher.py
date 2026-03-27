import unittest

from src.pipeline.embedding import (
    EmbeddingConfig,
    EmbeddingRequest,
    batch_requests,
)


def fake_token_counter(text: str, model: str) -> int:
    return len(text.split())


class TestEmbeddingBatcher(unittest.TestCase):
    def test_batches_by_batch_size(self) -> None:
        config = EmbeddingConfig(model="test", batch_size=2)
        requests = [
            EmbeddingRequest(text="a", metadata={"i": 0}),
            EmbeddingRequest(text="b", metadata={"i": 1}),
            EmbeddingRequest(text="c", metadata={"i": 2}),
        ]

        batches = batch_requests(requests, config)

        self.assertEqual([len(batch) for batch in batches], [2, 1])
        self.assertEqual(batches[0][0].metadata["i"], 0)
        self.assertEqual(batches[1][0].metadata["i"], 2)

    def test_enforces_max_bytes(self) -> None:
        config = EmbeddingConfig(model="test", max_bytes=3)
        requests = [EmbeddingRequest(text="abcd", metadata={})]

        with self.assertRaises(ValueError):
            batch_requests(requests, config)

    def test_enforces_max_tokens(self) -> None:
        config = EmbeddingConfig(model="test", max_tokens=2)
        requests = [EmbeddingRequest(text="one two three", metadata={})]

        with self.assertRaises(ValueError):
            batch_requests(requests, config, token_counter=fake_token_counter)

    def test_total_token_limit_splits_batches(self) -> None:
        config = EmbeddingConfig(model="test", batch_size=10, max_tokens=5)
        requests = [
            EmbeddingRequest(text="one two", metadata={"i": 0}),
            EmbeddingRequest(text="three four", metadata={"i": 1}),
            EmbeddingRequest(text="five six", metadata={"i": 2}),
        ]

        batches = batch_requests(
            requests,
            config,
            token_counter=fake_token_counter,
            max_total_tokens=4,
        )

        self.assertEqual([len(batch) for batch in batches], [2, 1])

    def test_total_token_limit_applies_without_per_item_max(self) -> None:
        config = EmbeddingConfig(model="test", batch_size=10, max_tokens=None)
        requests = [
            EmbeddingRequest(text="one two", metadata={"i": 0}),
            EmbeddingRequest(text="three four", metadata={"i": 1}),
            EmbeddingRequest(text="five six", metadata={"i": 2}),
        ]

        batches = batch_requests(
            requests,
            config,
            token_counter=fake_token_counter,
            max_total_tokens=4,
        )

        self.assertEqual([len(batch) for batch in batches], [2, 1])

    def test_requires_token_counter_when_max_tokens_set(self) -> None:
        config = EmbeddingConfig(model="test", max_tokens=2)
        requests = [EmbeddingRequest(text="a b", metadata={})]

        with self.assertRaises(ValueError):
            batch_requests(requests, config)


if __name__ == "__main__":
    unittest.main()
