# Click Contributor Onboarding Guide

## 1. Project Overview

**Click** is a Python package for creating command-line interfaces (CLIs) with minimal code.

- **Repository:** https://github.com/pallets/click (pallets__click)
- **Primary use:** Building composable CLI applications with decorators and groups
- **Key files to know:**
  - `README.md` – start here for project context
  - `docs/contrib.md` – contribution guidelines
  - `CHANGES.rst` – changelog (high-risk file; track carefully)

---

## 2. Tech Stack

- **Language:** Python
- **Testing:** pytest (configured in `pyproject.toml`)
- **Linting/Formatting:** ruff, editorconfig
- **CI/CD:** GitHub Actions
- **Documentation:** Sphinx (`.rst` and `.md` files in `docs/`)
- **Package management:** uv (see `uv.lock`)

---

## 3. Repository Structure

```
.
├── src/click/              # Main source code (18 files)
│   ├── core.py            # ⚠️ HIGH RISK – core CLI logic (62 commits)
│   ├── _termui_impl.py    # Terminal UI implementation
│   └── testing.py         # Testing utilities
├── tests/                 # Test suite (30 files)
│   ├── test_options.py    # ⚠️ MEDIUM RISK (33 commits)
│   ├── test_utils.py      # Utility tests
│   └── test_termui.py     # Terminal UI tests
├── docs/                  # Documentation (39 files)
│   ├── index.rst          # Main docs index
│   ├── api.md             # API reference
│   ├── contrib.md         # Contribution guide
│   └── *.rst              # Concept guides (commands, arguments, etc.)
├── examples/              # Example CLI scripts (39 files)
├── .github/workflows/     # CI/CD pipelines
│   ├── tests.yaml         # Test runner
│   └── publish.yaml       # Release automation
├── pyproject.toml         # Project config & dependencies
└── CHANGES.rst            # ⚠️ HIGH RISK – changelog (79 commits)
```

---

## 4. Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://example.com/pallets__click.git
   cd pallets__click
   ```

2. **Install dependencies** (using uv):
   ```bash
   uv sync
   ```
   Or with pip:
   ```bash
   pip install -e ".[dev]"
   ```

3. **Verify setup:**
   ```bash
   pytest --version
   ruff --version
   ```

---

## 5. How to Run Locally

- **Run tests:**
  ```bash
  pytest
  pytest tests/test_options.py -v  # specific test file
  ```

- **Run linter/formatter:**
  ```bash
  ruff check src/ tests/
  ruff format src/ tests/
  ```

- **Build documentation:**
  ```bash
  cd docs && make html
  ```

- **Run an example:**
  ```bash
  python examples/<example_name>.py
  ```

---

## 6. Development Workflow

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes** and write/update tests in `tests/`

3. **Run tests locally** before pushing:
   ```bash
   pytest
   ruff check .
   ```

4. **Update `CHANGES.rst`** if your change is user-facing (high-risk file—be careful)

5. **Commit with clear messages** and push

6. **Open a pull request** – use `.github/pull_request_template.md` as a guide

7. **CI runs automatically** via GitHub Actions (`.github/workflows/tests.yaml`)

---

## 7. First Contribution Tips

- **Start small:** Look at `tests/test_options.py` or `tests/test_utils.py` to understand test patterns
- **Read the docs:** `docs/contrib.md` and `docs/click-concepts.rst` explain core concepts
- **Core logic is in `src/click/core.py`:** This is the most-touched file; changes here need careful review
- **Co-changed files matter:** When editing `src/click/core.py`, also check `CHANGES.rst` and related tests
- **Use pre-commit hooks** (configured in `.pre-commit-config.yaml`) to catch issues early
- **Ask questions:** Check existing issues and pull requests before starting

---

## 8. Known Gaps / Things to Confirm

- **Exact Python version requirements** – check `pyproject.toml` for supported versions
- **Development environment setup** – confirm whether `uv` or `pip` is the preferred install method
- **Release process** – `.github/workflows/publish.yaml` exists but exact release steps should be confirmed with maintainers
- **Documentation build process** – verify `docs/conf.py` configuration and any special build requirements
- **Pre-commit hook enforcement** – confirm if `.pre-commit-config.yaml` is mandatory for all contributors
- **Ownership/code review expectations** – David Lord and Edward Girling appear as primary contributors; confirm review process