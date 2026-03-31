# ContribNow Desktop App

A desktop app that analyzes a GitHub repository and generates an onboarding guide, with an interactive Q&A chat powered by AWS Bedrock.

## Prerequisites

- Python 3.10+
- Node.js 18+
- Git (must be on PATH — used to clone repos at runtime)
- AWS credentials configured (`aws configure`) with access to Bedrock

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```
cp .env.example .env
```

| Variable | Description |
|---|---|
| `API_URL` | Base URL of the hosted ContribNow API |
| `API_TIMEOUT` | Timeout in seconds for the generate-onboarding API call (default: 120) |
| `MAX_FILE_SIZE` | Max file size in bytes before truncating content sent to the API (default: 100000) |
| `BEDROCK_AGENT_ID` | AWS Bedrock Agent ID for the Q&A chat feature |
| `BEDROCK_AGENT_ALIAS_ID` | AWS Bedrock Agent Alias ID |

AWS credentials are read from `~/.aws/credentials` via `aws configure`. 

## Running in Development

**Backend:**
```bash
cd app/
pip install -r requirements.txt
python -m uvicorn backend.main:app --port 8000
```

**Frontend:**
```bash
cd app/frontend/
npm install
npm run dev
```

The frontend dev server runs at `http://localhost:5173` and proxies API calls to the backend on port 8000.

## Building the .exe

Run from the repo root or `app/` directory:

```bash
app\build.bat
```

This will:
1. Build the React frontend with Vite
2. Copy the frontend dist into `app/frontend_dist/`
3. Run PyInstaller to produce `app/dist/ContribNow.exe`

The `.exe` is fully self-contained — it bundles the frontend, backend, and data pipeline. The only external requirement at runtime is **git** on the user's PATH.

Place a `.env` file next to `ContribNow.exe` before running it.

## Usage

1. Enter a public GitHub repository URL
2. Enter your access key
3. Optionally select a task type (fix bug, add feature, etc.)
4. Click **Analyze** — the app will clone the repo, run the analysis pipeline, and generate an onboarding guide
5. Use the **Chat** panel to ask questions about the codebase
