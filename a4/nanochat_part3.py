"""
Usage
-----
Full speedrun (mirrors `bash runs/speedrun.sh`):
    modal run nanochat_modal.py

Part 3 pipeline (short context -> long context continuation -> comparison eval):
    modal run nanochat_modal.py::part3

Individual stages (if you want to re-run one step):
    modal run nanochat_modal.py::stage_data
    modal run nanochat_modal.py::stage_tokenizer
    modal run nanochat_modal.py::stage_pretrain
    modal run nanochat_modal.py::stage_post_pretrain_eval
    modal run nanochat_modal.py::stage_part3_short_context
    modal run nanochat_modal.py::stage_part3_extend_context
    modal run nanochat_modal.py::stage_part3_eval_compare
    modal run nanochat_modal.py::stage_part3_eval_longprompts_compare
    modal run nanochat_modal.py::stage_list_checkpoints
    modal run nanochat_modal.py::stage_sft
    modal run nanochat_modal.py::stage_rl          # optional
    modal run nanochat_modal.py::stage_chat_sample

Cost reference (8×H100 at ~$31/hr for the node)
------------------------------------------------
    quick_test  d12, 8 shards    : ~15 min
    speedrun    d24, 240 shards  : ~3 hours

Notes
-----
- Modal Volumes persist data between runs, so downloaded shards and
  checkpoints survive container restarts. Stages are idempotent where
  possible (they skip work already done).
- The nanochat repo is regularly updated. If a flag name changes, check the
  matching speedrun.sh in your cloned repo and update the args
"""

import os
import subprocess
import modal
from modal import App, Image as ModalImage, Volume, Secret

# =============================================================================
# CONFIGURATION
# =============================================================================

# ── Model depth ──────────────────────────────────────────────────────────────
#   d12  ~125M params   5 min on 8xH100    good for iterating on code changes
#   d20  ~560M params   1.5 hr on 8xH100   budget speedrun (~$36)
#   d24  ~768M params   3 hr on 8xH100
#   d26  ~1B params     6 hr on 8xH100
#   d32  ~1.9B params   41 hr on 8xH100
DEPTH = 16

# ── Data shards ───────────────────────────────────────────────────────────────
# FineWeb-EDU is split into 1822 parquet shards, each ~250M chars / ~100MB.
# 240 shards is enough for d24. Use 450 for d26 and 800 for d32.
NUM_SHARDS = 160

# ── GPU configuration ─────────────────────────────────────────────────────────
# "H100:8" = 8 H100s, the reference configuration for the speedrun leaderboard.
# "H100:4" = 4 H100s, half the speed, same cost per GPU-hour.
# "A100:8" = 8 A100 80GBs, ~10-20% slower than H100s but sometimes cheaper.
# Single GPU works too — code auto-compensates with gradient accumulation.
GPU_PRETRAIN = "H100:8"
GPU_FINETUNE = "H100:4"  # SFT and RL don't need all 8 GPUs

# ── Device batch size ─────────────────────────────────────────────────────────
# Sequences per GPU per forward pass. Reduce if you hit OOM.
# The training script automatically adjusts gradient accumulation to compensate
# so the effective total batch size (524,288 tokens default) stays the same.
#
#   H100 80GB: 32 fits for d24, 16 for d26, 8 for d32
#   A100 80GB: same as H100
#   A100 40GB: use 16 for d24
DEVICE_BATCH_SIZE = 16  # d24 at 16 is safe; 32 may OOM on some H100 configs

# ── WandB ─────────────────────────────────────────────────────────────────────
# Set to "dummy" to disable WandB logging
WANDB_RUN = "picochat-base-d16"

# ── Part 3 defaults: context extension curriculum ────────────────────────────
# Stage A (checkpoint 1): short-context pretrain (task budget subset).
# Stage B (checkpoint 2): resume same model tag at long context.
PART3_NUM_SHARDS = 160
PART3_SHORT_SEQ_LEN = 512
PART3_LONG_SEQ_LEN = 2048
PART3_SHORT_NUM_ITERATIONS = 1200
PART3_LONG_ADDITIONAL_ITERATIONS = 1200
PART3_SHORT_WANDB_RUN = "picochat-part3-d16-base-shortctx"
PART3_LONG_WANDB_RUN = "picochat-part3-d16-base-extendctx"
PART3_EVAL_SPLIT_TOKENS = 2 * 524288
PART3_TASK_LABEL = "hellaswag_zeroshot"
PART3_TASK_MAX_PROBLEMS = 300
PART3_CUSTOM_TASK_LABEL = "hellaswag_zeroshot"
PART3_CUSTOM_MIN_PROMPT_TOKENS = 512
PART3_CUSTOM_MAX_PROBLEMS = 300

# ── Volume mount path ──────────────────────────────────────────────────────────
# All cached data (shards, tokenizer, checkpoints, eval bundle) lives here
# inside the Modal Volume. nanochat defaults to ~/.cache/nanochat; symlink
# the path to here so the code finds everything without modification.
VOLUME_MOUNT = "/vol"
NANOCHAT_CACHE = f"{VOLUME_MOUNT}/nanochat_cache"  # mirrors $NANOCHAT_BASE_DIR
BASE_DIR = "/data/.cache/nanochat"
PROJECT_DIR = "/root/nanochat"
DEPS_DIR = "/opt/nanochat_deps"
VENV_BIN = f"{DEPS_DIR}/.venv/bin"

# ── Timeout ───────────────────────────────────────────────────────────────────
# Modal kills a container after this many seconds of wall-clock time.
# The pretrain timeout must be longer than your expected training time.
PRETRAIN_TIMEOUT_SEC = 60 * 60 * 6  # 6 hours
FINETUNE_TIMEOUT_SEC = 60 * 60 * 2  # 2 hours (SFT and RL are much shorter)
DOWNLOAD_TIMEOUT_SEC = 60 * 90  # 90 min for shard download

