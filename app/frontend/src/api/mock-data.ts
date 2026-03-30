import type {
  AnalyzeRequest,
  AnalyzeResponse,
  AskRequest,
  AskResponse,
  CoChangePair,
  Conventions,
  DependencyGraph,
  FileAuthorship,
  Hotspot,
  RiskLevel,
} from "../types";

export const MOCK_RUN_ID = "mock-run-1";

export const MOCK_DOCUMENT = `# Onboarding Guide: pallets/markupsafe

## 1. Project Overview
MarkupSafe implements a text object that escapes characters for safe HTML and XML use.
It is a core dependency of Jinja2 and Flask.

**Primary Language:** Python
**License:** BSD-3-Clause

## 2. Tech Stack
- **Language:** Python 3.8+
- **Build:** setuptools / pyproject.toml
- **Testing:** pytest
- **CI/CD:** GitHub Actions
- **Docs:** Sphinx + ReadTheDocs

## 3. Repository Structure
| Path | Purpose |
|------|---------|
| \`src/markupsafe/\` | Core library |
| \`src/markupsafe/_speedups.c\` | C extension |
| \`tests/\` | Test suite |
| \`docs/\` | Sphinx docs |

## 4. Setup Instructions
\`\`\`bash
git clone https://github.com/pallets/markupsafe.git
cd markupsafe
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
\`\`\`

## 5. How to Run Locally
\`\`\`bash
pytest
cd docs && make html
\`\`\`

## 6. Development Workflow
1. Fork and create a feature branch
2. Add changes and tests
3. Run \`pytest\`
4. Open a pull request against \`main\`

## 7. First Contribution Tips
- Look for issues labeled \`good first issue\`
- Hot file: \`src/markupsafe/__init__.py\` (12 contributors, 45 commits)
- \`_speedups.c\` is high-risk — coordinate with maintainers before editing

## 8. Known Gaps / Things to Confirm
- Verify the C extension builds on your platform
- Confirm Python version compatibility for your environment
`;

export const MOCK_HOTSPOTS: Hotspot[] = [
  {
    path: "src/markupsafe/__init__.py",
    touch_count: 87,
    last_touched: "2024-03-15",
  },
  {
    path: "src/markupsafe/_speedups.c",
    touch_count: 42,
    last_touched: "2024-02-20",
  },
  {
    path: "src/markupsafe/_native.py",
    touch_count: 18,
    last_touched: "2024-01-10",
  },
  {
    path: "tests/test_markupsafe.py",
    touch_count: 12,
    last_touched: "2024-03-10",
  },
  {
    path: "src/markupsafe/sandbox.py",
    touch_count: 8,
    last_touched: "2023-12-05",
  },
];

export const MOCK_RISK_LEVELS: RiskLevel[] = [
  {
    path: "src/markupsafe/__init__.py",
    risk_level: "high",
    risk_score: 0.82,
    factors: { touch_count: 87, distinct_authors: 8, co_change_degree: 5 },
  },
  {
    path: "src/markupsafe/_speedups.c",
    risk_level: "medium",
    risk_score: 0.55,
    factors: { touch_count: 42, distinct_authors: 4, co_change_degree: 3 },
  },
  {
    path: "src/markupsafe/_native.py",
    risk_level: "medium",
    risk_score: 0.45,
    factors: { touch_count: 18, distinct_authors: 3, co_change_degree: 2 },
  },
  {
    path: "tests/test_markupsafe.py",
    risk_level: "low",
    risk_score: 0.22,
    factors: { touch_count: 12, distinct_authors: 5, co_change_degree: 1 },
  },
  {
    path: "src/markupsafe/sandbox.py",
    risk_level: "low",
    risk_score: 0.15,
    factors: { touch_count: 8, distinct_authors: 2, co_change_degree: 0 },
  },
];

export const MOCK_CONVENTIONS: Conventions = {
  test_framework: { name: "pytest", config_path: "pytest.ini" },
  test_dirs: ["tests/"],
  linters: [
    { name: "ruff", config_path: "pyproject.toml" },
    { name: "black", config_path: "pyproject.toml" },
  ],
  ci_pipelines: [
    { platform: "GitHub Actions", config_path: ".github/workflows/tests.yml" },
  ],
  contribution_docs: ["CONTRIBUTING.md"],
  package_manager: "poetry",
};

export const MOCK_AUTHORSHIP: FileAuthorship[] = [
  {
    path: "src/markupsafe/__init__.py",
    total_commits: 87,
    distinct_authors: 8,
    primary_contributors: [
      { name: "Alice Smith", commit_count: 18 },
      { name: "Bob Jones", commit_count: 12 },
      { name: "Charlie Lee", commit_count: 7 },
    ],
  },
  {
    path: "src/markupsafe/_speedups.c",
    total_commits: 42,
    distinct_authors: 4,
    primary_contributors: [
      { name: "Alice Smith", commit_count: 20 },
      { name: "David Kim", commit_count: 12 },
    ],
  },
  {
    path: "src/markupsafe/_native.py",
    total_commits: 18,
    distinct_authors: 3,
    primary_contributors: [{ name: "Bob Jones", commit_count: 9 }],
  },
];

export const MOCK_CO_CHANGES: CoChangePair[] = [
  {
    file_a: "src/markupsafe/__init__.py",
    file_b: "src/markupsafe/_speedups.c",
    co_change_count: 12,
  },
  {
    file_a: "src/markupsafe/__init__.py",
    file_b: "src/markupsafe/_native.py",
    co_change_count: 8,
  },
  {
    file_a: "src/markupsafe/_speedups.c",
    file_b: "tests/test_markupsafe.py",
    co_change_count: 5,
  },
];

export const MOCK_DEPENDENCIES: DependencyGraph = {
  imports_map: {},
  imported_by: {},
};

export async function mockAnalyze(params: AnalyzeRequest): Promise<AnalyzeResponse> {
  await new Promise((resolve) => setTimeout(resolve, 3000));
  return {
    success: true,
    runId: MOCK_RUN_ID,
    document: MOCK_DOCUMENT.replace(
      "pallets/markupsafe",
      new URL(params.repoUrl).pathname.slice(1)
    ),
    version: 1,
  };
}

export async function mockAsk(params: AskRequest): Promise<AskResponse> {
  await new Promise((resolve) => setTimeout(resolve, 500));
  const q = params.question.toLowerCase();

  if (q.includes("test") || q.includes("testing")) {
    return {
      answer: "The project uses **pytest**. Run `pytest` from the project root.",
      citations: [
        {
          filePath: "pytest.ini",
          startLine: 1,
          endLine: 5,
          snippet: "[pytest]\naddopts = -v\ntestpaths = tests",
        },
      ],
    };
  }

  if (q.includes("setup") || q.includes("install")) {
    return {
      answer: 'Install with `pip install -e ".[dev]"`.',
      citations: [
        {
          filePath: "pyproject.toml",
          startLine: 12,
          endLine: 18,
          snippet: '[project.optional-dependencies]\ndev = ["pytest", "coverage"]',
        },
      ],
    };
  }

  return {
    answer: "Try asking about setup, testing, or specific files.",
    citations: [],
  };
}
