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
  "ingest_schema_version": 2,
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
  "total_directories": 89,
  "file_extensions": {
    ".py": 342,
    ".md": 45,
    ".json": 12,
    ...
  },
  "primary_language": "Python"
}
```
- **Type:** Object
- **Fields:**
  - `total_files`: Integer, count of non-ignored files
  - `total_directories`: Integer, directory count
  - `file_extensions`: Object<ext_name: count>
  - `primary_language`: String, inferred from file distribution
- **Purpose:** High-level repository statistics
- **Constraint:** Extensions are lowercase with leading dot

### 3.5 hotspots

```json
"hotspots": [
  {
    "path": "src/core.py",
    "touch_count": 87,
    "risk_level": "high"
  },
  {
    "path": "src/utils.py",
    "touch_count": 42,
    "risk_level": "medium"
  }
]
```

- **Type:** Array of Objects
- **Fields per item:**
  - `path`: String, relative file path from repo root
  - `touch_count`: Integer ≥ 0, number of commits touching this file
  - `risk_level`: Enum ("high" | "medium" | "low")
- **Ordering:** Sorted by `touch_count` descending
- **Purpose:** Identify frequently-changing files
- **RAG Usage:** Prioritize chunks from high-touch files, flag as potentially unstable

### 3.6 risk_levels

```json
"risk_levels": {
  "src/core.py": {
    "risk_level": "high",
    "risk_score": 0.82,
    "factors": {
      "churn_score": 0.85,
      "author_diversity": 0.70,
      "coupling_degree": 0.75
    }
  },
  "src/utils.py": {
    "risk_level": "medium",
    "risk_score": 0.58,
    "factors": {
      "churn_score": 0.50,
      "author_diversity": 0.60,
      "coupling_degree": 0.65
    }
  }
}
```

- **Type:** Object<filepath: RiskRecord>
- **RiskRecord Fields:**
  - `risk_level`: Enum ("high" | "medium" | "low")
  - `risk_score`: Float, 0.0 to 1.0
  - `factors`: Object with three scores (each 0.0–1.0)
    - `churn_score`: 50% weight, files changed frequently
    - `author_diversity`: 30% weight, modified by many authors
    - `coupling_degree`: 20% weight, co-changes with other files
- **Scoring Formula:**
  ```
  risk_score = (0.5 × churn_score) + (0.3 × author_diversity) + (0.2 × coupling_degree)
  ```
- **Thresholds:**
  - `high`: risk_score > 0.7
  - `medium`: risk_score ≥ 0.4 and ≤ 0.7
  - `low`: risk_score < 0.4
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
"authorship": {
  "src/core.py": {
    "total_commits": 45,
    "distinct_authors": 8,
    "primary_contributors": [
      {"author": "alice@example.com", "commits": 18},
      {"author": "bob@example.com", "commits": 12},
      {"author": "charlie@example.com", "commits": 7}
    ]
  },
  "src/utils.py": {
    "total_commits": 22,
    "distinct_authors": 4,
    "primary_contributors": [
      {"author": "alice@example.com", "commits": 10},
      {"author": "david@example.com", "commits": 8}
    ]
  }
}
```

- **Type:** Object<filepath: AuthorshipRecord>
- **AuthorshipRecord Fields:**
  - `total_commits`: Integer > 0, sum of all commits touching this file
  - `distinct_authors`: Integer > 0, count of unique authors
  - `primary_contributors`: Array of ContributorRecord (sorted by commits desc)
    - `author`: String, author email from git log
    - `commits`: Integer, commit count by this author for this file
- **Constraint:** `primary_contributors` typically top 5 (no strict limit)
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
  - Sources: Extracted via AST (if tree-sitter available) or regex fallback
- **imported_by:** Object<module_name: Array<filepaths>>
  - Keys: Module/package names (can be builtins, thirds-party, or local)
  - Values: List of files that import this module
  - Auto-built from imports_map