# ── Derived: GPU count ────────────────────────────────────────────────────────
# Extract the integer from "H100:8" -> 8.  Used to pass --nproc_per_node.
_N_PRETRAIN_GPUS = int(GPU_PRETRAIN.split(":")[1]) if ":" in GPU_PRETRAIN else 1
_N_FINETUNE_GPUS = int(GPU_FINETUNE.split(":")[1]) if ":" in GPU_FINETUNE else 1

# Eval bundle URL (fixed, hosted by Karpathy)
EVAL_BUNDLE_URL = "https://karpathy-public.s3.us-west-2.amazonaws.com/eval_bundle.zip"

# Identity conversations for SFT personality layer
IDENTITY_JSONL_URL = (
    "https://karpathy-public.s3.us-west-2.amazonaws.com/identity_conversations.jsonl"
)

# =============================================================================
# MODAL PRIMITIVES — App, Volume, Secret, Image
# =============================================================================

# app = modal.App("nanochat-speedrun")
app = modal.App("picochat-part3-d16-base")

# Persistent network volume: survives container shutdowns.
# Stores downloaded shards (~24GB), tokenizer, checkpoints, eval bundle.
# First time you run, Modal creates this automatically.
volume = Volume.from_name("nanochat-vol", create_if_missing=True)

# Secret: injects WANDB_API_KEY and HF_TOKEN as env vars inside containers.
# Create once with:
#   modal secret create nanochat-secrets WANDB_API_KEY=... HF_TOKEN=hf_...
secret = Secret.from_name("nanochat-secrets")

# Container image -- built once, cached by Modal until you change it.
# Mirrors the environment setup block at the top of speedrun.sh:
#   command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh
#   uv sync
#   maturin develop --release --manifest-path rustbpe/Cargo.toml
image = (
    # NVIDIA CUDA 12.8 with Python 3.11
    ModalImage.from_registry("nvidia/cuda:12.8.1-devel-ubuntu24.04", add_python="3.11")
    # System dependencies
    .apt_install("git", "build-essential", "curl", "wget", "unzip")
    # Copy only dependency metadata first so this layer remains cacheable
    # across normal source-code edits.
    .add_local_file(
        local_path="./nanochat/pyproject.toml",
        remote_path=f"{DEPS_DIR}/pyproject.toml",
        copy=True,
    )
    .add_local_file(
        local_path="./nanochat/uv.lock",
        remote_path=f"{DEPS_DIR}/uv.lock",
        copy=True,
    )
    # Required because pyproject sets readme = "README.md".
    .add_local_file(
        local_path="./nanochat/README.md",
        remote_path=f"{DEPS_DIR}/README.md",
        copy=True,
    )
    # Install Rust and uv
    .run_commands(
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
        "echo 'source $HOME/.cargo/env' >> $HOME/.bashrc",
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "echo 'export PATH=\"$HOME/.cargo/bin:$PATH\"' >> $HOME/.bashrc",
        "bash -c 'source $HOME/.cargo/env'",
    )
    .pip_install("uv")
    # Environment variables
    .env(
        {
            "OMP_NUM_THREADS": "1",
            "NANOCHAT_BASE_DIR": "/data/.cache/nanochat",
            "HF_HOME": "/data/.cache/huggingface",
            "UV_CACHE_DIR": "/tmp/uv-cache",
        }
    )
    .run_commands(
        f"cd {DEPS_DIR} && uv sync --extra gpu --no-install-project",
    )
    # Copy source after deps install so code changes do not invalidate torch layer.
    .add_local_dir(local_path="./nanochat", remote_path=PROJECT_DIR, copy=True)
    .workdir(PROJECT_DIR)
)

# =============================================================================
# HELPERS
# =============================================================================


def _python(
    module: str, args: list | None = None, *, cwd: str = PROJECT_DIR
) -> None:
    """Run `python -m {module} [args]` -- for non-distributed scripts."""
    args = args or []
    cmd = f"cd {cwd} && {VENV_BIN}/python -m {module} {' '.join(args)}"
    _run(cmd)


def _torchrun(module: str, args: list | None = None, *, nproc: int) -> None:
    """
    Run a nanochat training script under torchrun for multi-GPU distributed execution.

    Mirrors the pattern used throughout speedrun.sh:
        torchrun --standalone --nproc_per_node=$NPROC_PER_NODE -m {module} -- {args}

    torchrun spawns `nproc` processes (one per GPU), assigns each a local rank,
    and sets up NCCL for gradient synchronisation across GPUs.
    --standalone means single-node (no multi-machine rendezvous server needed).
    The -- separates torchrun's own flags from the script's argument parser.
    """
    args = args or []
    args_str = (" -- " + " ".join(args)) if args else ""
    cmd = (
        f"cd {PROJECT_DIR} && "
        f"{VENV_BIN}/torchrun --standalone --nproc_per_node={nproc} -m {module}{args_str}"
    )
    print(cmd)
    _run(cmd)


