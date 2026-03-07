"""
Custom Part 3 evaluation:
- Uses a base-model CORE task (default: hellaswag_zeroshot)
- Filters to long prompts (default min length = 512 tokens)
- Evaluates one checkpoint and reports accuracy/centered score

Example:
    torchrun --standalone --nproc_per_node=4 -m scripts.part3_eval_longprompts -- \
      --model-tag d16-relu2-ctxext --step 1200 \
      --task-label hellaswag_zeroshot --min-prompt-tokens 512 --max-problems 300
"""

import os
import csv
import json
import yaml
import random
import shutil
import zipfile
import tempfile
import argparse

from nanochat.common import (
    compute_init,
    compute_cleanup,
    print0,
    get_base_dir,
    autodetect_device_type,
    download_file_with_lock,
)
from nanochat.checkpoint_manager import load_model
from nanochat.core_eval import (
    evaluate_task,
    render_prompts_mc,
    render_prompts_schema,
    render_prompts_lm,
)

EVAL_BUNDLE_URL = "https://karpathy-public.s3.us-west-2.amazonaws.com/eval_bundle.zip"


def place_eval_bundle(file_path):
    """Unzip eval_bundle.zip and place it in the base directory."""
    base_dir = get_base_dir()
    eval_bundle_dir = os.path.join(base_dir, "eval_bundle")
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)
        extracted_bundle_dir = os.path.join(tmpdir, "eval_bundle")
        if os.path.exists(eval_bundle_dir):
            shutil.rmtree(eval_bundle_dir)
        shutil.move(extracted_bundle_dir, eval_bundle_dir)
    print0(f"Placed eval_bundle directory at {eval_bundle_dir}")


def load_core_bundle():
    base_dir = get_base_dir()
    eval_bundle_dir = os.path.join(base_dir, "eval_bundle")
    if not os.path.exists(eval_bundle_dir):
        download_file_with_lock(
            EVAL_BUNDLE_URL, "eval_bundle.zip", postprocess_fn=place_eval_bundle
        )
    config_path = os.path.join(eval_bundle_dir, "core.yaml")
    data_base_path = os.path.join(eval_bundle_dir, "eval_data")
    eval_meta_data = os.path.join(eval_bundle_dir, "eval_meta_data.csv")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["icl_tasks"], data_base_path, eval_meta_data