- **Note:** Optional field, may be empty dict if AST unavailable or no imports detected
- **AST Coverage:** Python (full), JavaScript/TypeScript (full), Java (full), others (regex fallback)
- **Purpose:** Build code dependency graph for relationship-aware retrieval
- **RAG Usage:** Given a chunk, retrieve related chunks via dependency_graph; visualize import relationships

### 3.10 conventions

```json
"conventions": {
  "testing": {
    "test_framework": "pytest",
    "test_location_pattern": "tests/",
    "evidence_files": ["pytest.ini", "setup.cfg", "pyproject.toml"]
  },
  "linting": {
    "linters_detected": ["ruff", "black"],
    "config_files": [".ruff.toml", "pyproject.toml"]
  },
  "ci_cd": {
    "platforms": ["GitHub Actions"],
    "workflow_files": [".github/workflows/tests.yml"]
  },
  "contribution_docs": {
    "files_found": ["CONTRIBUTING.md"],
    "has_contributing_guide": true
  },
  "package_manager": {
    "manager": "pip",
    "config_files": ["setup.py", "pyproject.toml", "requirements.txt"]
  }
}
```

- **Type:** Object with keys: `testing`, `linting`, `ci_cd`, `contribution_docs`, `package_manager`
- **Sub-schemas:**
  - **testing:** Boolean field `test_framework` (string or null), `test_location_pattern` (string), `evidence_files` (array)
  - **linting:** `linters_detected` (array of names), `config_files` (array of paths)
  - **ci_cd:** `platforms` (array), `workflow_files` (array)
  - **contribution_docs:** `files_found` (array), `has_contributing_guide` (boolean)
  - **package_manager:** `manager` (string, e.g., "pip", "npm"), `config_files` (array)
- **Purpose:** Surface practical contribution norms for onboarding guides
- **RAG Usage:** Mention conventions in generated summaries; suggest adherence in recommendations

### 3.11 transform_metadata

```json
"transform_metadata": {
  "schema_version": 2,
  "transform_timestamp": "2026-03-16T15:23:45Z",
  "git_depth": 500,
  "top_n_hotspots": 20,
  "co_change_threshold": 3
}
```

- **Type:** Object
- **Fields:**
  - `schema_version`: Integer, current version is 2
  - `transform_timestamp`: ISO 8601 string, when transform ran
  - `git_depth`: Integer, depth of git clone used
  - `top_n_hotspots`: Integer, how many hotspots were computed
  - `co_change_threshold`: Integer, minimum co-occurrences to include pair
- **Purpose:** Pipeline operational metadata and versioning
- **RAG Usage:** Interpret data version; understand pipeline parameters

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
- **authorship:** One entry per source file (same as hotspots count)
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

## 6. Integration Guide for RAG Layer

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

## 7. Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-03-16 | Added risk_levels, co_change_pairs, authorship, dependency_graph, conventions; snapshot.json enrichment |
| 1.0 | 2026-01-XX | Initial release: structure, hotspots only |

---

## 8. FAQ

**Q: What if dependency_graph is empty?**  
A: AST parsing failed or was disabled. Regex fallback may still extract basic imports. Check transform_metadata.schema_version and pipeline logs.

**Q: Can co_change_pairs be empty?**  
A: Yes, if no file pairs co-occur ≥3 times. This is valid.

**Q: Are file paths absolute or relative?**  
A: Always relative to repo root, with forward slashes (/).

**Q: What if authorship has an author with no email?**  
A: Git logs are trusted as-is. Malformed authors may appear as-is.

**Q: Should RAG team use transform.json or snapshot.json?**  
A: Either works. `snapshot.json` has the same data with cleaner field names (risk_matrix vs risk_levels, authorship_summary vs authorship). Choice is stylistic.

---

## 9. Contact & Updates

Schema questions? Contact ETL team.  
Need a new field? File an issue with:
- Proposed field name
- Type and constraints
- Use case (RAG, analytics, UI)
- Example value

Changes to this schema are backward-compatible or marked clearly.