def _run(cmd: str) -> None:
    """Shell out to bash, stream stdout/stderr, and raise on failure."""
    print(f"\n>>>  {cmd}\n")
    result = subprocess.run(["bash", "-c", cmd], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command exited with code {result.returncode}:\n  {cmd}")


def _base_model_tag(depth: int, use_swiglu: bool) -> str:
    """Return canonical base checkpoint tag for architecture selection."""
    return f"d{depth}-{'swiglu' if use_swiglu else 'relu2'}"


def _part3_model_tag(depth: int, use_swiglu: bool) -> str:
    """Return a stable checkpoint tag for the Part 3 context extension run."""
    return f"{_base_model_tag(depth, use_swiglu)}-ctxext"


# def _setup_base_dir():
#     os.makedirs(BASE_DIR, exist_ok=True)
#     os.makedirs(f"{BASE_DIR}/base_data", exist_ok=True)
#     os.makedirs(f"{BASE_DIR}/tokenizer", exist_ok=True)
#     os.makedirs(f"{BASE_DIR}/checkpoints", exist_ok=True)
#     os.makedirs(f"{BASE_DIR}/eval_bundle", exist_ok=True)
#     os.makedirs(f"{BASE_DIR}/report", exist_ok=True)


def _setup_cache() -> None:
    """
    Create cache directories and symlink ~/.cache/nanochat -> the volume.

    nanochat hardcodes $NANOCHAT_BASE_DIR (defaulting to ~/.cache/nanochat) as
    the root for all its output: data shards, the tokenizer, checkpoints,
    the eval bundle, and the markdown report.  By symlinking that path to
    our persistent Modal Volume, everything survives across container restarts.

    speedrun.sh:
        export NANOCHAT_BASE_DIR="$HOME/.cache/nanochat"
        mkdir -p $NANOCHAT_BASE_DIR
    """
    # _setup_base_dir()
    os.makedirs(NANOCHAT_CACHE, exist_ok=True)

    if not os.path.lexists(BASE_DIR):
        os.makedirs("/data/.cache/", exist_ok=True)
        os.symlink(NANOCHAT_CACHE, BASE_DIR)
        print(f"Symlinked {BASE_DIR} -> {NANOCHAT_CACHE}")
    else:
        print(f"Cache symlink already exists: {BASE_DIR}")


def _curl(url: str, dest: str) -> None:
    """Download a file with curl, skipping if already present."""
    if os.path.exists(dest):
        print(f"Already cached, skipping: {dest}")
        return
    _run(f"curl -L -o {dest} {url}")


def _print_core_task_from_csv(step: int, task_label: str) -> None:
    """
    Read base_eval CSV and print one selected CORE task result.

    base_eval writes CSVs as:
      /.../base_eval/base_model_<step>.csv
    """
    csv_path = os.path.join(NANOCHAT_CACHE, "base_eval", f"base_model_{step:06d}.csv")
    if not os.path.exists(csv_path):
        print(f"CORE CSV not found at {csv_path}")
        return

    found = False
    with open(csv_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.strip().split(",")]
            if len(parts) < 3:
                continue
            label = parts[0]
            if label.lower() == task_label.lower():
                acc = parts[1]
                centered = parts[2]
                print(
                    f"Selected CORE task @ step {step}: "
                    f"{label} | accuracy={acc} | centered={centered}"
                )
                found = True
                break
    if not found:
        print(
            f"Task '{task_label}' not found in {csv_path}. "
            "Use the exact label from core.yaml/base_eval output."
        )


# =============================================================================
# STAGE 0: DATA DOWNLOAD
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    cpu=8,
    memory=16384,
    timeout=DOWNLOAD_TIMEOUT_SEC,
)
def stage_data(num_shards: int = NUM_SHARDS) -> None:
    """
    Download FineWeb-EDU dataset shards (CPU-only, run once).

    speedrun.sh:
        python -m nanochat.dataset -n 240

    Each shard is one parquet file of ~250M chars / ~100MB of high-quality
    educational web text, re-packaged by Karpathy from HuggingFace.
    nanochat.dataset parallelises the download internally and skips shards
    that are already present on disk -- this stage is idempotent.

    240 shards = ~24GB = enough data for a d24 model at the default
    tokens:params ratio (~10x Chinchilla-optimal).
    """
    _setup_cache()
    print(f"Downloading {num_shards} FineWeb-EDU shards...")
    _python("nanochat.dataset", [f"-n {num_shards}"])
    volume.commit()
    print(f"Done: {num_shards} shards downloaded.")


# =============================================================================
# STAGE 1: TOKENIZER TRAINING
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu="H100:1",
    timeout=60 * 30,
)
def stage_tokenizer() -> None:
    """
    Train a custom BPE tokenizer on 2B characters of FineWeb-EDU.

    speedrun.sh:
        python -m scripts.tok_train --max-chars=2000000000
        python -m scripts.tok_eval

    The tokenizer is implemented in Rust (rustbpe/) for speed and wrapped in
    a Python API in nanochat/tokenizer.py. It uses the same algorithm as GPT-4:
    regex pre-splitting followed by byte-level BPE. The default vocab size is
    2^16 = 65,536 tokens (9 are reserved as special chat tokens like
    <|user_start|>, <|assistant_start|>, etc.).

    tok_eval prints the compression ratio (should be ~4.8 chars/token, beating
    GPT-2's ~3.9 chars/token).

    This stage takes ~1-2 minutes and only needs to run once.
    """
    _setup_cache()

    tokenizer_path = os.path.join(NANOCHAT_CACHE, "tokenizer.model")
    if os.path.exists(tokenizer_path):
        print("Tokenizer already trained. Skipping tok_train.")
    else:
        print("Training tokenizer on 2B characters...")
        # speedrun.sh: python -m scripts.tok_train --max-chars=2000000000
        _python("scripts.tok_train", ["--max-chars=2000000000"])
        volume.commit()

    # speedrun.sh: python -m scripts.tok_eval
    print("Evaluating tokenizer compression ratio...")
    _python("scripts.tok_eval")
    print("Tokenizer ready.")


