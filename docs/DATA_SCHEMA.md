# ContribNow Data Schema

**Purpose:** This document specifies the exact structure, field definitions, and constraints for all data produced by the pipeline. It serves as a data contract between the ETL pipeline and downstream consumers (RAG layer, analytics, etc.).

**Last Updated:** March 16, 2026  
**Pipeline Version:** 2.0 (Schema Version: 2)

---

## 1. Data Layers Overview

```
Raw Layer (data/raw_<run_id>/)
├── Actual source code files
├── Real commit messages
├── Unmodified git history
└── NO privacy transformations

Transform Layer (data/transform_<run_id>/)
├── Structured transform.json
├── Extracted metadata
├── Computed features (hotspots, risk, authorship, etc.)
└── NO hashing or stripping (local-only)

Output Layer (data/output_<run_id>/)
├── onboarding_snapshot.json (enriched projection)
├── index.json (artifact inventory)
└── User-consumable format
```

---

## 2. Raw Layer

**Location:** `data/raw_<run_id>/<repo_slug>/`

**Contents:**
- Full clone of repository at specified depth (default: 500 commits)
- All source files with original paths and content
- Git metadata (logs, diffs)

**What RAG Team Uses:**
- Raw source code for embedding
- Real file paths for citations
- Actual commit messages for context

**Important:**
- This is the **source of truth** for code content
- Never truncate or hash file paths here
- Used only locally (never cloud-synced for privacy)

---

## 3. Transform Layer: transform.json

**Location:** `data/transform_<run_id>/<repo_slug>/transform.json`

**Top-level Structure:**
```json
{
  "repo_slug": "string",
  "repo_url": "string",
  "head_commit": "string (SHA-1)",
  "structure_summary": {...},
  "hotspots": [...],
  "risk_levels": {...},
  "co_change_pairs": [...],
  "authorship": {...},
  "dependency_graph": {...},
  "conventions": {...},
  "transform_metadata": {...}
}
```

### 3.1 repo_slug
```json
"repo_slug": "pallets__markupsafe"
```
- **Type:** String
- **Format:** `{owner}__{repo}` (double underscore delimiter)
- **Purpose:** Unique identifier for output directories
- **Derived from:** GitHub URL

### 3.2 repo_url
```json
"repo_url": "https://github.com/pallets/markupsafe.git"
```
- **Type:** String (valid HTTPS Git URL)
- **Purpose:** Provenance tracking
- **Constraint:** Must be the URL used for clone

### 3.3 head_commit
```json
"head_commit": "a1b2c3d4e5f6..."
```
- **Type:** String (40-char SHA-1 hash)
- **Purpose:** Version identifier for reproducibility
- **Usage:** Deduplication key (combined with tenant_id and repo_fingerprint)

### 3.4 structure_summary
```json
"structure_summary": {
  "total_files": 487,
  "top_level_directories": [
    {"path": "src", "file_count": 342},
    {"path": "tests", "file_count": 45},
    {"path": "docs", "file_count": 30}
  ],
  "file_type_counts": [
    {"extension": ".py", "count": 342},
    {"extension": ".md", "count": 45},
    {"extension": ".json", "count": 12}
  ],
  "start_here_candidates": [
    {"path": "README.md", "score": 100, "reasons": ["project_overview"]},
    {"path": "CONTRIBUTING.md", "score": 95, "reasons": ["contribution_guidelines"]},
    {"path": "src/main.py", "score": 75, "reasons": ["application_entrypoint"]}
  ]
}
```
- **Type:** Object
- **Fields:**
  - `total_files`: Integer, count of non-ignored files
  - `top_level_directories`: Array of `{path: String, file_count: Integer}`, sorted by file_count descending
  - `file_type_counts`: Array of `{extension: String, count: Integer}`, sorted by count descending
  - `start_here_candidates`: Array of `{path: String, score: Integer, reasons: Array<String>}`, top 15 files scored by pattern matching against well-known entry points (README, CONTRIBUTING, Dockerfile, etc.), sorted by score descending
- **Purpose:** High-level repository statistics and onboarding entry points
- **Constraint:** Extensions are lowercase with leading dot; `"."` root directory is represented as `"."`

