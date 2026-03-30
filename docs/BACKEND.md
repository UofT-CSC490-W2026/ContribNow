# Backend Overview

This document describes the current `backend/` service in ContribNow: what it runs, how requests flow through it, which files matter, and which parts are still legacy or transitional.

## Purpose

The backend is a FastAPI application packaged for AWS Lambda through Mangum.

Its main responsibilities today are:

- Generate onboarding documents with Bedrock from repo metadata supplied by the local app
- Store and load onboarding markdown in S3
- Track which onboarding docs belong to which access key in RDS
- Store and query vector embeddings in PostgreSQL with `pgvector`
- Save and load chat history in RDS

The backend does **not** clone repositories itself. The local app is expected to gather repo metadata and send it in the request body.

## Directory Map

```text
backend/
├── Dockerfile
├── requirements.txt
├── onboarding_guide_ex.md         # example/generated markdown artifact
└── app/
    ├── main.py                    # FastAPI routes + app lifecycle
    ├── models.py                  # request/response models
    ├── config.py                  # environment loading + logger
    ├── constants.py               # shared constants
    └── services/
        ├── auth.py                # access-key verification
        ├── db.py                  # psycopg connection factory
        ├── db_init.py             # table/schema initialization
        ├── llm.py                 # Bedrock invocation
        ├── prompt_builder.py      # onboarding prompt template
        ├── retrieval.py           # prompt context construction
        ├── rds.py                 # RDS helpers for repo/chat metadata
        ├── s3.py                  # S3 helpers for markdown objects
        ├── pgvector.py            # pgvector-backed vector store
        ├── pgvector_interfaces.py # vector dataclasses/interfaces
        ├── storage.py             # legacy versioned markdown storage
        └── __init__.py
```

## Runtime and Deployment

The container entrypoint is defined in [backend/Dockerfile](/c:/Users/owner/terminal/csc490/ContribNow/backend/Dockerfile). It uses the AWS Lambda Python 3.12 base image, installs `backend/requirements.txt`, copies `app/`, and runs:

```python
CMD ["app.main.handler"]
```

The Lambda handler is `handler = Mangum(app, lifespan="auto")` in [backend/app/main.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/main.py).

Dependencies in [backend/requirements.txt](/c:/Users/owner/terminal/csc490/ContribNow/backend/requirements.txt):

- `fastapi`
- `mangum`
- `boto3`
- `psycopg[binary]`
- `uvicorn`
- `dotenv`
- `numpy`

## Environment Variables

Loaded in [backend/app/config.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/config.py).

Required:

- `ACCESS_KEYS`
- `BEDROCK_MODEL_ID`
- `S3_BUCKET_NAME`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

Optional:

- `AWS_REGION` default: `ca-central-1`
- `DB_SSLMODE` default: `require`

If required variables are missing, the app raises on import.

## App Startup

Startup is handled by the FastAPI lifespan function in [backend/app/main.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/main.py).

On startup it:

1. Creates the `onboarding_user_repos` table if needed
2. Creates the `chat_history` table if needed
3. Initializes the `PgVectorStore`
4. Ensures the `vector` extension and `rag_vectors` table exist

These initialization helpers live in [backend/app/services/db_init.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/db_init.py).

## Core Models

Defined in [backend/app/models.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/models.py).

Important onboarding models:

- `GenerateOnboardingRequest`
- `GenerateOnboardingResponse`
- `RepoSnapshot`
- `OnboardingSnapshot`
- `RepoFileContent`
- `SaveChatRequest`
- `ChatMessage`

### `GenerateOnboardingRequest`

Current fields:

- `repoUrl: HttpUrl`
- `repoSlug: str`
- `userPrompt: str | None`
- `forceRegenerate: bool`
- `repoSnapshot: RepoSnapshot | None`
- `onboardingSnapshot: OnboardingSnapshot | None`

### `RepoSnapshot`

Used for local-app-supplied file inventory and selected file contents:

- `repo_slug`
- `files`
- `selected_file_contents`

`selected_file_contents` also accepts incoming `file_contents` as an alias for compatibility.

