"""
Shared utilities for Calc-X style arithmetic word-problem datasets.
"""

import re
from tasks.common import Task


ANSWER_RE = re.compile(r"####\s*([^\n]+)")
CHAIN_TAG_RE = re.compile(r"<(gadget|output|result)(?:\s+[^>]*)?>(.*?)</\1>")


def normalize_answer(text):
    """Normalize a numeric answer string for exact-match comparison."""
    text = text.strip().splitlines()[0]
    text = text.replace(",", "").replace("_", "")
    parts = text.split()
    return parts[0] if parts else None


def extract_answer(completion):
    """Extract the answer from a `#### ...` final-answer line."""
    match = ANSWER_RE.search(completion)
    if match:
        return normalize_answer(match.group(1))
    return None


def render_calcx_chain(chain, result):
    """
    Convert Calc-X html-like calculator traces into nanochat assistant parts.
    """
    assistant_parts = []
    cursor = 0
    for match in CHAIN_TAG_RE.finditer(chain):
        prefix = chain[cursor:match.start()]
        if prefix.strip():
            assistant_parts.append({"type": "text", "text": prefix.strip()})
        tag = match.group(1)
        body = match.group(2).strip()
        if tag == "gadget":
            assistant_parts.append({"type": "python", "text": body})
        elif tag == "output":
            assistant_parts.append({"type": "python_output", "text": body})
        elif tag == "result":
            assistant_parts.append({"type": "text", "text": f"\n\n#### {normalize_answer(body)}"})
        cursor = match.end()

    suffix = chain[cursor:]
    if suffix.strip():
        assistant_parts.append({"type": "text", "text": suffix.strip()})

    if not assistant_parts:
        assistant_parts.append({"type": "text", "text": f"#### {normalize_answer(result)}"})
    elif assistant_parts[-1]["type"] != "text" or "####" not in assistant_parts[-1]["text"]:
        assistant_parts.append({"type": "text", "text": f"\n\n#### {normalize_answer(result)}"})

    return assistant_parts


class CalcXTask(Task):
    """
    Base class for calculator-augmented arithmetic word-problem datasets.
    """

    @property
    def eval_type(self):
        return "generative"

    def num_examples(self):
        return len(self.ds)

    def get_example(self, index):
        row = self.ds[index]
        question = row["question"]
        chain = row["chain"]
        result = row["result"]
        messages = [
            {"role": "user", "content": question},
            {"role": "assistant", "content": render_calcx_chain(chain, result)},
        ]
        return {"messages": messages}

    def evaluate(self, conversation, assistant_response):
        assert isinstance(assistant_response, str), "Assuming simple string response for now"
        assistant_message = conversation["messages"][-1]
        assert assistant_message["role"] == "assistant", "Last message must be from the Assistant"
        assert isinstance(assistant_message["content"], list), "Assistant message must be a list of parts"
        last_text_part = assistant_message["content"][-1]["text"]
        ref_num = extract_answer(last_text_part)
        pred_num = extract_answer(assistant_response)
        return int(pred_num == ref_num)

    def reward(self, conversation, assistant_response):
        return float(self.evaluate(conversation, assistant_response))
