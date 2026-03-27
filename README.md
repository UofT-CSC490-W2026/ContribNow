# ContribNow

CSC490 project by:
- Louis Ryan Tan
- Janis Joplin
- Maverick Luke
- Razan Ahsan Rifandi

## Test Coverage

<!-- Pytest Coverage Comment:Begin -->
Coverage report will appear here after CI runs.
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
