"""
MetaMathQA math instruction-following dataset.
https://huggingface.co/datasets/meta-math/MetaMathQA

This is a substantially larger math SFT source than ASDiv/SVAMP/MAWPS and is
useful for ~100k-row math ablations without extreme oversampling of small sets.
"""

from datasets import load_dataset
from tasks.common import Task


class MetaMathQA(Task):
    """
    Official MetaMathQA dataset.

    The dataset provides a `train` split on Hugging Face. Use Task slicing via
    start/stop to choose a smaller subset, e.g. `stop=100000` for a 100k-row
    ablation.
    """

    def __init__(self, split, **kwargs):
        super().__init__(**kwargs)
        assert split == "train", "MetaMathQA only provides a train split"
        self.ds = load_dataset("meta-math/MetaMathQA", split=split).shuffle(seed=42)

    def num_examples(self):
        return len(self.ds)

    def get_example(self, index):
        row = self.ds[index]
        messages = [
            {"role": "user", "content": row["query"]},
            {"role": "assistant", "content": row["response"]},
        ]
        return {"messages": messages}
