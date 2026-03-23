"""
ASDiv-A arithmetic word problems in Calc-X format.
https://huggingface.co/datasets/MU-NLPC/Calc-asdiv_a
"""

from datasets import load_dataset
from tasks.calcx import CalcXTask


class ASDiv(CalcXTask):
    """
    Calc-ASDiv_A only ships a benchmark split, so both train and test map to HF's test split.
    If you want a held-out split locally, use Task slicing via start/stop.
    """

    def __init__(self, split, config="default", **kwargs):
        super().__init__(**kwargs)
        assert split in ["train", "test"], "ASDiv split must be train|test"
        hf_split = "test"
        self.ds = load_dataset("MU-NLPC/Calc-asdiv_a", config, split=hf_split).shuffle(seed=42)
