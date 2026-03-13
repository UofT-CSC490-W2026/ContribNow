"""
GSM8K evaluation.
https://huggingface.co/datasets/openai/gsm8k

Example problem instance:

Question:
Weng earns $12 an hour for babysitting. Yesterday, she just did 50 minutes of babysitting. How much did she earn?
Answer:
Weng earns 12/60 = $<<12/60=0.2>>0.2 per minute.
Working 50 minutes, she earned 0.2 x 50 = $<<0.2*50=10>>10.
#### 10

Notice that GSM8K uses tool calls inside << >> tags.
"""

import re
import ast
import operator
from datasets import load_dataset
from tasks.common import Task


GSM_RE = re.compile(r"#### (\-?[0-9\.\,]+)")
def extract_answer(completion):
    """
    Extract the numerical answer after #### marker.
    Follows official code for normalization:
    https://github.com/openai/grade-school-math/blob/3101c7d5072418e28b9008a6636bde82a006892c/grade_school_math/dataset.py#L28
    """
    match = GSM_RE.search(completion)
    if match:
        match_str = match.group(1).strip()
        match_str = match_str.replace(",", "")
        return match_str
    return None


class GSM8K(Task):

    def __init__(self, subset, split, **kwargs):
        super().__init__(**kwargs)
        assert subset in ["main", "socratic"], "GSM8K subset must be main|socratic"
        assert split in ["train", "test"], "GSM8K split must be train|test"
        self.ds = load_dataset("openai/gsm8k", subset, split=split).shuffle(seed=42)

    @property
    def eval_type(self):
        return 'generative'

    def num_examples(self):
        return len(self.ds)

    def get_example(self, index):
        """ Get a single problem from the dataset. """
        row = self.ds[index]
        question = row['question'] # string of the question prompt
        answer = row['answer'] # string of the full solution and the answer after #### marker
        # Create and return the Conversation object
        # This is tricky because GSM8K uses tool calls, which we need to parse here.
        assistant_message_parts = []
        parts = re.split(r'(<<[^>]+>>)', answer)
        for part in parts:
            if part.startswith('<<') and part.endswith('>>'):
                # This is a calculator tool call
                inner = part[2:-2]  # Remove << >>
                # Split on = to get expression and result
                if '=' in inner:
                    expr, result = inner.rsplit('=', 1)
                else:
                    expr, result = inner, ""
                # Add the tool call as a part
                assistant_message_parts.append({"type": "python", "text": expr})
                # Add the result as a part
                assistant_message_parts.append({"type": "python_output", "text": result})
            else:
                # Regular text in between tool calls
                assistant_message_parts.append({"type": "text", "text": part})
        # Now put it all together
        messages = [
            {"role": "user", "content": question}, # note: simple string
            {"role": "assistant", "content": assistant_message_parts}, # note: list of parts (as dicts)
        ]
        conversation = {
            "messages": messages,
        }
        return conversation
    
    def _binary_correct_rewards(self, pred_num, ref_num):
        return int(pred_num == ref_num)

    def _relative_correct_rewards(self, pred_num, ref_num):
        try:
            ref_f, pred_f = float(ref_num), float(pred_num)
            rel_error = abs(ref_f - pred_f) / (abs(ref_f) + 1e-8)
            return max(0.0, 1.0 - rel_error)
        except ValueError:
            return 0.0
        
    def _reasoning_step_rewards(self, assistant_response):
        tool_calls = re.findall(r'<<([^>]+)>>', assistant_response)
        valid_steps = 0
        for call in tool_calls:
            if '=' in call:
                expr, result = call.rsplit('=', 1)
                try:
                    if abs(self._safe_eval(expr) - float(result)) < 1e-6:
                        valid_steps += 1
                except:
                    pass
        
        return min(0.3, valid_steps * 0.05)

    def _safe_eval(self, expr):
        """
        Safely evaluate a simple arithmetic expression.
        Supports numbers, parentheses, and basic arithmetic ops.
        """
        node = ast.parse(expr, mode='eval')

        def _eval(n):
            if isinstance(n, ast.Expression):
                return _eval(n.body)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
                op = operator.pos if isinstance(n.op, ast.UAdd) else operator.neg
                return op(_eval(n.operand))
            if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv)):
                ops = {
                    ast.Add: operator.add,
                    ast.Sub: operator.sub,
                    ast.Mult: operator.mul,
                    ast.Div: operator.truediv,
                    ast.Pow: operator.pow,
                    ast.Mod: operator.mod,
                    ast.FloorDiv: operator.floordiv,
                }
                return ops[type(n.op)](_eval(n.left), _eval(n.right))
            raise ValueError("Unsafe or unsupported expression")

        return _eval(node)

    def evaluate(self, conversation, assistant_response, reward_type = "binary"):
        """
        Given (conversation, completion), return evaluation outcome (0 = wrong, 1 = correct)
        Note that:
        - the conversation has both user AND assistant message (containing the ground truth answer)
        - the assistant_response is usually the alternative assistant message achieved via sampling

        TODO: Technically, assistant_response should be a Message (either a string or a list of parts)
              We can handle this later possibly. For now just assume string.
        """
        assert isinstance(assistant_response, str), "Assuming simple string response for now"
        # First extract the ground truth answer
        assistant_message = conversation['messages'][-1]
        assert assistant_message['role'] == "assistant", "Last message must be from the Assistant"
        assert isinstance(assistant_message['content'], list), "This is expected to be a list of parts"
        assert reward_type in {'binary', 'relative', 'reasoning', 'relative_and_reasoning'}, "Invalid reward type" 
        last_text_part = assistant_message['content'][-1]['text'] # this contains the final answer in GSM8K
        # Extract both the ground truth answer and the predicted answer
        ref_num = extract_answer(last_text_part)
        pred_num = extract_answer(assistant_response)

        if pred_num is None:
            return 0.0
    
        if reward_type == "binary":
            return self._binary_correct_rewards(pred_num, ref_num)
        elif reward_type == "relative":
            return self._relative_correct_rewards(pred_num, ref_num)
        elif reward_type == "reasoning":
            correct_rewards = self._binary_correct_rewards(pred_num, ref_num)
            step_bonus = self._reasoning_step_rewards(assistant_response)
            return min(1.0, correct_rewards * 0.7 + step_bonus)
        elif reward_type == "relative_and_reasoning":
            correct_rewards = self._relative_correct_rewards(pred_num, ref_num)
            step_bonus = self._reasoning_step_rewards(assistant_response)
            return min(1.0, correct_rewards * 0.7 + step_bonus)

    def reward(self, conversation, assistant_response, reward_type = "binary"):
        """
        Used during RL. To keep things simple, just re-use the evaluation above.
        Later this could be made more complex (e.g. format matching etc.)
        """
        is_correct = self.evaluate(conversation, assistant_response, reward_type)
        is_correct_float = float(is_correct)
        return is_correct_float
