CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS repos (
    repo_id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    repo_fingerprint TEXT NOT NULL,
    canonical_repo_ref_hash TEXT NOT NULL,
    UNIQUE (tenant_id, repo_fingerprint)
);

CREATE TABLE IF NOT EXISTS repo_versions (
    version_id BIGSERIAL PRIMARY KEY,
    repo_id BIGINT NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
    head_commit TEXT NOT NULL,
    version_key TEXT NOT NULL UNIQUE,
    structure_json JSONB NOT NULL,
    schema_version INTEGER NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS version_hotspots (
    version_id BIGINT NOT NULL REFERENCES repo_versions(version_id) ON DELETE CASCADE,
    file_hash TEXT NOT NULL,
    touch_count INTEGER NOT NULL,
    last_touched TIMESTAMPTZ NULL,
    PRIMARY KEY (version_id, file_hash)
);

CREATE TABLE IF NOT EXISTS version_files (
    version_id BIGINT NOT NULL REFERENCES repo_versions(version_id) ON DELETE CASCADE,
    file_path_hash TEXT NOT NULL,
    content_hash TEXT NULL,
    PRIMARY KEY (version_id, file_path_hash)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    sync_run_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    repo_fingerprint TEXT NOT NULL,
    head_commit TEXT NOT NULL,
    version_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'failed', 'partial')),
    error_summary TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_repo_versions_repo_id ON repo_versions (repo_id);
CREATE INDEX IF NOT EXISTS idx_repo_versions_version_key ON repo_versions (version_key);
CREATE INDEX IF NOT EXISTS idx_sync_runs_tenant_created ON sync_runs (tenant_id, created_at DESC);
