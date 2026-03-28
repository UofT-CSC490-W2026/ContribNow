import type { GenerateOnboardingRequest, GenerateOnboardingResponse } from "../types";

/* v8 ignore next */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function isMockMode() {
  return import.meta.env.VITE_USE_MOCK === "true";
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

const MOCK_DOCUMENT = `# Onboarding Guide: pallets/markupsafe

## 1. Project Overview
MarkupSafe is a Python library that implements a text object that escapes characters for safe use in HTML and XML. It is widely used as a dependency by Jinja2, Flask, and many other projects in the Python ecosystem.

**Primary Language:** Python
**License:** BSD-3-Clause
**Stars:** 650+

## 2. Tech Stack
- **Language:** Python 3.8+
- **Build System:** setuptools with \`pyproject.toml\`
- **Testing:** pytest
- **CI/CD:** GitHub Actions
- **Documentation:** Sphinx + ReadTheDocs

## 3. Repository Structure
| Path | Purpose |
|------|---------|
| \`src/markupsafe/\` | Core library code |
| \`src/markupsafe/_speedups.c\` | C extension for performance |
| \`tests/\` | Test suite |
| \`docs/\` | Sphinx documentation |
| \`pyproject.toml\` | Project metadata and build config |

## 4. Setup Instructions
\`\`\`bash
git clone https://github.com/pallets/markupsafe.git
cd markupsafe
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
\`\`\`

## 5. How to Run Locally
\`\`\`bash
# Run the test suite
pytest

# Build documentation
cd docs && make html
\`\`\`

## 6. Development Workflow
1. Fork the repository and create a feature branch
2. Make changes and add tests
3. Run \`pytest\` to ensure all tests pass
4. Submit a pull request against the \`main\` branch
5. Maintainers will review and provide feedback

## 7. First Contribution Tips
- **Good first issues:** Look for issues labeled \`good first issue\`
- **Hot files:** \`src/markupsafe/__init__.py\` has the most activity (12 contributors, 45 commits)
- **Risk areas:** \`_speedups.c\` is high-risk — changes here need careful review
- **Co-changed files:** \`__init__.py\` and \`_speedups.c\` are often modified together

## 8. Known Gaps / Things to Confirm
- Check if the C extension build works on your platform
- Confirm Python version compatibility for your environment
`;

async function mockGenerateOnboarding(
  params: GenerateOnboardingRequest
): Promise<GenerateOnboardingResponse> {
  // Simulate network + LLM generation delay
  await new Promise((resolve) => setTimeout(resolve, 3000));

  if (params.accessKey !== "test") {
    throw new ApiError(401, "Invalid access key");
  }

  return {
    success: true,
    document: MOCK_DOCUMENT.replace(
      "pallets/markupsafe",
      new URL(params.repoUrl).pathname.slice(1)
    ),
    storageKey: `outputs/mock-repo-id/v1.md`,
    fromCache: params.forceRegenerate ? false : Math.random() > 0.5,
    version: 1,
  };
}

export async function generateOnboarding(
  params: GenerateOnboardingRequest,
  signal?: AbortSignal
): Promise<GenerateOnboardingResponse> {
  if (isMockMode()) {
    return mockGenerateOnboarding(params);
  }

  const response = await fetch(`${API_BASE_URL}/generate-onboarding`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      errorBody.detail || "Request failed"
    );
  }

  return response.json();
}

export async function healthCheck(): Promise<boolean> {
  if (isMockMode()) return true;

  try {
    const response = await fetch(`${API_BASE_URL}/`);
    return response.ok;
  } catch {
    return false;
  }
}
