import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from src.pipeline.utils import utc_now


def _run_git(args: list[str], cwd: Path) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return process.stdout


def _build_structure_summary(files: list[str]) -> dict[str, object]:
    top_level_counts: Counter[str] = Counter()
    file_type_counts: Counter[str] = Counter()

    for file_path in files:
        path = Path(file_path)
        top_level = path.parts[0] if len(path.parts) > 1 else "."
        top_level_counts[top_level] += 1
        ext = path.suffix.lower()
        file_type_counts[ext if ext else "[no_ext]"] += 1

    return {
        "total_files": len(files),
        "top_level_directories": [
            {"path": path, "file_count": count}
            for path, count in sorted(top_level_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "file_type_counts": [
            {"extension": ext, "count": count}
            for ext, count in sorted(file_type_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "start_here_candidates": _find_start_here_candidates(files),
    }


def _find_start_here_candidates(files: list[str]) -> list[dict[str, object]]:
    patterns: list[tuple[re.Pattern[str], str, int]] = [
        (re.compile(r"(?i)^readme(\..+)?$"), "project_overview", 100),
        (re.compile(r"(?i)^contributing(\..+)?$"), "contribution_guidelines", 95),
        (re.compile(r"(?i)^docs?/"), "documentation", 90),
        (re.compile(r"(?i)^pyproject\.toml$"), "python_project_config", 85),
        (re.compile(r"(?i)^package\.json$"), "node_project_config", 85),
        (re.compile(r"(?i)^makefile$"), "build_entrypoint", 80),
        (re.compile(r"(?i)^dockerfile$"), "runtime_entrypoint", 75),
        (re.compile(r"(?i)^src/main\."), "application_entrypoint", 75),
        (re.compile(r"(?i)^src/app\."), "application_entrypoint", 70),
        (re.compile(r"(?i)^tests?/"), "test_suite", 70),
        (re.compile(r"(?i)^\.github/workflows/"), "ci_workflow", 68),
    ]

    skip_extensions = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg", ".tiff",
        ".mp4", ".avi", ".mov", ".mkv", ".mp3", ".wav", ".flac", ".ogg",
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
        ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".class", ".o", ".a",
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".bin", ".dat", ".db", ".sqlite", ".wasm",
    }

    scored: list[tuple[int, str, list[str]]] = []
    for file_path in files:
        norm = file_path.replace("\\", "/")
        if Path(norm).suffix.lower() in skip_extensions:
            continue
        reasons: list[str] = []
        score = 0
        for pattern, reason, points in patterns:
            if pattern.search(norm):
                reasons.append(reason)
                score += points
        if reasons:
            scored.append((score, norm, sorted(set(reasons))))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{"path": path, "score": score, "reasons": reasons} for score, path, reasons in scored[:15]]



def _compute_hotspots_from_commits(
    commits: list[dict[str, object]], top_n: int
) -> list[dict[str, object]]:
    """Rank files by how many commits touched them."""
    touch_counter: Counter[str] = Counter()
    last_touched: dict[str, str] = {}
    for commit in commits:
        date = str(commit.get("date", ""))
        for file_path in commit["files"]:  # type: ignore[union-attr]
            fp = str(file_path)
            touch_counter[fp] += 1
            if fp not in last_touched:
                last_touched[fp] = date
    ranked = sorted(touch_counter.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    return [
        {"path": path, "touch_count": touches, "last_touched": last_touched.get(path)}
        for path, touches in ranked
    ]


MAX_FILES_PER_COMMIT = 50


def _compute_co_change_matrix(
    commits: list[dict[str, object]], min_threshold: int = 3
) -> list[dict[str, object]]:
    """
    Count how many times each file pair is modified in the same commit.
    Only pairs with co_change_count >= min_threshold are returned.
    Commits touching more than MAX_FILES_PER_COMMIT files are skipped
    (bulk changes like formatting or dependency bumps are noise).
    """
    pair_counter: Counter[tuple[str, str]] = Counter()
    for commit in commits:
        files = sorted(set(str(f) for f in commit["files"]))  # type: ignore[union-attr]
        if len(files) > MAX_FILES_PER_COMMIT:
            continue
        for i, file_a in enumerate(files):
            for file_b in files[i + 1:]:
                pair_counter[(file_a, file_b)] += 1
    return [
        {"file_a": a, "file_b": b, "co_change_count": count}
        for (a, b), count in sorted(pair_counter.items(), key=lambda x: (-x[1], x[0][0]))
        if count >= min_threshold
    ]


def _compute_authorship(
    commits: list[dict[str, object]], files: list[str]
) -> list[dict[str, object]]:
    """
    For each file, count how many commits have touched it and which authors
    contributed, ordered by commit count.
    """
    file_set = set(files)
    file_commit_counts: dict[str, int] = {}
    file_author_counts: dict[str, Counter[str]] = {}

    for commit in commits:
        author = str(commit.get("author", ""))
        for file_path in commit["files"]:  # type: ignore[union-attr]
            fp = str(file_path)
            if fp not in file_set:
                continue
            file_commit_counts[fp] = file_commit_counts.get(fp, 0) + 1
            if fp not in file_author_counts:
                file_author_counts[fp] = Counter()
            file_author_counts[fp][author] += 1

    result: list[dict[str, object]] = []
    for path in files:
        if path not in file_commit_counts:
            continue
        author_counts = file_author_counts.get(path, Counter())
        result.append(
            {
                "path": path,
                "total_commits": file_commit_counts[path],
                "distinct_authors": len(author_counts),
                "primary_contributors": [
                    {"name": name, "commit_count": count}
                    for name, count in author_counts.most_common(3)
                ],
            }
        )
    return result


def _compute_risk_levels(
    hotspots: list[dict[str, object]],
    co_change_pairs: list[dict[str, object]],
    authorship: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    Assign a risk level to each hotspot file by combining three signals:
      - churn  (touch_count)         weight 50%
      - author diversity             weight 30%
      - co-change coupling degree    weight 20%

    Each signal is min-max normalised within the hotspot set.
    Thresholds: high > 0.7, medium >= 0.4, low < 0.4.
    """
    if not hotspots:
        return []

    author_map = {str(a["path"]): a for a in authorship}
    coupling_degree: Counter[str] = Counter()
    for pair in co_change_pairs:
        coupling_degree[str(pair["file_a"])] += 1
        coupling_degree[str(pair["file_b"])] += 1

    churn_vals = [int(h["touch_count"]) for h in hotspots]  # type: ignore[arg-type]
    author_vals = [
        int(author_map.get(str(h["path"]), {}).get("distinct_authors", 1))
        for h in hotspots
    ]
    coupling_vals = [coupling_degree.get(str(h["path"]), 0) for h in hotspots]

    def _norm(vals: list[int]) -> list[float]:
        mn, mx = min(vals), max(vals)
        return [0.5] * len(vals) if mx == mn else [(v - mn) / (mx - mn) for v in vals]

    n_churn = _norm(churn_vals)
    n_authors = _norm(author_vals)
    n_coupling = _norm(coupling_vals)

    result: list[dict[str, object]] = []
    for i, hotspot in enumerate(hotspots):
        score = 0.5 * n_churn[i] + 0.3 * n_authors[i] + 0.2 * n_coupling[i]
        level = "high" if score > 0.7 else ("medium" if score >= 0.4 else "low")
        result.append(
            {
                "path": hotspot["path"],
                "risk_level": level,
                "risk_score": round(score, 4),
                "factors": {
                    "touch_count": churn_vals[i],
                    "distinct_authors": author_vals[i],
                    "co_change_degree": coupling_vals[i],
                },
            }
        )
    return result


def _detect_conventions(files: list[str], repo_checkout: Path) -> dict[str, object]:
    """
    Detect testing frameworks, linters, CI pipelines, contribution docs and
    package managers by scanning well-known config file patterns.
    """
    file_lower = {f.lower(): f for f in files}

    def _read(rel_path: str) -> str:
        try:
            return (repo_checkout / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def _any_match(names: list[str]) -> str | None:
        for name in names:
            if name in file_lower:
                return file_lower[name]
            match = next((orig for low, orig in file_lower.items() if low.endswith(f"/{name}")), None)
            if match:
                return match
        return None

    # --- Test framework ---
    test_framework: dict[str, object] | None = None
    if (cfg := _any_match(["pytest.ini"])):
        test_framework = {"name": "pytest", "config_path": cfg}
    elif "pyproject.toml" in file_lower:
        pyproject_path = file_lower["pyproject.toml"]
        if "[tool.pytest.ini_options]" in _read(pyproject_path):
            test_framework = {"name": "pytest", "config_path": pyproject_path}
    if test_framework is None and (cfg := _any_match(["setup.cfg"])):
        if "[tool:pytest]" in _read(cfg):
            test_framework = {"name": "pytest", "config_path": cfg}
    for jest_cfg in ("jest.config.js", "jest.config.ts", "jest.config.mjs", "jest.config.cjs"):
        if (cfg := _any_match([jest_cfg])):
            test_framework = {"name": "jest", "config_path": cfg}
            break

    # --- Linters / formatters ---
    linters: list[dict[str, object]] = []
    linter_patterns: list[tuple[str, list[str]]] = [
        ("editorconfig", [".editorconfig"]),
        ("ruff", ["ruff.toml", ".ruff.toml"]),
        ("flake8", [".flake8"]),
        ("eslint", [".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml"]),
        ("prettier", [".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.yml"]),
    ]
    for linter_name, cfg_names in linter_patterns:
        if (cfg := _any_match(cfg_names)):
            linters.append({"name": linter_name, "config_path": cfg})
    if "pyproject.toml" in file_lower:
        pyproject_path = file_lower["pyproject.toml"]
        content = _read(pyproject_path)
        if "[tool.ruff]" in content and not any(l["name"] == "ruff" for l in linters):
            linters.append({"name": "ruff", "config_path": pyproject_path})
        if "[tool.black]" in content:
            linters.append({"name": "black", "config_path": pyproject_path})

    # --- CI / CD ---
    ci_pipelines: list[dict[str, object]] = []
    ci_patterns: list[tuple[str, str]] = [
        ("github_actions", ".github/workflows/"),
        ("gitlab_ci", ".gitlab-ci.yml"),
        ("jenkins", "jenkinsfile"),
        ("circleci", ".circleci/"),
        ("travis_ci", ".travis.yml"),
    ]
    for platform, marker in ci_patterns:
        match = next(
            (orig for low, orig in file_lower.items()
             if low.startswith(marker) or low == marker),
            None,
        )
        if match:
            ci_pipelines.append({"platform": platform, "config_path": match})

    # --- Contribution docs ---
    contribution_doc_names = {
        "contributing.md", "contributing.rst", "contributing.txt",
        "code_of_conduct.md", "pull_request_template.md",
    }
    contribution_docs = [
        orig for low, orig in file_lower.items()
        if Path(low).name in contribution_doc_names
    ]

    # --- Package manager ---
    package_manager: str | None = None
    for lockfile, mgr in [
        ("poetry.lock", "poetry"), ("pipfile.lock", "pipenv"),
        ("package-lock.json", "npm"), ("yarn.lock", "yarn"),
        ("pnpm-lock.yaml", "pnpm"), ("cargo.lock", "cargo"),
        ("go.sum", "go_modules"), ("gemfile.lock", "bundler"),
    ]:
        if _any_match([lockfile]):
            package_manager = mgr
            break

    # --- Test directories ---
    test_dir_names = {"tests", "test", "__tests__", "spec"}
    test_dirs = sorted({
        Path(f).parts[0] for f in files
        if Path(f).parts and Path(f).parts[0].lower() in test_dir_names
    })

    return {
        "test_framework": test_framework,
        "test_dirs": test_dirs,
        "linters": linters,
        "ci_pipelines": ci_pipelines,
        "contribution_docs": contribution_docs,
        "package_manager": package_manager,
    }


def _compute_dependency_graph(files: list[str], repo_checkout: Path) -> dict[str, object]:
    """
    Build an import/export dependency graph for source files.

    Delegates to ast_imports.build_dependency_graph(), which uses tree-sitter
    AST parsing. Returns an empty graph if tree-sitter is not installed or
    ast_imports cannot be imported.
    """
    try:
        from src.pipeline import ast_imports  # optional dependency

        return ast_imports.build_dependency_graph(files, repo_checkout)
    except ImportError:
        return {"imports_map": {}, "imported_by": {}, "note": "dependency graph omitted: src.pipeline.ast_imports module not available"}


def transform_repo(raw_repo_dir: Path, transform_root: Path, top_n_hotspots: int = 20) -> Path:
    """
    Build enriched gold-layer analytics from a raw ingest directory.

    Produces transform.json with:
      structure_summary, hotspots, co_change_pairs, risk_levels,
      authorship, dependency_graph, conventions
    """
    raw_repo_dir = Path(raw_repo_dir)
    transform_root = Path(transform_root)

    ingest_path = raw_repo_dir / "ingest.json"
    repo_checkout = raw_repo_dir / "repo"
    if not ingest_path.exists():
        raise FileNotFoundError(f"Missing ingest artifact: {ingest_path}")
    if not repo_checkout.exists():
        raise FileNotFoundError(f"Missing repo checkout: {repo_checkout}")

    ingest_data = json.loads(ingest_path.read_text(encoding="utf-8"))
    repo_slug = str(ingest_data.get("repo_slug") or raw_repo_dir.name)
    files: list[str] = list(ingest_data.get("files", []))

    # Derive lightweight commit list from ingest's commit_log
    raw_commit_log = ingest_data.get("commit_log", [])
    commits: list[dict[str, object]] = [
        {
            "sha": entry["sha"],
            "date": entry["author_date"],
            "author": entry["author_name"],
            "files": [f["path"] for f in entry.get("files_changed", [])],
        }
        for entry in raw_commit_log
    ]
    commits_analyzed = len(commits)

    structure_summary = _build_structure_summary(files)
    hotspots = _compute_hotspots_from_commits(commits, top_n=top_n_hotspots)
    co_change_pairs = _compute_co_change_matrix(commits)
    authorship = _compute_authorship(commits, files)
    risk_levels = _compute_risk_levels(hotspots, co_change_pairs, authorship)
    conventions = _detect_conventions(files, repo_checkout)
    dependency_graph = _compute_dependency_graph(files, repo_checkout)

    out_dir = transform_root / repo_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    transformed = {
        "repo_slug": repo_slug,
        "repo_url": ingest_data.get("repo_url"),
        "head_commit": ingest_data.get("head_commit"),
        "structure_summary": structure_summary,
        "hotspots": hotspots,
        "co_change_pairs": co_change_pairs,
        "risk_levels": risk_levels,
        "authorship": authorship,
        "dependency_graph": dependency_graph,
        "conventions": conventions,
        "transform_metadata": {
            "generated_at": utc_now(),
            "top_n_hotspots": top_n_hotspots,
            "commits_analyzed": commits_analyzed,
            "source_ingest_path": str(ingest_path),
        },
    }

    out_path = out_dir / "transform.json"
    out_path.write_text(json.dumps(transformed, indent=2), encoding="utf-8")
    return out_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transform raw ingest data into structure + hotspots.")
    parser.add_argument("--raw-root", type=Path, required=True, help="Directory containing raw repo folders.")
    parser.add_argument(
        "--transform-root",
        type=Path,
        required=True,
        help="Directory to write transformed artifacts.",
    )
    parser.add_argument("--top-n-hotspots", type=int, default=20, help="Max hotspots to emit per repo.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    candidates = sorted(
        [path for path in args.raw_root.iterdir() if path.is_dir() and (path / "ingest.json").exists()],
        key=lambda path: path.name,
    )

    success_count = 0
    for raw_repo_dir in candidates:
        try:
            out_path = transform_repo(raw_repo_dir, args.transform_root, top_n_hotspots=args.top_n_hotspots)
            print(f"[transform] wrote {out_path}")
            success_count += 1
        except Exception as exc:
            print(f"[transform] failed for {raw_repo_dir}: {exc}", file=sys.stderr)

    print(f"[transform] completed {success_count} / {len(candidates)} repositories")
    return 0 if success_count else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())