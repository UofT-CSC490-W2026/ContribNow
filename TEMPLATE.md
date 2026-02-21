# ContribNow ETL Run Template

Preferred runner:

```bash
.venv/bin/python scripts/run_pipeline.py --repo "https://github.com/pallets/markupsafe.git"
```

Multiple repos:

```bash
.venv/bin/python scripts/run_pipeline.py \
  --repo "https://github.com/pallets/markupsafe.git" \
  --repo "https://github.com/pallets/click.git" \
  --top-n-hotspots 20
```

Cloud-sync run (uses `.env`/env vars for DB + tenant config):

```bash
.venv/bin/python scripts/run_pipeline.py \
  --repo "https://github.com/pallets/markupsafe.git" \
  --cloud-sync \
  --apply-schema
```

Experimental local index (RAG prototype):

```bash
.venv/bin/python scripts/run_pipeline.py \
  --repo "https://github.com/pallets/markupsafe.git" \
  --experimental-index
```

Legacy manual steps are still supported via the Python module CLIs in `README.md`.