# =============================================================================
# STAGE 2: BASE MODEL PRETRAINING
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu=GPU_PRETRAIN,
    timeout=PRETRAIN_TIMEOUT_SEC,
)
def stage_pretrain(
    depth: int = DEPTH,
    device_batch_size: int = DEVICE_BATCH_SIZE,
    wandb_run: str = WANDB_RUN,
    use_swiglu: bool = False,
    model_tag: str = "",
) -> None:
    """
    Pretrain the base GPT model on FineWeb-EDU from random initialization.

    speedrun.sh:
        python -m nanochat.report reset
        torchrun --standalone --nproc_per_node=8 -m scripts.base_train -- \\
            --depth=20 \\
            --device-batch-size=16 \\
            --run=$WANDB_RUN

    This is the most compute-intensive stage. The training loop in
    scripts/base_train.py implements:
        - Chinchilla-optimal token budget derived from depth
        - Muon optimizer for weight matrices, AdamW for embeddings
        - BOS-aligned BestFit-Crop data packing (no midtraining)
        - Cosine LR warmup + linear warmdown (50% of training)
        - Gradient accumulation if device_batch_size * n_gpus < target batch

    Flags:
        --depth               Transformer depth; controls all other hparams
        --device-batch-size   Sequences per GPU per step (reduce if OOM)
        --run                 WandB run name ("dummy" to disable logging)
        --save-every          Checkpoint every N steps (resume-friendly)
    """
    _setup_cache()

    # speedrun.sh: python -m nanochat.report reset
    # Resets the markdown report file and writes system info + run timestamp.
    print("Resetting training report...")
    _python("nanochat.report", ["reset"])

    print(
        f"Starting pretraining: depth={depth}, "
        f"device_batch_size={device_batch_size}, "
        f"nproc={_N_PRETRAIN_GPUS}, run={wandb_run}, use_swiglu={use_swiglu}"
    )

    # speedrun.sh: torchrun --standalone --nproc_per_node=$NPROC_PER_NODE
    #              -m scripts.base_train -- --depth=24 --device-batch-size=16 --run=...
    resolved_model_tag = model_tag or _base_model_tag(depth, use_swiglu)
    train_args = [
        f"--depth={depth}",
        f"--device-batch-size={device_batch_size}",
        f"--run={wandb_run}",
        f"--model-tag={resolved_model_tag}",
        "--save-every=1000",  # checkpoint every 1k steps for resilience
    ]
    if use_swiglu:
        train_args.append("--use-swiglu")
    _torchrun(
        "scripts.base_train",
        train_args,
        nproc=_N_PRETRAIN_GPUS,
    )

    volume.commit()
    print("Pretraining complete.")


# =============================================================================
# STAGE 3: POST-PRETRAIN EVALUATION
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu=GPU_PRETRAIN,
    timeout=60 * 60 * 2,
)
def stage_post_pretrain_eval() -> None:
    """
    Evaluate the base model immediately after pretraining.

    speedrun.sh:
        torchrun ... -m scripts.base_eval

    scripts.base_eval  -- runs the CORE metric: zero-shot evaluation across
        22 diverse benchmarks from the DCLM paper (HellaSwag, ARC, BoolQ,
        LAMBADA, TriviaQA, ...). The target is 0.256525 (GPT-2's score).
        A successful d24 speedrun hits ~0.258-0.260. Takes ~20-40 min.

    The eval bundle (benchmark data files, ~1GB) is downloaded on first run
    and cached in the volume for subsequent runs.
    """
    _setup_cache()

    # speedrun.sh:
    #   if [ ! -d "$NANOCHAT_BASE_DIR/eval_bundle" ]; then
    #       curl -L -o eval_bundle.zip $EVAL_BUNDLE_URL && unzip -q ...
    eval_bundle_dir = os.path.join(NANOCHAT_CACHE, "eval_bundle")
    if not os.path.isdir(eval_bundle_dir):
        print("Downloading eval bundle (~1GB)...")
        zip_path = "/tmp/eval_bundle.zip"
        _curl(EVAL_BUNDLE_URL, zip_path)
        _run(f"unzip -q {zip_path} -d {NANOCHAT_CACHE} && rm {zip_path}")
        volume.commit()

    # speedrun.sh: torchrun ... -m scripts.base_eval
    print("Running CORE evaluation (22 benchmarks, ~20-40 min)...")
    _torchrun("scripts.base_eval", nproc=_N_PRETRAIN_GPUS)

    volume.commit()
    print("Post-pretrain eval complete.")


