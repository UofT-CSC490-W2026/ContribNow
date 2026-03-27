# ETL Profiling Guide

This project uses an in-process profiler for ETL stages so we can capture Python call stacks (as opposed to timing only subprocess boundaries). The script below runs ingest, transform, and load directly in Python and stores `.prof` files for later comparison.

## Why in-process profiling

The existing runner in `scripts/run_pipeline.py` launches each stage in a subprocess. That is fine for normal runs, but it hides function-level timings from `cProfile`. The profiling script calls `ingest_repos()`, `transform_repo()`, and `load_artifact()` directly so we can see where time is spent inside each stage.

## Primary targets (one per stage)

These are the default focus points when reading profiler output:

- Ingest: `src.pipeline.ingest._list_files` (repo walk + hashing)
- Ingest (optional swap-in): `src.pipeline.ingest._build_commit_log` (git history parsing)
- Transform: `src.pipeline.transform._compute_co_change_matrix` (pair counting)
- Load: `src.pipeline.load.load_artifact` (snapshot + index generation)

If you are profiling different functions (RAG, backend, or AST parsing), keep the same script and replace your analysis section with your target functions.

## Script usage

The profiling script is `profiles/profile_etl.py`.

## Shared format (for non-ETL profiling)

If you are profiling non-ETL code (RAG, backend, AST experiments), keep the same *format* so results are comparable across the team:

- Put new profiling scripts under `profiles/` (e.g., `profiles/profile_rag.py`, `profiles/profile_backend.py`).
- Accept `--run-id` and write profiler dumps as `.prof` files under `data/profiles_<run_id>/`.
- Run the code *in-process* under `cProfile` (avoid profiling only subprocess boundaries).
- Print the “top N cumulative” rows to stdout (same columns + sorting).

You can copy the helper pattern from `profiles/profile_etl.py` (the `_profile_call(...)` wrapper and the `data/*_<run_id>` folder naming).

### Medium run (2 repos)

```
python profiles/profile_etl.py \
  --repo https://github.com/pallets/click \
  --repo https://github.com/pallets/markupsafe \
  --run-id profile_click_markupsafe_2 \
  --depth 200
```

Outputs:
- `data/raw_<run_id>`
- `data/transform_<run_id>`
- `data/output_<run_id>`
- `data/profiles_<run_id>/{ingest,transform,load}.prof`

### Reuse existing raw artifacts (transform + load only)

```
python profiles/profile_etl.py \
  --skip-ingest \
  --raw-root data/raw_profile_click_1 \
  --run-id profile_click_1_transform_only
```

### Transform-only example

```
python profiles/profile_etl.py \
  --skip-ingest \
  --skip-load \
  --raw-root data/raw_profile_click_1 \
  --run-id profile_click_1_transform_only
```

## Reading the output

Each stage prints the top cumulative functions and writes a `.prof` file. Use cumulative time to find total time spent in a function including callees. Use `tottime` when you want to focus on a function's own body.

You can also inspect a profile interactively:

```
python -m pstats data/profiles_profile_click_1/transform.prof
```

Inside `pstats`, useful commands include:
- `sort cumulative`
- `stats 20`
- `callers <function>`
- `callees <function>`

## Analysis template (for the write-up)

Copy/paste this template and fill it in per stage or per target function:

- Run id:
- Stage profiled:
- Target functions:
- Top 10 cumulative functions:
- Where the targets appear in the list:
- Hypothesis for improvement:
- Change made (if any):
- Before/after timing delta:

## Tips

- Keep runs small and repeatable: 1-2 repos, shallow clone depth.
- Reuse the same run id naming scheme for before/after comparisons.
- The script disables cloud sync by default, so load stays local-only.
