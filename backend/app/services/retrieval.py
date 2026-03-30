from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
import re

from app.models import OnboardingSnapshot, RepoFileContent, RepoSnapshot

_MAX_FILE_LIST_FOR_PROMPT = 400
_MAX_FILE_CONTENT_CHARS = 4000
_MAX_TOTAL_CONTENT_CHARS = 16000


def _normalize_files(files: list[str]) -> list[str]:
    normalized = [path.replace("\\", "/") for path in files if path]
    return sorted(dict.fromkeys(normalized))


def _top_level_counts(files: list[str]) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for path in files:
        parts = PurePosixPath(path).parts
        top_level = parts[0] if len(parts) > 1 else "."
        counts[top_level] += 1
    return counts.most_common(12)


def _file_type_counts(files: list[str]) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for path in files:
        suffix = PurePosixPath(path).suffix.lower() or "[no_ext]"
        counts[suffix] += 1
    return counts.most_common(12)


def _find_start_here_candidates(files: list[str]) -> list[str]:
    patterns: list[tuple[re.Pattern[str], str, int]] = [
        (re.compile(r"(?i)^readme(\..+)?$"), "project overview", 100),
        (re.compile(r"(?i)^contributing(\..+)?$"), "contribution guide", 95),
        (re.compile(r"(?i)^docs?/"), "documentation", 90),
        (re.compile(r"(?i)^pyproject\.toml$"), "python project config", 85),
        (re.compile(r"(?i)^package\.json$"), "node project config", 85),
        (re.compile(r"(?i)^makefile$"), "build entrypoint", 80),
        (re.compile(r"(?i)^dockerfile"), "runtime entrypoint", 75),
        (re.compile(r"(?i)^tests?/"), "test suite", 70),
        (re.compile(r"(?i)^\.github/workflows/"), "ci workflow", 68),
        (re.compile(r"(?i)^src/main\."), "application entrypoint", 68),
        (re.compile(r"(?i)^src/app\."), "application entrypoint", 65),
    ]
    scored: list[tuple[int, str, list[str]]] = []
    for path in files:
        reasons: list[str] = []
        score = 0
        for pattern, reason, points in patterns:
            if pattern.search(path):
                reasons.append(reason)
                score += points
        if reasons:
            scored.append((score, path, sorted(set(reasons))))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [f"- {path} ({', '.join(reasons)})" for score, path, reasons in scored[:12]]


def _detect_conventions(files: list[str], selected_file_contents: list[RepoFileContent]) -> list[str]:
    file_set = {path.lower() for path in files}
    content_map = {item.path.lower(): item.content for item in selected_file_contents}

    conventions: list[str] = []
    if "pytest.ini" in file_set or "[tool.pytest.ini_options]" in content_map.get("pyproject.toml", ""):
        conventions.append("- Tests: pytest is likely configured")
    if "package.json" in file_set:
        conventions.append("- JavaScript package management: package.json is present")
    if "pyproject.toml" in file_set:
        conventions.append("- Python packaging: pyproject.toml is present")
    if any(path.endswith("requirements.txt") for path in file_set):
        conventions.append("- Python dependencies: requirements file is present")
    if any(path.startswith(".github/workflows/") for path in file_set):
        conventions.append("- CI/CD: GitHub Actions workflow files are present")
    if any(path.startswith("dockerfile") or path == "docker-compose.yml" for path in file_set):
        conventions.append("- Containerization: Docker-related files are present")
    if "makefile" in file_set:
        conventions.append("- Local developer commands may be centralized in Makefile")
    return conventions


def _format_file_inventory(files: list[str]) -> str:
    if not files:
        return "No file inventory was provided."

    visible_files = files[:_MAX_FILE_LIST_FOR_PROMPT]
    lines = ["All repository file paths:", *[f"- {path}" for path in visible_files]]
    if len(files) > len(visible_files):
        lines.append(f"- ... {len(files) - len(visible_files)} more files omitted for prompt size")
    return "\n".join(lines)


