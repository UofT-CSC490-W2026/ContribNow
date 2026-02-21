# ContribNow

CSC490 project by:
- Louis Ryan Tan
- Janis Joplin
- Maverick Luke
- Razan Ahsan Rifandi

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
- `data/raw_<run_id>`
- `data/transform_<run_id>`
- `data/output_<run_id>`

Experimental index stage (for local RAG prototyping):

```bash
.venv/bin/python scripts/run_pipeline.py \
  --repo "https://github.com/pallets/markupsafe.git" \
  --experimental-index
```

This writes to `data/index_<run_id>` with:
- `documents.jsonl` chunks
- `inverted_index.json` token lookup
- `metadata.json`
- `index_registry.json`

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
.venv/bin/python -m src.pipeline.index --output-root "data/output_<run_id>" --index-root "data/index_<run_id>"
```
