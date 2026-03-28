# ContribNow

CSC490 project by:
- Louis Ryan Tan
- Janis Joplin
- Maverick Luke
- Razan Ahsan Rifandi

## Test Coverage

<!-- Pytest Coverage Comment:Begin -->
<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/README.md"><img alt="Coverage" src="https://img.shields.io/badge/Coverage-100%25-brightgreen.svg" /></a><details><summary>Coverage Report </summary><table><tr><th>File</th><th>Stmts</th><th>Miss</th><th>Cover</th></tr><tbody><tr><td colspan="4"><b>src/pipeline</b></td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/ast_imports.py">ast_imports.py</a></td><td>142</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/ast_utils.py">ast_utils.py</a></td><td>45</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/cloud_sync.py">cloud_sync.py</a></td><td>166</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/ingest.py">ingest.py</a></td><td>159</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/load.py">load.py</a></td><td>83</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/transform.py">transform.py</a></td><td>216</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/utils.py">utils.py</a></td><td>14</td><td>0</td><td>100%</td></tr><tr><td colspan="4"><b>src/pipeline/chunking</b></td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/__init__.py">\_\_init\_\_.py</a></td><td>8</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/interfaces.py">interfaces.py</a></td><td>51</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/registry.py">registry.py</a></td><td>46</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/strategies.py">strategies.py</a></td><td>47</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/ts_base_strategy.py">ts_base_strategy.py</a></td><td>88</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/ts_java_strategy.py">ts_java_strategy.py</a></td><td>9</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/ts_javascript_strategy.py">ts_javascript_strategy.py</a></td><td>9</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/ts_jsx_strategy.py">ts_jsx_strategy.py</a></td><td>9</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/chunking/ts_py_strategy.py">ts_py_strategy.py</a></td><td>9</td><td>0</td><td>100%</td></tr><tr><td colspan="4"><b>src/pipeline/embedding</b></td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/embedding/__init__.py">\_\_init\_\_.py</a></td><td>4</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/embedding/batcher.py">batcher.py</a></td><td>46</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/embedding/interfaces.py">interfaces.py</a></td><td>41</td><td>0</td><td>100%</td></tr><tr><td colspan="4"><b>src/pipeline/embedding/providers</b></td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/embedding/providers/__init__.py">\_\_init\_\_.py</a></td><td>4</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/embedding/providers/huggingface_provider.py">huggingface_provider.py</a></td><td>43</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/embedding/providers/local_provider.py">local_provider.py</a></td><td>14</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/embedding/providers/openai_provider.py">openai_provider.py</a></td><td>58</td><td>0</td><td>100%</td></tr><tr><td colspan="4"><b>src/pipeline/indexing</b></td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/indexing/__init__.py">\_\_init\_\_.py</a></td><td>3</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/indexing/indexer.py">indexer.py</a></td><td>151</td><td>0</td><td>100%</td></tr><tr><td colspan="4"><b>src/pipeline/vector_store</b></td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/vector_store/__init__.py">\_\_init\_\_.py</a></td><td>4</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/vector_store/in_memory.py">in_memory.py</a></td><td>53</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/vector_store/interfaces.py">interfaces.py</a></td><td>27</td><td>0</td><td>100%</td></tr><tr><td>&nbsp; &nbsp;<a href="https://github.com/UofT-CSC490-W2026/ContribNow/blob/main/src/pipeline/vector_store/pgvector.py">pgvector.py</a></td><td>115</td><td>0</td><td>100%</td></tr><tr><td><b>TOTAL</b></td><td><b>1664</b></td><td><b>0</b></td><td><b>100%</b></td></tr></tbody></table></details>
<!-- Pytest Coverage Comment:End -->

## ETL Quickstart

Run from repo root with the helper script:

```bash
.venv/bin/python scripts/run_pipeline.py --repo "https://github.com/pallets/markupsafe.git"
```

Run multiple repos:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --repo "https://github.com/pallets/markupsafe.git" \
  --repo "https://github.com/pallets/click.git"