# =============================================================================
# PART 3: CONTEXT EXTENSION CURRICULUM (checkpoint 1 -> checkpoint 2)
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu=GPU_PRETRAIN,
    timeout=PRETRAIN_TIMEOUT_SEC,
)
def stage_part3_short_context(
    depth: int = DEPTH,
    device_batch_size: int = DEVICE_BATCH_SIZE,
    use_swiglu: bool = False,
    short_seq_len: int = PART3_SHORT_SEQ_LEN,
    short_num_iterations: int = PART3_SHORT_NUM_ITERATIONS,
    wandb_run: str = PART3_SHORT_WANDB_RUN,
    model_tag: str = "",
) -> None:
    """
    Part 3 checkpoint 1: train with reduced context length (e.g., 512).

    This stage uses a reduced sequence length and reduced training horizon
    (`num_iterations`) to represent training on a portion of the total budget.
    """
    _setup_cache()
    resolved_model_tag = model_tag or _part3_model_tag(depth, use_swiglu)
    save_every = max(100, short_num_iterations // 2)
    print(
        f"Part 3 / stage A: short-context pretrain "
        f"(seq={short_seq_len}, steps={short_num_iterations}, tag={resolved_model_tag})"
    )
    _torchrun(
        "scripts.base_train",
        [
            f"--depth={depth}",
            f"--device-batch-size={device_batch_size}",
            f"--run={wandb_run}",
            f"--model-tag={resolved_model_tag}",
            f"--max-seq-len={short_seq_len}",
            f"--num-iterations={short_num_iterations}",
            f"--save-every={save_every}",
        ]
        + (["--use-swiglu"] if use_swiglu else []),
        nproc=_N_PRETRAIN_GPUS,
    )
    volume.commit()
    print(
        f"Part 3 checkpoint 1 complete: model_tag={resolved_model_tag}, "
        f"step={short_num_iterations}"
    )


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu=GPU_PRETRAIN,
    timeout=PRETRAIN_TIMEOUT_SEC,
)
def stage_part3_extend_context(
    depth: int = DEPTH,
    device_batch_size: int = DEVICE_BATCH_SIZE,
    use_swiglu: bool = False,
    short_seq_len: int = PART3_SHORT_SEQ_LEN,
    long_seq_len: int = PART3_LONG_SEQ_LEN,
    resume_step: int = PART3_SHORT_NUM_ITERATIONS,
    long_additional_iterations: int = PART3_LONG_ADDITIONAL_ITERATIONS,
    wandb_run: str = PART3_LONG_WANDB_RUN,
    model_tag: str = "",
) -> None:
    """
    Part 3 checkpoint 2: resume from short-context checkpoint and continue at 2048.

    The model tag is kept identical so `--resume-from-step` loads checkpoint 1
    and continues optimization with a larger `--max-seq-len`.
    """
    _setup_cache()
    resolved_model_tag = model_tag or _part3_model_tag(depth, use_swiglu)
    total_iterations = resume_step + long_additional_iterations
    save_every = max(100, long_additional_iterations // 2)
    print(
        f"Part 3 / stage B: context extension "
        f"(resume_step={resume_step}, seq {short_seq_len}->{long_seq_len}, "
        f"target_step={total_iterations}, tag={resolved_model_tag})"
    )
    _torchrun(
        "scripts.base_train",
        [
            f"--depth={depth}",
            f"--device-batch-size={device_batch_size}",
            f"--run={wandb_run}",
            f"--model-tag={resolved_model_tag}",
            f"--max-seq-len={long_seq_len}",
            f"--resume-from-step={resume_step}",
            f"--num-iterations={total_iterations}",
            f"--save-every={save_every}",
        ]
        + (["--use-swiglu"] if use_swiglu else []),
        nproc=_N_PRETRAIN_GPUS,
    )
    volume.commit()
    print(
        f"Part 3 checkpoint 2 complete: model_tag={resolved_model_tag}, "
        f"step={total_iterations}"
    )


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu=GPU_FINETUNE,
    timeout=60 * 60,
)
def stage_part3_eval_compare(
    depth: int = DEPTH,
    use_swiglu: bool = False,
    checkpoint1_step: int = PART3_SHORT_NUM_ITERATIONS,
    checkpoint2_step: int = (
        PART3_SHORT_NUM_ITERATIONS + PART3_LONG_ADDITIONAL_ITERATIONS
    ),
    device_batch_size: int = DEVICE_BATCH_SIZE,
    split_tokens: int = PART3_EVAL_SPLIT_TOKENS,
    task_label: str = PART3_TASK_LABEL,
    task_max_problems: int = PART3_TASK_MAX_PROBLEMS,
    model_tag: str = "",
) -> None:
    """
    Compare checkpoint 1 vs checkpoint 2 on:
      1) BPB (train/val split)
      2) A chosen CORE task (default: hellaswag_zeroshot)
    """
    _setup_cache()
    resolved_model_tag = model_tag or _part3_model_tag(depth, use_swiglu)

    common_args = [
        "--eval=core,bpb",
        f"--model-tag={resolved_model_tag}",
        f"--device-batch-size={device_batch_size}",
        f"--split-tokens={split_tokens}",
        f"--max-per-task={task_max_problems}",
    ]

    print(
        f"Evaluating Part 3 checkpoint 1 (step={checkpoint1_step}) "
        f"on BPB with model_tag={resolved_model_tag}"
    )
    _torchrun(
        "scripts.base_eval",
        common_args + [f"--step={checkpoint1_step}"],
        nproc=_N_FINETUNE_GPUS,
    )
    _print_core_task_from_csv(checkpoint1_step, task_label)

    print(
        f"Evaluating Part 3 checkpoint 2 (step={checkpoint2_step}) "
        f"on BPB with model_tag={resolved_model_tag}"
    )
    _torchrun(
        "scripts.base_eval",
        common_args + [f"--step={checkpoint2_step}"],
        nproc=_N_FINETUNE_GPUS,
    )
    _print_core_task_from_csv(checkpoint2_step, task_label)
    print("Part 3 comparison eval complete.")


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu=GPU_FINETUNE,
    timeout=60 * 60,
)
def stage_part3_eval_longprompts_compare(
    depth: int = DEPTH,
    use_swiglu: bool = False,
    checkpoint1_step: int = PART3_SHORT_NUM_ITERATIONS,
    checkpoint2_step: int = (
        PART3_SHORT_NUM_ITERATIONS + PART3_LONG_ADDITIONAL_ITERATIONS
    ),
    task_label: str = PART3_CUSTOM_TASK_LABEL,
    min_prompt_tokens: int = PART3_CUSTOM_MIN_PROMPT_TOKENS,
    max_problems: int = PART3_CUSTOM_MAX_PROBLEMS,
    model_tag: str = "",
) -> None:
    """
    Custom Part 3 eval:
    Compare ckpt1 vs ckpt2 on one CORE task, but only for long prompts.

    Uses scripts/part3_eval_longprompts.py and keeps existing pipeline untouched.
    """
    _setup_cache()
    resolved_model_tag = model_tag or _part3_model_tag(depth, use_swiglu)

    print(
        f"Custom long-prompt eval ckpt1 step={checkpoint1_step} "
        f"task={task_label} min_prompt_tokens={min_prompt_tokens}"
    )
    _torchrun(
        "scripts.part3_eval_longprompts",
        [
            f"--model-tag={resolved_model_tag}",
            f"--step={checkpoint1_step}",
            f"--task-label={task_label}",
            f"--min-prompt-tokens={min_prompt_tokens}",
            f"--max-problems={max_problems}",
        ],
        nproc=_N_FINETUNE_GPUS,
    )

    print(
        f"Custom long-prompt eval ckpt2 step={checkpoint2_step} "
        f"task={task_label} min_prompt_tokens={min_prompt_tokens}"
    )
    _torchrun(
        "scripts.part3_eval_longprompts",
        [
            f"--model-tag={resolved_model_tag}",
            f"--step={checkpoint2_step}",
            f"--task-label={task_label}",
            f"--min-prompt-tokens={min_prompt_tokens}",
            f"--max-problems={max_problems}",
        ],
        nproc=_N_FINETUNE_GPUS,
    )
    print("Part 3 custom long-prompt comparison eval complete.")