def _truncate_content(content: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    return content[:limit].rstrip() + "\n...[truncated]"


def _format_selected_file_contents(selected_file_contents: list[RepoFileContent]) -> str:
    if not selected_file_contents:
        return "No selected file contents were provided."

    preferred_patterns = [
        re.compile(r"(?i)(^|/)readme(\..+)?$"),
        re.compile(r"(?i)(^|/)contributing(\..+)?$"),
        re.compile(r"(?i)(^|/)pyproject\.toml$"),
        re.compile(r"(?i)(^|/)package\.json$"),
        re.compile(r"(?i)(^|/)requirements[^/]*\.txt$"),
        re.compile(r"(?i)(^|/)dockerfile"),
        re.compile(r"(?i)(^|/)docker-compose"),
        re.compile(r"(?i)(^|/)makefile$"),
        re.compile(r"(?i)(^|/)pytest\.ini$"),
        re.compile(r"(?i)^\.github/workflows/"),
        re.compile(r"(?i)^docs?/"),
    ]

    def sort_key(item: RepoFileContent) -> tuple[int, str]:
        score = 100
        for idx, pattern in enumerate(preferred_patterns):
            if pattern.search(item.path.replace("\\", "/")):
                score = idx
                break
        return score, item.path

    remaining_budget = _MAX_TOTAL_CONTENT_CHARS
    sections: list[str] = []
    for item in sorted(selected_file_contents, key=sort_key):
        if remaining_budget <= 0:
            break
        excerpt_limit = min(_MAX_FILE_CONTENT_CHARS, remaining_budget)
        excerpt = _truncate_content(item.content, excerpt_limit)
        remaining_budget -= len(excerpt)
        truncated_note = " (source was truncated before upload)" if item.truncated else ""
        sections.append(
            f"### {item.path}{truncated_note}\n```text\n{excerpt}\n```"
        )

    if not sections:
        return "No file contents fit within the prompt budget."
    if len(sections) < len(selected_file_contents):
        sections.append(
            f"... {len(selected_file_contents) - len(sections)} additional selected file entries omitted for prompt size"
        )
    return "\n\n".join(sections)


def _snapshot_top_level(summary: dict[str, object]) -> list[str]:
    rows = summary.get("top_level_directories", [])
    if not isinstance(rows, list):
        return []
    lines: list[str] = []
    for item in rows[:12]:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        count = item.get("file_count")
        if isinstance(path, str):
            lines.append(f"- {path}: {count} files")
    return lines


def _snapshot_file_types(summary: dict[str, object]) -> list[str]:
    rows = summary.get("file_type_counts", [])
    if not isinstance(rows, list):
        return []
    lines: list[str] = []
    for item in rows[:12]:
        if not isinstance(item, dict):
            continue
        ext = item.get("extension")
        count = item.get("count")
        if isinstance(ext, str):
            lines.append(f"- {ext}: {count} files")
    return lines


def _snapshot_start_here(summary: dict[str, object]) -> list[str]:
    rows = summary.get("start_here_candidates", [])
    if not isinstance(rows, list):
        return []
    lines: list[str] = []
    for item in rows[:12]:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        reasons = item.get("reasons")
        if not isinstance(path, str):
            continue
        if isinstance(reasons, list):
            reason_text = ", ".join(str(reason) for reason in reasons[:4])
            lines.append(f"- {path} ({reason_text})")
        else:
            lines.append(f"- {path}")
    return lines


def _snapshot_hotspots(hotspots: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for item in hotspots[:10]:
        path = item.get("path")
        touches = item.get("touch_count")
        last_touched = item.get("last_touched")
        if isinstance(path, str):
            lines.append(f"- {path}: {touches} touches; last touched {last_touched or 'unknown'}")
    return lines


def _snapshot_risk_matrix(risk_matrix: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for item in risk_matrix[:10]:
        path = item.get("path")
        risk_level = item.get("risk_level")
        risk_score = item.get("risk_score")
        if isinstance(path, str):
            lines.append(f"- {path}: risk={risk_level} score={risk_score}")
    return lines


def _snapshot_authorship(authorship_summary: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for item in authorship_summary[:8]:
        path = item.get("path")
        contributors = item.get("primary_contributors", [])
        contributor_text = ""
        if isinstance(contributors, list):
            names: list[str] = []
            for contributor in contributors[:3]:
                if isinstance(contributor, dict) and isinstance(contributor.get("name"), str):
                    names.append(str(contributor["name"]))
            contributor_text = ", ".join(names)
        if isinstance(path, str):
            details = f"; primary contributors: {contributor_text}" if contributor_text else ""
            lines.append(f"- {path}: {item.get('total_commits')} commits{details}")
    return lines


def _snapshot_top_contributors(authorship_summary: list[dict[str, object]]) -> list[str]:
    contributor_counts: Counter[str] = Counter()
    for item in authorship_summary:
        contributors = item.get("primary_contributors", [])
        if not isinstance(contributors, list):
            continue
        for contributor in contributors:
            if not isinstance(contributor, dict):
                continue
            name = contributor.get("name")
            commit_count = contributor.get("commit_count", 0)
            if isinstance(name, str):
                try:
                    contributor_counts[name] += int(commit_count)
                except (TypeError, ValueError):
                    contributor_counts[name] += 0
    return [f"- {name}: {count} commits across listed files" for name, count in contributor_counts.most_common(8)]


def _snapshot_co_changes(co_change_pairs: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for item in co_change_pairs[:10]:
        file_a = item.get("file_a")
        file_b = item.get("file_b")
        count = item.get("co_change_count")
        if isinstance(file_a, str) and isinstance(file_b, str):
            lines.append(f"- {file_a} <-> {file_b}: {count} co-changes")
    return lines


def _snapshot_conventions(conventions: dict[str, object]) -> list[str]:
    if not conventions:
        return []

    lines: list[str] = []
    test_framework = conventions.get("test_framework")
    if isinstance(test_framework, dict):
        name = test_framework.get("name")
        config_path = test_framework.get("config_path")
        lines.append(f"- Tests: {name} configured via {config_path}")

    test_dirs = conventions.get("test_dirs")
    if isinstance(test_dirs, list) and test_dirs:
        lines.append(f"- Test directories: {', '.join(str(item) for item in test_dirs[:5])}")

    linters = conventions.get("linters")
    if isinstance(linters, list) and linters:
        names = []
        for item in linters[:5]:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(str(item["name"]))
        if names:
            lines.append(f"- Linters/formatters: {', '.join(names)}")

    ci_pipelines = conventions.get("ci_pipelines")
    if isinstance(ci_pipelines, list) and ci_pipelines:
        names = []
        for item in ci_pipelines[:5]:
            if isinstance(item, dict) and isinstance(item.get("platform"), str):
                names.append(str(item["platform"]))
        if names:
            lines.append(f"- CI/CD: {', '.join(names)}")

    contribution_docs = conventions.get("contribution_docs")
    if isinstance(contribution_docs, list) and contribution_docs:
        lines.append(f"- Contribution docs: {', '.join(str(item) for item in contribution_docs[:5])}")

    package_manager = conventions.get("package_manager")
    if package_manager:
        lines.append(f"- Package manager: {package_manager}")

    return lines


def retrieve_context(
    repo_url: str,
    repo_snapshot: RepoSnapshot | None = None,
    onboarding_snapshot: OnboardingSnapshot | None = None,
) -> str:
    if repo_snapshot is None and onboarding_snapshot is not None:
        repo_snapshot = RepoSnapshot(repo_slug=onboarding_snapshot.repo_slug)

    if repo_snapshot is None:
        return f"""
Repository URL: {repo_url}
Main purpose: Contributor onboarding documentation
Repository snapshot: not provided
Important note: Exact setup steps are not confirmed yet
""".strip()

    files = _normalize_files(repo_snapshot.files)
    structure_summary = onboarding_snapshot.structure_summary if onboarding_snapshot is not None else {}
    top_level = _snapshot_top_level(structure_summary) or [f"- {path}: {count} files" for path, count in _top_level_counts(files)]
    file_types = _snapshot_file_types(structure_summary) or [f"- {ext}: {count} files" for ext, count in _file_type_counts(files)]
    start_here = _snapshot_start_here(structure_summary) or _find_start_here_candidates(files)
    hotspots = (
        _snapshot_hotspots(onboarding_snapshot.hotspots)
        if onboarding_snapshot is not None
        else []
    )
    risk_matrix = (
        _snapshot_risk_matrix(onboarding_snapshot.risk_matrix)
        if onboarding_snapshot is not None
        else []
    )
    authorship_summary = (
        _snapshot_authorship(onboarding_snapshot.authorship_summary)
        if onboarding_snapshot is not None
        else []
    )
    authors = (
        _snapshot_top_contributors(onboarding_snapshot.authorship_summary)
        if onboarding_snapshot is not None
        else []
    )
    co_change_pairs = (
        _snapshot_co_changes(onboarding_snapshot.co_change_pairs)
        if onboarding_snapshot is not None
        else []
    )
    repo_slug = (
        (onboarding_snapshot.repo_slug if onboarding_snapshot is not None else None)
        or repo_snapshot.repo_slug
        or "unknown"
    )
    conventions = (
        _snapshot_conventions(onboarding_snapshot.conventions)
        if onboarding_snapshot is not None
        else []
    ) or _detect_conventions(files, repo_snapshot.selected_file_contents)

    sections = [
        f"Repository URL: {repo_url}",
        f"Repository slug: {repo_slug}",
        f"Total files discovered: {len(files)}",
        "",
        _format_file_inventory(files),
        "",
        "Top-level directories by file count:",
        *(top_level or ["- No top-level directory summary available"]),
        "",
        "Most common file types:",
        *(file_types or ["- No file type summary available"]),
        "",
        "Suggested starting points:",
        *(start_here or ["- No obvious entry files detected"]),
        "",
        "Hotspots:",
        *(hotspots or ["- No hotspot summary provided"]),
        "",
        "Risk areas:",
        *(risk_matrix or ["- No risk summary provided"]),
        "",
        "Frequently co-changed files:",
        *(co_change_pairs or ["- No co-change summary provided"]),
        "",
        "Most active contributors:",
        *(authors or ["- No contributor summary provided"]),
        "",
        "Ownership examples:",
        *(authorship_summary or ["- No authorship summary provided"]),
        "",
        "Detected conventions:",
        *(conventions or ["- No strong conventions detected from provided files"]),
        "",
        "Selected file contents:",
        _format_selected_file_contents(repo_snapshot.selected_file_contents),
    ]
    return "\n".join(sections).strip()