### 3.5 hotspots

```json
"hotspots": [
  {
    "path": "src/core.py",
    "touch_count": 87,
    "last_touched": "2026-03-10T14:22:00+00:00"
  },
  {
    "path": "src/utils.py",
    "touch_count": 42,
    "last_touched": "2026-03-08T09:15:00+00:00"
  }
]
```

- **Type:** Array of Objects
- **Fields per item:**
  - `path`: String, relative file path from repo root
  - `touch_count`: Integer ≥ 0, number of commits touching this file
  - `last_touched`: String (ISO 8601 date) or null, date of the most recent commit touching this file
- **Ordering:** Sorted by `touch_count` descending
- **Note:** Risk levels are computed separately in `risk_levels` (section 3.6), not embedded in hotspots
- **Purpose:** Identify frequently-changing files
- **RAG Usage:** Prioritize chunks from high-touch files, flag as potentially unstable

### 3.6 risk_levels

```json
"risk_levels": [
  {
    "path": "src/core.py",
    "risk_level": "high",
    "risk_score": 0.82,
    "factors": {
      "touch_count": 87,
      "distinct_authors": 8,
      "co_change_degree": 5
    }
  },
  {
    "path": "src/utils.py",
    "risk_level": "medium",
    "risk_score": 0.58,
    "factors": {
      "touch_count": 42,
      "distinct_authors": 4,
      "co_change_degree": 3
    }
  }
]
```

- **Type:** Array of Objects
- **Fields per item:**
  - `path`: String, relative file path from repo root
  - `risk_level`: Enum ("high" | "medium" | "low")
  - `risk_score`: Float, 0.0 to 1.0 (rounded to 4 decimal places)
  - `factors`: Object with raw values used as scoring inputs
    - `touch_count`: Integer, number of commits touching this file (weight 50%)
    - `distinct_authors`: Integer, number of unique authors (weight 30%)
    - `co_change_degree`: Integer, number of co-change pairs involving this file (weight 20%)
- **Scoring Formula:** Each factor is min-max normalised within the hotspot set, then combined:
  ```
  risk_score = (0.5 × norm_touch_count) + (0.3 × norm_distinct_authors) + (0.2 × norm_co_change_degree)
  ```
- **Thresholds:**
  - `high`: risk_score > 0.7
  - `medium`: risk_score ≥ 0.4 and ≤ 0.7
  - `low`: risk_score < 0.4
- **Note:** `factors` contains the raw integer values; normalisation is applied internally to compute `risk_score`
- **Purpose:** Multi-dimensional risk assessment for change management
- **RAG Usage:** Filter chunks by risk level; attach risk metadata; warn about high-risk edits

### 3.7 co_change_pairs

```json
"co_change_pairs": [
  {
    "file_a": "src/core.py",
    "file_b": "src/utils.py",
    "co_change_count": 12
  },
  {
    "file_a": "src/handler.py",
    "file_b": "src/requests.py",
    "co_change_count": 8
  }
]
```

- **Type:** Array of Objects
- **Fields per item:**
  - `file_a`: String, file path
  - `file_b`: String, file path
  - `co_change_count`: Integer ≥ 3 (threshold constraint)
- **Constraint:** Only includes pairs with co_change_count ≥ 3
- **Ordering:** Sorted by co_change_count descending
- **Symmetry:** Each pair appears once (a < b lexicographically)
- **Purpose:** Identify hidden file dependencies (often changed together)
- **RAG Usage:** When retrieving chunk from file_a, also retrieve from file_b; flag as hidden dependency

### 3.8 authorship

```json
"authorship": [
  {
    "path": "src/core.py",
    "total_commits": 45,
    "distinct_authors": 8,
    "primary_contributors": [
      {"name": "Alice Smith", "commit_count": 18},
      {"name": "Bob Jones", "commit_count": 12},
      {"name": "Charlie Lee", "commit_count": 7}
    ]
  },
  {
    "path": "src/utils.py",
    "total_commits": 22,
    "distinct_authors": 4,
    "primary_contributors": [
      {"name": "Alice Smith", "commit_count": 10},
      {"name": "David Park", "commit_count": 8}
    ]
  }
]
```