### `OnboardingSnapshot`

Used for pipeline-derived enriched metadata:

- `repo_slug`
- `repo_url`
- `head_commit`
- `structure_summary`
- `hotspots`
- `risk_matrix`
- `co_change_pairs`
- `authorship_summary`
- `dependency_graph`
- `conventions`
- `transform_metadata`
- `load_metadata`

### `SaveChatRequest`

Used by `POST /chat-history/save`.

Fields:

- `repo_slug`
- `role`
- `message`
- `created_at`

### `ChatMessage`

Used for persisted and returned chat entries:

- `role`
- `message`
- `created_at`

## Request Flow: Onboarding Generation

The main endpoint is `POST /generate-onboarding` in [backend/app/main.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/main.py).

### High-level flow

1. Validate `X-Access-Key` with `verify_key()`
2. Read `repoSlug` from the request body
3. Build S3 key:

```text
onboarding_docs/{access_key}/{repo_slug}.md
```

4. If `forceRegenerate` is false, attempt to load the cached markdown from S3
5. If no cached doc is found:
   - Build repo context with `retrieve_context()`
   - Build prompt with `build_prompt()`
   - Generate markdown with Bedrock via `generate_document()`
   - Save markdown to S3
   - Save `(access_key, repo_slug)` in RDS
6. Return the markdown and storage key

### Current storage behavior

`generate_onboarding` now uses the same storage convention as `/onboarding-doc/save`.

That means:

- Cached onboarding docs are loaded directly from S3 by repo slug
- Repo ownership metadata is stored in `onboarding_user_repos`
- The older versioned cache path is no longer the active onboarding flow

## Context Building for Bedrock

Prompt context is built in [backend/app/services/retrieval.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/retrieval.py).

This module merges two sources:

- `repoSnapshot`
  - full file inventory
  - selected file excerpts
- `onboardingSnapshot`
  - structure summary
  - hotspots
  - risk matrix
  - co-change pairs
  - authorship summary
  - conventions

### What retrieval includes

The generated context contains:

- repository URL
- repository slug
- total file count
- a capped list of file paths
- top-level directory counts
- file-type counts
- start-here candidates
- hotspots
- risk areas
- co-change relationships
- contributor summary
- ownership examples
- conventions summary
- selected file excerpts

### Prompt budgeting

The retrieval layer intentionally caps prompt size:

- max file list entries: `400`
- max chars per selected file excerpt: `4000`
- max chars across all selected file excerpts: `16000`

This keeps Bedrock prompts manageable while still grounding the response.

## Prompt Template

Defined in [backend/app/services/prompt_builder.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/prompt_builder.py).

The prompt requires exactly these eight sections:

1. Project Overview
2. Tech Stack
3. Repository Structure
4. Setup Instructions
5. How to Run Locally
6. Development Workflow
7. First Contribution Tips
8. Known Gaps / Things to Confirm

The prompt also explicitly tells the model to:

- write only markdown
- avoid unsupported claims
- stay concise enough to fit output limits
- prefer important commands, paths, and risks

## Bedrock Invocation

Handled by [backend/app/services/llm.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/llm.py).

Current request shape:

- Anthropic Bedrock API format
- `max_tokens = 2200`
- `temperature = 0.2`

The service concatenates all returned text blocks and raises if Bedrock returns no text.

## S3 Storage

Handled by [backend/app/services/s3.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/s3.py).

Helpers:

- `save_object_to_s3(object_key, obj)`
- `load_object_from_s3(object_key)`
- `delete_object_from_s3(object_key)`

These return booleans or `None` instead of raising AWS errors directly, and log failures through the shared logger.

### Onboarding document path

Defined by [backend/app/constants.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/constants.py):

```text
onboarding_docs/{access_key}/{repo_slug}.md
```

## RDS Metadata and Chat History

Handled by [backend/app/services/rds.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/rds.py).

### Onboarding metadata

Table: `onboarding_user_repos`

Tracks which repo slugs belong to which access key.

Used by:

- `/generate-onboarding`
- `/onboarding-doc/save`
- `/onboarding-doc/load-all`
- `/onboarding-doc/delete`

