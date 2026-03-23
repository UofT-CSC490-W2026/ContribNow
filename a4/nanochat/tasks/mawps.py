"""
MAWPS arithmetic word problems in Calc-X format.
https://huggingface.co/datasets/MU-NLPC/Calc-mawps
"""

from datasets import load_dataset
from tasks.calcx import CalcXTask


class MAWPS(CalcXTask):
    """
    By default this uses the filtered Calc-X split variant of MAWPS.
    Pass config="original-splits" if you explicitly want the original split layout.
    """

    def __init__(self, split, config="default", **kwargs):
        super().__init__(**kwargs)
        assert split in ["train", "validation", "test"], "MAWPS split must be train|validation|test"
        self.ds = load_dataset("MU-NLPC/Calc-mawps", config, split=split).shuffle(seed=42)