# =============================================================================
# UTILS
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    cpu=2,
    memory=2048,
    timeout=60 * 10,
)
def stage_list_checkpoints() -> None:
    """List available base checkpoint tags and step files in the Modal volume."""
    _setup_cache()
    base_ckpt_dir = os.path.join(NANOCHAT_CACHE, "base_checkpoints")
    print(f"Base checkpoints dir: {base_ckpt_dir}")
    if not os.path.isdir(base_ckpt_dir):
        print("No base_checkpoints directory found yet.")
        return

    tags = sorted(
        [
            d
            for d in os.listdir(base_ckpt_dir)
            if os.path.isdir(os.path.join(base_ckpt_dir, d))
        ]
    )
    if not tags:
        print("No checkpoint tags found.")
        return

    for tag in tags:
        tag_dir = os.path.join(base_ckpt_dir, tag)
        model_files = sorted(
            [f for f in os.listdir(tag_dir) if f.startswith("model_") and f.endswith(".pt")]
        )
        steps = [f.removeprefix("model_").removesuffix(".pt") for f in model_files]
        print("-" * 80)
        print(f"tag: {tag}")
        print(f"steps ({len(steps)}): {', '.join(steps[:20])}{' ...' if len(steps) > 20 else ''}")
        if steps:
            print(f"latest: {steps[-1]}")


# =============================================================================
# STAGE 4: SUPERVISED FINE-TUNING (SFT)
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu=GPU_FINETUNE,
    timeout=FINETUNE_TIMEOUT_SEC,
)
def stage_sft(
    wandb_run: str = WANDB_RUN,
    depth: int = DEPTH,
    use_swiglu: bool = False,
    model_step: int | None = None,
    model_tag: str = "",
) -> None:
    """
    Supervised fine-tuning: teach the model to follow chat instructions.

    speedrun.sh:
        curl -L -o $NANOCHAT_BASE_DIR/identity_conversations.jsonl $IDENTITY_URL
        torchrun ... -m scripts.chat_sft -- --run=$WANDB_RUN
        torchrun ... -m scripts.chat_eval -- -i sft

    chat_sft trains on a curated mixture of conversation data with loss masked
    to assistant-only tokens. This is the key structural difference from
    pretraining: the model sees the full context (user + assistant turns) but
    only gets gradient signal from its own tokens. User prompt tokens have
    their targets set to -1, which F.cross_entropy ignores.

    Data mixture includes:
        - SmolTalk:   ~460K general conversations (dominant)
        - MMLU:       ~100K multiple-choice knowledge questions
        - ARC:        ~8K science reasoning questions
        - GSM8K:      math word problems with calculator tool use
        - HumanEval:  Python coding tasks
        - identity_conversations.jsonl: synthetic data teaching self-awareness

    identity_conversations.jsonl is downloaded fresh each time from Karpathy's
    S3. It's a small file (~a few hundred rows) that teaches the model its name,
    creator, and basic facts about itself. See dev/gen_synthetic_data.py for how
    to generate your own custom version.

    chat_eval -i sft runs task-specific evals (GSM8K accuracy, HumanEval pass@1,
    MMLU accuracy) on the SFT checkpoint and appends results to the report.
    """
    _setup_cache()

    # speedrun.sh: curl -L -o $NANOCHAT_BASE_DIR/identity_conversations.jsonl $URL
    identity_dest = os.path.join(NANOCHAT_CACHE, "identity_conversations.jsonl")
    print("Downloading identity conversations for SFT personality layer...")
    _curl(IDENTITY_JSONL_URL, identity_dest)

    # speedrun.sh: torchrun ... -m scripts.chat_sft -- --run=$WANDB_RUN
    print("Running SFT...")
    resolved_model_tag = model_tag or _base_model_tag(depth, use_swiglu)
    sft_args = [
        f"--run={wandb_run}",
        f"--model-tag={resolved_model_tag}",
    ]
    if model_step is not None:
        sft_args.append(f"--model-step={model_step}")
    _torchrun(
        "scripts.chat_sft",
        sft_args,
        nproc=_N_FINETUNE_GPUS,
    )

    # speedrun.sh: torchrun ... -m scripts.chat_eval -- -i sft
    # -i sft tells chat_eval to load the SFT checkpoint (not base or rl)
    print("Evaluating SFT checkpoint on task benchmarks...")
    _torchrun(
        "scripts.chat_eval",
        [
            "-i",
            "sft",
        ],
        nproc=_N_FINETUNE_GPUS,
    )

    volume.commit()
    print("SFT complete.")


