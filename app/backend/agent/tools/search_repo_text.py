from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .shared import BINARY_EXTENSIONS, IGNORED_DIR_NAMES, LocalTool


def handler(params: dict[str, str], repo_roots: dict[str, Path]) -> str:
    repo_slug = params["repoSlug"]
    query = params["query"]
    if not query.strip():
        raise ValueError("Query must be non-empty.")
    if repo_slug not in repo_roots:
        raise ValueError(f"Unsupported repo slug: {repo_slug}")

    root = repo_roots[repo_slug].resolve()
    rg_bin = shutil.which("rg")
    if rg_bin:
        command = [
            rg_bin,
            "-n",
            "-i",
            "-m",
            "50",
            "--no-heading",
            "--color",
            "never",
        ]
        for dirname in sorted(IGNORED_DIR_NAMES):
            command.extend(["-g", f"!{dirname}/**"])
        for ext in sorted(BINARY_EXTENSIONS):
            command.extend(["-g", f"!*{ext}"])
        command.extend([query, str(root)])

        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or "rg search failed.")
        if not result.stdout.strip():
            return "No matches found."

        lines: list[str] = []
        for raw_line in result.stdout.splitlines():
            prefix, sep, match = raw_line.partition(":")
            if not sep:
                continue
            line_no, sep, content = match.partition(":")
            if not sep:
                continue
            rel_path = Path(prefix).resolve().relative_to(root)
            lines.append(f"{rel_path}:{line_no}: {content.strip()}")
            if len(lines) >= 50:
                break
        if lines:
            return "\n".join(lines)
        return "No matches found."

    matches: list[str] = []
    lowered_query = query.lower()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames if name.lower() not in IGNORED_DIR_NAMES
        ]
        for filename in filenames:
            if len(matches) >= 50:
                break
            file_path = Path(dirpath) / filename
            if file_path.suffix.lower() in BINARY_EXTENSIONS:
                continue
            try:
                rel_path = file_path.relative_to(root)
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for line_number, line in enumerate(content.splitlines(), start=1):
                if lowered_query in line.lower():
                    matches.append(f"{rel_path}:{line_number}: {line.strip()}")
                    if len(matches) >= 50:
                        break
        if len(matches) >= 50:
            break

    if not matches:
        return "No matches found."
    return "\n".join(matches)


TOOL: LocalTool = {
    "definition": {
        "name": "searchRepoText",
        "description": "Search repository text files for lines containing a query string.",
        "parameters": {
            "repoSlug": {
                "description": "Repository identifier for the local repository workspace.",
                "required": True,
                "type": "string",
            },
            "query": {
                "description": "Case-insensitive text query to search for.",
                "required": True,
                "type": "string",
            },
        },
    },
    "handler": handler,
}