```

The script writes artifacts to:
- `data/raw_<run_id>` — Raw layer (source code, git history)
- `data/transform_<run_id>` — Transform layer (enriched metadata)
- `data/output_<run_id>` — Output layer (user-consumable format)

## Pipeline Output & Data Schema

The pipeline produces **enriched metadata** from code repositories:

**transform.json** contains:
- `hotspots` — Files ranked by change frequency
- `risk_levels` — Multi-factor risk scoring per file (churn, author diversity, coupling)
- `co_change_pairs` — Files frequently modified together (threshold ≥3 co-occurrences)
- `authorship` — Per-file author distribution and primary contributors
- `dependency_graph` — Import relationships extracted via AST
- `conventions` — Detected testing frameworks, linters, CI/CD platforms, contribution docs

**onboarding_snapshot.json** provides a clean projection:
- Same enriched fields as transform.json, renamed for clarity
- User-friendly format for UI, dashboards, and downstream tools
- Includes load metadata (generation timestamp, source path)

**For RAG Integration:** The RAG team consumes:
1. **transform.json / onboarding_snapshot.json** — Metadata (risk scores, dependencies, authorship)
2. **Raw layer (source files)** — Actual code content for embeddings and citations

**Full Data Reference:** See [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md) for:
- Exact field definitions, types, and constraints
- Recommended vector store schema
- Integration guidance for chunking/embedding layer

## Cloud-Safe Sync (Optional)

Create `.env` in repo root, for example:

```env
ENABLE_CLOUD_SYNC=true
TENANT_ID=<workspace-name>
USER_ID=<your-user-id>
TENANT_SALT=<replace-with-strong-random-secret>
CLOUD_DB_URL=postgresql://user:password@localhost:5432/<db-name>
```

Then run:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --repo "https://github.com/pallets/markupsafe.git" \
  --cloud-sync \
  --apply-schema
```

## Live PgVector Test

The repository includes a real integration test for `PgVectorStore` against a disposable local
Postgres instance with the `pgvector` extension.

Run it from the repo root:

```bash
bash scripts/run_pgvector_tests.sh
```

What the script does:
- Syncs the optional `cloud` dependencies if `psycopg` is missing in `.venv`
- Uses `PGVECTOR_TEST_DB_URL` directly if you already have a Postgres/pgvector instance
- Otherwise starts a temporary `pgvector/pgvector:pg17` container on `localhost:54329`
- Sets `RUN_PG_VECTOR_TESTS=1` and `PGVECTOR_TEST_DB_URL`
- Runs `tests.test_postgres_vector_store.TestPgVectorStore.test_live_round_trip`

You can override defaults with env vars such as `PGVECTOR_PORT`, `PGVECTOR_DB`,
`PGVECTOR_USER`, `PGVECTOR_PASSWORD`, or `PGVECTOR_IMAGE`.

## Manual CLI (Alternative)

```bash
.venv/bin/python -m src.pipeline.ingest --repo "<repo_url>" --raw-root "data/raw_<run_id>"
.venv/bin/python -m src.pipeline.transform --raw-root "data/raw_<run_id>" --transform-root "data/transform_<run_id>" --top-n-hotspots 20
.venv/bin/python -m src.pipeline.load --transform-root "data/transform_<run_id>" --output-root "data/output_<run_id>"
```

## Terraform usage guide

1. Install [Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli) and [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
2. Run `aws configure` and enter your credentials.
3. Navigate to environment
```
cd terraform/environments/dev
```
4. Run terraform
```
terraform init
terraform plan
terraform apply -var=db_password='<your password here>'
```
5. Sync `.env` from Terraform outputs
```
export DB_PASSWORD='<your password here>' # or omit to get a hidden prompt
.venv/bin/python scripts/sync_env_from_terraform.py \
  --terraform-dir terraform/environments/prod \
  --tenant-id workspace-dev \
  --user-id <your-user-id> \
  --tenant-salt <replace-with-strong-random-secret>
```
6. To destroy resources, run `terraform destroy`