# =============================================================================
# STAGE 5: REINFORCEMENT LEARNING (optional)
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu=GPU_FINETUNE,
    timeout=FINETUNE_TIMEOUT_SEC,
)
def stage_rl(
    wandb_run: str = WANDB_RUN,
    depth: int = DEPTH,
    use_swiglu: bool = False,
    model_step: int | None = None,
    model_tag: str = "",
) -> None:
    """
    Optional RL stage to boost math reasoning on GSM8K.

    speedrun.sh:
        torchrun ... -m scripts.chat_rl -- --run=$WANDB_RUN
        torchrun ... -m scripts.chat_eval -- -i rl

    Uses a simplified GRPO/REINFORCE variant trained on GSM8K math word
    problems. The model generates multiple candidate answers, checks each
    against the ground truth integer, and uses correct/incorrect as a binary
    reward signal. No value network, no KL penalty against the SFT reference.

    From the source comment: "I put GRPO in quotes because we actually end up
    with something a lot simpler and more similar to just REINFORCE."

    Expected improvement: GSM8K accuracy ~5% (SFT) -> ~15-20% (after RL).

    This stage is NOT part of the default speedrun.sh -- it's an optional
    extension. Run it separately after stage_sft:
        modal run nanochat_modal.py::stage_rl
    """
    _setup_cache()

    print("Running RL (GRPO on GSM8K)...")
    # speedrun.sh: torchrun ... -m scripts.chat_rl -- --run=$WANDB_RUN
    resolved_model_tag = model_tag or _base_model_tag(depth, use_swiglu)
    rl_args = [
        f"--run={wandb_run}",
        f"--model-tag={resolved_model_tag}",
    ]
    if model_step is not None:
        rl_args.append(f"--model-step={model_step}")
    _torchrun(
        "scripts.chat_rl",
        rl_args,
        nproc=_N_FINETUNE_GPUS,
    )

    # speedrun.sh: torchrun ... -m scripts.chat_eval -- -i rl
    print("Evaluating RL checkpoint...")
    _torchrun("scripts.chat_eval", ["-i", "rl"], nproc=_N_FINETUNE_GPUS)

    volume.commit()
    print("RL complete.")


# =============================================================================
# FULL SPEEDRUN PIPELINE (main entrypoint)
# =============================================================================


@app.local_entrypoint()
def main(
    use_swiglu: bool = False,
    depth: int = DEPTH,
    num_shards: int = NUM_SHARDS,
    device_batch_size: int = DEVICE_BATCH_SIZE,
    wandb_run: str = WANDB_RUN,
    sft_model_step: int | None = None,
) -> None:
    """
    Run the complete speedrun pipeline, mirroring runs/speedrun.sh end-to-end.

    This is what executes when you run: modal run nanochat_modal.py

    Stage order (matches speedrun.sh top to bottom):
        0. Download FineWeb-EDU shards       (CPU, ~20 min for 240 shards)
        1. Train BPE tokenizer               (1 GPU, ~2 min)
        2. Pretrain base model               (8 GPU, ~3 hours for d24)
        3. Post-pretrain eval (loss + CORE)  (8 GPU, ~30 min)
        4. SFT + chat_eval                   (4 GPU, ~30-45 min)
        5. Chat sample                       (1 GPU, ~1 min)

    Each stage is a separate Modal function call with its own container, GPU
    allocation, and log stream. If a stage fails, re-run it individually:
        modal run nanochat_modal.py::stage_pretrain

    The optional RL stage is NOT included in the default pipeline. Run it
    manually after stage_sft if you want the math reasoning boost:
        modal run nanochat_modal.py::stage_rl
    """
    w = 64
    print("\n" + "=" * w)
    print("nanochat Speedrun -- Modal Edition")
    print(f"  Mirrors: runs/speedrun.sh")
    print(
        f"  depth={depth}  shards={num_shards}  gpu={GPU_PRETRAIN}  wandb={wandb_run}"
    )
    print(
        f"  arch={'swiglu' if use_swiglu else 'relu2'}  model_tag={_base_model_tag(depth, use_swiglu)}"
    )
    print("=" * w + "\n")

    # Stage 0: Data
    # speedrun.sh: python -m nanochat.dataset -n 240
    print("[0/5] Downloading FineWeb-EDU shards...")
    stage_data.remote(num_shards=num_shards)

    # Stage 1: Tokenizer
    # speedrun.sh: python -m scripts.tok_train && python -m scripts.tok_eval
    print("[1/5] Training tokenizer...")
    stage_tokenizer.remote()

    # Stage 2: Pretrain
    # speedrun.sh: python -m nanochat.report reset
    #              torchrun ... -m scripts.base_train -- --depth=24 ...
    print("[2/5] Pretraining base model (the long one)...")
    stage_pretrain.remote(
        depth=depth,
        device_batch_size=device_batch_size,
        wandb_run=wandb_run,
        use_swiglu=use_swiglu,
    )

    # Stage 3: Post-pretrain eval
    #              torchrun ... -m scripts.base_eval
    print("[3/5] Evaluating base model (bits-per-byte + CORE)...")
    stage_post_pretrain_eval.remote()

    # Stage 4: SFT + eval
    # speedrun.sh: curl identity_conversations.jsonl
    #              torchrun ... -m scripts.chat_sft -- --run=...
    #              torchrun ... -m scripts.chat_eval -- -i sft
    print("[4/5] Supervised fine-tuning + eval...")
    stage_sft.remote(
        wandb_run=wandb_run,
        depth=depth,
        use_swiglu=use_swiglu,
        model_step=sft_model_step,
    )

    print("\n" + "=" * w)
    print("Speedrun complete!")
    print("  Checkpoints + report are in the 'nanochat-vol' Modal Volume.")
    print("  Optional RL stage: modal run nanochat_modal.py::stage_rl")
    print("=" * w + "\n")


# =============================================================================
# PART 3 ENTRYPOINT
# =============================================================================