### Chat history

Table: `chat_history`

Used by:

- `/chat-history/save`
- `/chat-history/load`
- `/chat-history/delete`

Messages are stored and queried by the composite key `(access_key, repo_slug)`.

Within each repo, messages are append-only and loaded in chronological order.

## PostgreSQL / pgvector

Vector interfaces are defined in [backend/app/services/pgvector_interfaces.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/pgvector_interfaces.py).

Implementation is in [backend/app/services/pgvector.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/pgvector.py).

### Current schema

`PgVectorStore.ensure_schema()` creates:

- extension: `vector`
- schema: `public`
- table: `rag_vectors`

Stored columns include:

- `repo_slug`
- `head_commit`
- `file_path`
- `start_line`
- `end_line`
- `embedding`
- timestamps

### Supported operations

- `upsert(records)`
- `delete_by_repo(repo_slug)`
- `search(query_vector, k, repo_slug, head_commit, file_path)`

The app initializes `PgVectorStore` with:

- schema: `public`
- table: `rag_vectors`
- embedding dimension: `32`

## Endpoint Inventory

Defined in [backend/app/main.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/main.py).

### Health

- `GET /`
- `GET /debug-db`

### Onboarding

- `POST /generate-onboarding`
- `POST /onboarding-doc/save`
- `GET /onboarding-doc/load`
- `GET /onboarding-doc/load-all`
- `DELETE /onboarding-doc/delete`

### Vector store

- `POST /vector/store`
- `POST /vector/query`
- `DELETE /vector/delete-by-repo`

### Chat history

- `POST /chat-history/save`
- `GET /chat-history/load`
- `DELETE /chat-history/delete`

### Commented / inactive routes

These are present but commented out:

- `/rds/create-table`
- `/rds/save`
- `/rds/load`
- `/s3/save`
- `/s3/load`

## Authentication Model

Authentication is simple shared-key auth.

Implemented in [backend/app/services/auth.py](/c:/Users/owner/terminal/csc490/ContribNow/backend/app/services/auth.py).

Each protected route expects:

```text
X-Access-Key: <value>
```

The key is checked against the comma-separated `ACCESS_KEYS` environment variable.

## Legacy / Transitional Modules

Some backend files are still present but are not the active onboarding path anymore.

### `services/storage.py`

This writes markdown to:

```text
outputs/{repo_id}/v{version}.md
```

That is the older versioned document storage flow.

### `services/cache.py`

This manages the `onboarding_documents` table and versioned cache records keyed by normalized repo URL.

The current `generate_onboarding` route no longer uses this path. The module remains in the repo and still has tests, but it is now effectively legacy unless reintroduced.

### Commented generic save/load endpoints

There are generic RDS/S3 helper routes commented out in `main.py`. They are not part of the active public backend behavior.

## Error Behavior

Common patterns:

- `401` for invalid access key
- `400` for invalid onboarding generation input such as missing `repoSlug`
- `400` for invalid chat-history input such as missing `repo_slug`
- `500` for generation, S3, RDS, or vector-store failures

Most service helpers log the underlying exception and return a boolean or structured error, while the route layer converts that into an `HTTPException`.

## Suggested Mental Model

If you are onboarding onto this backend quickly, think of it in four layers:

1. `main.py`
Route wiring, auth checks, and orchestration

2. `models.py`
Request and response contracts

3. `services/retrieval.py` + `prompt_builder.py` + `llm.py`
Onboarding generation pipeline

4. `services/s3.py`, `services/rds.py`, `services/pgvector.py`
Persistence and retrieval infrastructure

## Current Onboarding Contract

For onboarding generation, the local app should send:

- `repoUrl`
- `repoSlug`
- optional `userPrompt`
- optional `forceRegenerate`
- optional `repoSnapshot`
  - `repo_slug`
  - `files`
  - `selected_file_contents`
- optional `onboardingSnapshot`
  - pipeline metadata from `onboarding_snapshot.json`

This keeps the Lambda lightweight while still giving Bedrock enough context to produce a grounded onboarding guide.