- **Type:** Array of Objects
- **Fields per item:**
  - `path`: String, relative file path from repo root
  - `total_commits`: Integer > 0, sum of all commits touching this file
  - `distinct_authors`: Integer > 0, count of unique authors
  - `primary_contributors`: Array of ContributorRecord (sorted by commit_count desc, top 3)
    - `name`: String, author name from git log (`%aN`)
    - `commit_count`: Integer, number of commits by this author for this file
- **Constraint:** `primary_contributors` limited to top 3 contributors
- **Note:** Only files present in the ingest file list are included; files with zero commits are omitted
- **Purpose:** Track code ownership and context-sensitive expertise
- **RAG Usage:** Suggest code reviewers; flag high-expertise areas; link chunks to maintainers

### 3.9 dependency_graph

```json
"dependency_graph": {
  "imports_map": {
    "src/app.py": ["os", "json", "src.core", "src.utils"],
    "src/core.py": ["re", "typing", "src.utils"],
    "src/utils.py": ["json", "pathlib"]
  },
  "imported_by": {
    "os": ["src/app.py"],
    "json": ["src/app.py", "src/utils.py"],
    "src.core": ["src/app.py"],
    "src.utils": ["src/app.py", "src/core.py"],
    "re": ["src/core.py"],
    "typing": ["src/core.py"],
    "pathlib": ["src/utils.py"]
  }
}
```

- **Type:** Object with two keys: `imports_map` and `imported_by`
- **imports_map:** Object<filepath: Array<module_names>>
  - Keys: Source file paths (relative to repo root)
  - Values: List of imported module/package names
  - Sources: Extracted via AST (requires tree-sitter)
- **imported_by:** Object<module_name: Array<filepaths>>
  - Keys: Module/package names (can be builtins, thirds-party, or local)
  - Values: List of files that import this module
  - Auto-built from imports_map
- **Note:** Optional field, may be empty dict if AST unavailable or no imports detected
- **AST Coverage:** Python (full), JavaScript/TypeScript (full), Java (full). Others: not supported (returns empty)
- **Purpose:** Build code dependency graph for relationship-aware retrieval
- **RAG Usage:** Given a chunk, retrieve related chunks via dependency_graph; visualize import relationships

### 3.10 conventions

```json
"conventions": {
  "test_framework": {
    "name": "pytest",
    "config_path": "pytest.ini"
  },
  "test_dirs": ["tests"],
  "linters": [
    {"name": "ruff", "config_path": ".ruff.toml"},
    {"name": "black", "config_path": "pyproject.toml"}
  ],
  "ci_pipelines": [
    {"platform": "github_actions", "config_path": ".github/workflows/tests.yml"}
  ],
  "contribution_docs": ["CONTRIBUTING.md"],
  "package_manager": "poetry"
}
```