def load_random_baselines(eval_meta_data_path):
    random_baselines = {}
    with open(eval_meta_data_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            random_baselines[row["Eval Task"]] = float(row["Random baseline"])
    return random_baselines


def resolve_task(tasks, requested_label):
    exact = [t for t in tasks if t["label"].lower() == requested_label.lower()]
    if len(exact) == 1:
        return exact[0]
    contains = [t for t in tasks if requested_label.lower() in t["label"].lower()]
    if len(contains) == 1:
        return contains[0]
    labels = [t["label"] for t in tasks]
    raise ValueError(
        f"Could not resolve task label '{requested_label}'. Available: {labels}"
    )


def estimate_prompt_len_tokens(item, task_meta, tokenizer):
    """Estimate prompt length used by CORE evaluation for one item."""
    bos = tokenizer.get_bos_token_id()
    task_type = task_meta["task_type"]
    delim = task_meta["continuation_delimiter"]
    if task_type == "multiple_choice":
        prompts = render_prompts_mc(item, delim, fewshot_examples=None)
        toks = tokenizer(prompts, prepend=bos)
        return max(len(t) for t in toks)
    if task_type == "schema":
        prompts = render_prompts_schema(item, delim, fewshot_examples=None)
        toks = tokenizer(prompts, prepend=bos)
        return max(len(t) for t in toks)
    if task_type == "language_modeling":
        prompts = render_prompts_lm(item, delim, fewshot_examples=None)
        toks = tokenizer(prompts, prepend=bos)
        # prompts_lm returns [without_continuation, with_continuation]
        return len(toks[1])
    raise ValueError(f"Unsupported task type: {task_type}")


def main():
    parser = argparse.ArgumentParser(description="Part 3 custom long-prompt eval")
    parser.add_argument("--model-tag", type=str, required=True)
    parser.add_argument("--step", type=int, default=None)
    parser.add_argument("--task-label", type=str, default="hellaswag_zeroshot")
    parser.add_argument("--max-problems", type=int, default=300)
    parser.add_argument("--min-prompt-tokens", type=int, default=512)
    parser.add_argument("--device-type", type=str, default="", help="cuda|cpu|mps")
    args = parser.parse_args()

    device_type = autodetect_device_type() if args.device_type == "" else args.device_type
    ddp, ddp_rank, ddp_local_rank, ddp_world_size, device = compute_init(device_type)

    model, tokenizer, meta = load_model(
        "base", device, phase="eval", model_tag=args.model_tag, step=args.step
    )

    tasks, data_base_path, eval_meta_data = load_core_bundle()
    task = resolve_task(tasks, args.task_label)
    task_label = task["label"]
    task_meta = {
        "task_type": task["icl_task_type"],
        "dataset_uri": task["dataset_uri"],
        "num_fewshot": task["num_fewshot"][0],
        "continuation_delimiter": task.get("continuation_delimiter", " "),
    }

    data_path = os.path.join(data_base_path, task_meta["dataset_uri"])
    with open(data_path, "r", encoding="utf-8") as f:
        full_data = [json.loads(line.strip()) for line in f]

    # Filter by prompt length to create a custom long-context slice.
    filtered = []
    lengths = []
    for item in full_data:
        plen = estimate_prompt_len_tokens(item, task_meta, tokenizer)
        if plen >= args.min_prompt_tokens:
            filtered.append(item)
            lengths.append(plen)

    rng = random.Random(1337)
    rng.shuffle(filtered)
    if args.max_problems > 0:
        filtered = filtered[: args.max_problems]

    print0("=" * 80)
    print0(
        f"Part3 custom eval | task={task_label} | model_tag={args.model_tag} | step={meta['step']}"
    )
    print0(
        f"Filter: prompt_len >= {args.min_prompt_tokens} | "
        f"kept={len(filtered)} / total={len(full_data)}"
    )
    if lengths:
        print0(
            f"Prompt length stats (kept set, pre-truncation): "
            f"min={min(lengths)} max={max(lengths)} avg={sum(lengths)/len(lengths):.1f}"
        )
    print0("=" * 80)

    if len(filtered) == 0:
        raise RuntimeError(
            f"No items left after filtering with min_prompt_tokens={args.min_prompt_tokens}"
        )

    accuracy = evaluate_task(model, tokenizer, filtered, device, task_meta)
    random_baseline = load_random_baselines(eval_meta_data).get(task_label, 0.0)
    centered = (accuracy - 0.01 * random_baseline) / (1.0 - 0.01 * random_baseline)

    print0(f"{task_label} (long-prompt) accuracy: {accuracy:.6f}")
    print0(f"{task_label} (long-prompt) centered: {centered:.6f}")

    if ddp_rank == 0:
        base_dir = get_base_dir()
        out_dir = os.path.join(base_dir, "part3_custom_eval")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(
            out_dir,
            f"{args.model_tag}_step{meta['step']:06d}_{task_label}_min{args.min_prompt_tokens}.json",
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "task": task_label,
                    "model_tag": args.model_tag,
                    "step": meta["step"],
                    "max_problems": args.max_problems,
                    "min_prompt_tokens": args.min_prompt_tokens,
                    "num_examples": len(filtered),
                    "accuracy": accuracy,
                    "centered": centered,
                    "random_baseline_pct": random_baseline,
                },
                f,
                indent=2,
            )
        print0(f"Wrote custom eval json: {out_path}")

    compute_cleanup()


if __name__ == "__main__":
    main()