@app.local_entrypoint()
def part3(
    use_swiglu: bool = False,
    depth: int = DEPTH,
    num_shards: int = PART3_NUM_SHARDS,
    device_batch_size: int = DEVICE_BATCH_SIZE,
    short_seq_len: int = PART3_SHORT_SEQ_LEN,
    long_seq_len: int = PART3_LONG_SEQ_LEN,
    short_num_iterations: int = PART3_SHORT_NUM_ITERATIONS,
    long_additional_iterations: int = PART3_LONG_ADDITIONAL_ITERATIONS,
    short_wandb_run: str = PART3_SHORT_WANDB_RUN,
    long_wandb_run: str = PART3_LONG_WANDB_RUN,
    task_label: str = PART3_TASK_LABEL,
    task_max_problems: int = PART3_TASK_MAX_PROBLEMS,
) -> None:
    """
    Run Part 3 end-to-end:
      1) short-context training (checkpoint 1)
      2) long-context continuation (checkpoint 2)
      3) checkpoint comparison on BPB
    """
    w = 72
    model_tag = _part3_model_tag(depth, use_swiglu)
    ckpt2_step = short_num_iterations + long_additional_iterations
    print("\n" + "=" * w)
    print("nanochat Part 3 -- Context Extension Curriculum")
    print(
        f"  depth={depth}  shards={num_shards}  short_seq={short_seq_len}  long_seq={long_seq_len}"
    )
    print(
        f"  short_steps={short_num_iterations}  long_extra_steps={long_additional_iterations}"
    )
    print(f"  arch={'swiglu' if use_swiglu else 'relu2'}  model_tag={model_tag}")
    print(f"  task_eval={task_label}  max_problems={task_max_problems}")
    print("=" * w + "\n")

    print("[0/4] Ensuring dataset shards and tokenizer are ready...")
    stage_data.remote(num_shards=num_shards)
    stage_tokenizer.remote()

    print("[1/4] Training short-context checkpoint (checkpoint 1)...")
    stage_part3_short_context.remote(
        depth=depth,
        device_batch_size=device_batch_size,
        use_swiglu=use_swiglu,
        short_seq_len=short_seq_len,
        short_num_iterations=short_num_iterations,
        wandb_run=short_wandb_run,
        model_tag=model_tag,
    )

    print("[2/4] Extending context and continuing training (checkpoint 2)...")
    stage_part3_extend_context.remote(
        depth=depth,
        device_batch_size=device_batch_size,
        use_swiglu=use_swiglu,
        short_seq_len=short_seq_len,
        long_seq_len=long_seq_len,
        resume_step=short_num_iterations,
        long_additional_iterations=long_additional_iterations,
        wandb_run=long_wandb_run,
        model_tag=model_tag,
    )

    print("[3/4] Comparing checkpoint 1 vs checkpoint 2 on BPB + task eval...")
    stage_part3_eval_compare.remote(
        depth=depth,
        use_swiglu=use_swiglu,
        checkpoint1_step=short_num_iterations,
        checkpoint2_step=ckpt2_step,
        device_batch_size=device_batch_size,
        task_label=task_label,
        task_max_problems=task_max_problems,
        model_tag=model_tag,
    )

    print("\n" + "=" * w)
    print("Part 3 pipeline complete.")
    print(f"  Checkpoint 1: model_tag={model_tag}, step={short_num_iterations}")
    print(f"  Checkpoint 2: model_tag={model_tag}, step={ckpt2_step}")
    print("=" * w + "\n")


# =============================================================================
# QUICK TEST
# =============================================================================


@app.function(
    image=image,
    secrets=[secret],
    volumes={VOLUME_MOUNT: volume},
    gpu="H100:4",
    timeout=60 * 60 * 2,
)
def quick_test() -> None:
    """
    End-to-end smoke test using a tiny d12 model and only 8 data shards.

    d12 = 12-layer transformer, ~125M params (GPT-1 scale).
    Downloads only 8 shards (~800MB), trains in ~5 min on 4xH100.

    If this passes without errors, you know:
        - The container image built correctly (Rust/uv/maturin all work)
        - The volume mount is working (data persists)
        - The secret injection is working (HF_TOKEN for download)
        - torchrun multi-GPU distributed training works
        - The full code path from data -> tokenizer -> pretrain -> SFT -> chat runs
    """
    _setup_cache()

    nproc = 4

    # 1. Download a handful of shards to get data on the volume
    print("Downloading 8 shards for quick test...")
    _python("nanochat.dataset", ["-n 8"])
    volume.commit()

    # 2. Train tokenizer on 500M chars instead of 2B (much faster)
    print("Training tokenizer (500M chars)...")
    _python("scripts.tok_train", ["--max-chars=500000000"])
    _python("scripts.tok_eval")

    # 3. Quick pretrain: d12, skip CORE metric (slow), skip intermediate saves
    print("Pretraining d12 (no CORE metric, no intermediate saves)...")
    _torchrun(
        "scripts.base_train",
        [
            "--depth=12",
            "--device-batch-size=32",
            "--run=dummy",
            "--core-metric-every=999999",  # skip CORE during training (it's slow)
            "--sample-every=-1",  # skip intermediate samples
            "--save-every=-1",  # skip intermediate checkpoints
        ],
        nproc=nproc,
    )

    # 4. Minimal SFT to verify the code path runs end-to-end
    print("Quick SFT...")
    identity_dest = os.path.join(NANOCHAT_CACHE, "identity_conversations.jsonl")
    _curl(IDENTITY_JSONL_URL, identity_dest)
    _torchrun("scripts.chat_sft", ["--run=dummy"], nproc=nproc)

    # 5. Chat sample to confirm inference works
    print("Chat sample...")
    _python("scripts.chat_cli", ['-p "Hello, who are you?"', "-i sft"])

    volume.commit()
    print("\nQuick test passed! Ready for the full speedrun.")