- **Type:** Object with keys: `test_framework`, `test_dirs`, `linters`, `ci_pipelines`, `contribution_docs`, `package_manager`
- **Fields:**
  - `test_framework`: Object `{name: String, config_path: String}` or null if none detected. Supported: `pytest`, `jest`
  - `test_dirs`: Array of Strings, top-level directories matching common test directory names (e.g., `tests`, `test`, `__tests__`, `spec`)
  - `linters`: Array of `{name: String, config_path: String}`. Detected linters/formatters include: `editorconfig`, `ruff`, `flake8`, `eslint`, `prettier`, `black`
  - `ci_pipelines`: Array of `{platform: String, config_path: String}`. Detected platforms: `github_actions`, `gitlab_ci`, `jenkins`, `circleci`, `travis_ci`
  - `contribution_docs`: Array of Strings, paths to contribution-related files (e.g., `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `PULL_REQUEST_TEMPLATE.md`)
  - `package_manager`: String or null. Detected via lockfile presence: `poetry`, `pipenv`, `npm`, `yarn`, `pnpm`, `cargo`, `go_modules`, `bundler`
- **Purpose:** Surface practical contribution norms for onboarding guides
- **RAG Usage:** Mention conventions in generated summaries; suggest adherence in recommendations

### 3.11 transform_metadata

```json
"transform_metadata": {
  "generated_at": "2026-03-16T15:23:45Z",
  "top_n_hotspots": 20,
  "commits_analyzed": 487,
  "source_ingest_path": "data/raw_20260316.../pallets__markupsafe/ingest.json"
}
```

- **Type:** Object
- **Fields:**
  - `generated_at`: ISO 8601 string, when the transform ran (via `utc_now()`)
  - `top_n_hotspots`: Integer, maximum number of hotspots computed
  - `commits_analyzed`: Integer, total number of commits parsed from git log
  - `source_ingest_path`: String, filesystem path to the ingest.json used as input
- **Purpose:** Pipeline operational metadata and provenance
- **RAG Usage:** Understand pipeline parameters; trace back to source ingest

---

## 4. Output Layer: onboarding_snapshot.json

**Location:** `data/output_<run_id>/<repo_slug>/onboarding_snapshot.json`

**Structure:**
```json
{
  "repo_slug": "pallets__markupsafe",
  "repo_url": "https://github.com/pallets/markupsafe.git",
  "head_commit": "a1b2c3d4...",
  "structure_summary": {...},
  "hotspots": [...],
  "risk_matrix": {...},
  "co_change_pairs": [...],
  "authorship_summary": {...},
  "dependency_graph": {...},
  "conventions": {...},
  "transform_metadata": {...},
  "load_metadata": {
    "generated_at": "2026-03-16T15:24:10Z",
    "source_transform_path": "data/transform_20260316.../pallets__markupsafe/transform.json"
  }
}
```

**Differences from transform.json:**
- `risk_levels` → `risk_matrix` (same content, renamed for clarity)
- `authorship` → `authorship_summary` (same content, renamed)
- Added `load_metadata` field (generation timestamp and source path)
- Otherwise identical projection of enriched fields

**Purpose:** User-consumable format, clean JSON structure for dashboards/tools  
**RAG Usage:** Use as summary layer; filters on risk_matrix; convention references

---

## 5. Data Constraints & Guardrails

### Mandatory Fields
These must always be present in transform.json:

- `repo_slug` ✓
- `repo_url` ✓
- `head_commit` ✓
- `structure_summary` ✓
- `hotspots` ✓
- `risk_levels` ✓
- `co_change_pairs` (may be empty array)
- `authorship` ✓
- `dependency_graph` (may be empty dict)
- `conventions` ✓
- `transform_metadata` ✓

### Optional Fields
These may be missing or empty:

- `dependency_graph` — empty if AST unavailable
- `co_change_pairs` — empty if no pairs meet threshold
- Certain convention sub-arrays — empty if not detected

### Value Constraints

| Field | Constraint | Reason |
|-------|-----------|--------|
| `risk_score` | 0.0 ≤ x ≤ 1.0 | Normalized float |
| `risk_level` | Must be enum | Consistency |
| `touch_count` | ≥ 0 | Non-negative integer |
| `co_change_count` | ≥ 3 | Threshold constraint |
| `distinct_authors` | ≥ 1 | At least one author |
| File paths | Relative, forward-slash | Normalize separators |

### Performance Considerations

- **hotspots:** Typically 20-100 items
- **co_change_pairs:** Can be 50–500+ pairs in large repos
- **authorship:** One entry per file with at least one commit (can be larger than hotspots, which is capped at top_n)
- **dependency_graph:** Can be large in import-heavy codebases
  - Recommended: Pre-compute imports, cache results
  - Beware: Transitive dependencies not expanded (only direct imports)

---

## 6. Architectural Notes: What Goes Where

### Source Code Storage

**Important:** Actual source code files are **NOT** stored in JSON files. They remain in the raw layer filesystem.

**Why:**
- JSON bloat: Large repos could exceed 100MB+ as JSON
- Efficient I/O: Direct file reads are faster than JSON parsing
- No duplication: Code already exists in raw layer
- Version control: Would be unwieldy to track code changes in JSON

**Where code lives:**
- Raw layer: `data/raw_<run_id>/<repo_slug>/` → actual source files with original paths
- Transform.json: Metadata ONLY (hotspots, risk, authorship, dependency_graph)
- Output snapshot: Metadata projection for user interface

### Data Contract: ETL → RAG Team

| Layer | Owner | Content | Purpose |
|-------|-------|---------|---------|
| Raw | ETL | Source code files | LLM grounding (actual code) |
| Transform.json | ETL | Metadata (risk, imports, authorship, conventions) | Context for retrieval/ranking |
| Snapshot.json | ETL | Metadata subset (clean projection) | User interface display |
| Vector store | RAG | Embeddings + source + metadata | Similarity search |

**RAG team workflow:**  
```
1. Read raw layer files → load actual source code
2. Read transform.json → get metadata (risk_levels, dependency_graph, etc.)
3. Chunk code (using AST + metadata to inform chunk boundaries)
4. Generate embeddings (OpenAI, CodeBERT, etc.)
5. Store in vector DB with metadata attached
6. Enable semantic search over code + context
```

**ETL responsibilities (DONE):**  
✅ Ingest source code + git history  
✅ Parse and extract metadata  
✅ Compute enriched features (risk, co-changes, authorship, imports)  
✅ Expose metadata in JSON format (transform.json, snapshot.json)  

**RAG responsibilities (TODO - next phase):**  
🔲 Read raw + transform data  
🔲 Implement chunking strategy  
🔲 Generate embeddings  
🔲 Store in vector database  
🔲 Implement retrieval logic  

---

## 7. Integration Guide for RAG Layer

### Recommended Vector Store Schema

```sql
CREATE TABLE code_embeddings (
  embedding_id UUID PRIMARY KEY,
  tenant_id UUID,
  repo_id UUID,
  file_path TEXT,                    -- from snapshot.json keys
  chunk_type VARCHAR(20),            -- 'function'|'class'|'method'|'line_range'
  start_line INT,
  end_line INT,
  source_content TEXT,               -- from raw layer
  embedding VECTOR(384),             -- or chosen dimension
  
  -- metadata from transform.json
  risk_level VARCHAR(20),            -- from risk_levels
  risk_score FLOAT,                  -- for retrieval filtering
  co_changes_with TEXT[],           -- related files from co_change_pairs
  authors TEXT[],                    -- from authorship_summary
  
  -- cross-links
  imported_modules TEXT[],           -- from dependency_graph.imports_map[file_path]
  imported_by_files TEXT[],          -- from dependency_graph.imported_by
  
  -- provenance
  commit_sha VARCHAR(40),            -- from head_commit
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

### Retrieval Strategy

1. **Query embedding** → find top-k by vector similarity
2. **Filter by risk_level** (optional) → exclude high-risk areas if user preference
3. **Expand via co_changes_with** → add related files for broader context
4. **Load source_content** from raw layer
5. **Attach metadata** (authors, conventions) for response grounding

### Citation Building

From a retrieved chunk:
```
Source: {file_path}:{start_line}-{end_line}
Last Modified By: {authors[0]} ({authorship_summary[file_path].total_commits} commits)
Risk Level: {risk_level}
Related Files: {co_changes_with}
Relevant Conventions: [conventions.testing.test_framework, ...]
```

---

## 8. Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-03-16 | Added risk_levels, co_change_pairs, authorship, dependency_graph, conventions; snapshot.json enrichment |
| 1.0 | 2026-01-XX | Initial release: structure, hotspots only |

---

## 9. FAQ

**Q: What if dependency_graph is empty?**  
A: AST parsing failed or tree-sitter is not installed. Install the `[ast]` extra to enable import extraction. Check pipeline logs.

**Q: Can co_change_pairs be empty?**  
A: Yes, if no file pairs co-occur ≥3 times. This is valid.

**Q: Are file paths absolute or relative?**  
A: Always relative to repo root, with forward slashes (/).

**Q: What if authorship has an author with no email?**  
A: Git logs are trusted as-is. Malformed authors may appear as-is.

**Q: Should RAG team use transform.json or snapshot.json?**  
A: Either works. `snapshot.json` has the same data with cleaner field names (risk_matrix vs risk_levels, authorship_summary vs authorship). Choice is stylistic.

---

## 10. Contact & Updates

Schema questions? Contact ETL team.  
Need a new field? File an issue with:
- Proposed field name
- Type and constraints
- Use case (RAG, analytics, UI)
- Example value

Changes to this schema are backward-compatible or marked clearly.