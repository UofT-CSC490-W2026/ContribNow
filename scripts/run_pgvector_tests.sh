#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
UV_BIN="${UV_BIN:-uv}"
DOCKER_BIN="${DOCKER_BIN:-docker}"
PGVECTOR_IMAGE="${PGVECTOR_IMAGE:-pgvector/pgvector:pg17}"
PGVECTOR_CONTAINER_NAME="${PGVECTOR_CONTAINER_NAME:-contribnow-pgvector-test-$RANDOM-$RANDOM}"
PGVECTOR_PORT="${PGVECTOR_PORT:-54329}"
PGVECTOR_DB="${PGVECTOR_DB:-contribnow_test}"
PGVECTOR_USER="${PGVECTOR_USER:-postgres}"
PGVECTOR_PASSWORD="${PGVECTOR_PASSWORD:-postgres}"
PGVECTOR_WAIT_SECONDS="${PGVECTOR_WAIT_SECONDS:-30}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "error: python interpreter not found at $PYTHON_BIN" >&2
  exit 1
fi

if ! command -v "$DOCKER_BIN" >/dev/null 2>&1; then
  echo "error: docker is required to run the live pgvector test" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c "import psycopg" >/dev/null 2>&1; then
  echo "psycopg is missing from $PYTHON_BIN; syncing the optional cloud dependencies..." >&2
  "$UV_BIN" sync --extra cloud
fi

if [[ -n "${PGVECTOR_TEST_DB_URL:-}" ]]; then
  export RUN_PG_VECTOR_TESTS=1
  echo "Running live PgVectorStore test against ${PGVECTOR_TEST_DB_URL}" >&2
  "$PYTHON_BIN" -m unittest tests.test_postgres_vector_store.TestPgVectorStore.test_live_round_trip
  exit 0
fi

cleanup() {
  "$DOCKER_BIN" stop "$PGVECTOR_CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  echo "error: docker is installed but the daemon is not reachable." >&2
  echo "set PGVECTOR_TEST_DB_URL to point at an existing pgvector database, or start docker and rerun." >&2
  exit 1
fi

"$DOCKER_BIN" run \
  --detach \
  --rm \
  --name "$PGVECTOR_CONTAINER_NAME" \
  --publish "${PGVECTOR_PORT}:5432" \
  --env "POSTGRES_DB=$PGVECTOR_DB" \
  --env "POSTGRES_USER=$PGVECTOR_USER" \
  --env "POSTGRES_PASSWORD=$PGVECTOR_PASSWORD" \
  "$PGVECTOR_IMAGE" >/dev/null

for _ in $(seq 1 "$PGVECTOR_WAIT_SECONDS"); do
  if "$DOCKER_BIN" exec "$PGVECTOR_CONTAINER_NAME" \
    pg_isready -U "$PGVECTOR_USER" -d "$PGVECTOR_DB" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! "$DOCKER_BIN" exec "$PGVECTOR_CONTAINER_NAME" \
  pg_isready -U "$PGVECTOR_USER" -d "$PGVECTOR_DB" >/dev/null 2>&1; then
  echo "error: pgvector container did not become ready within ${PGVECTOR_WAIT_SECONDS}s" >&2
  exit 1
fi

export RUN_PG_VECTOR_TESTS=1
export PGVECTOR_TEST_DB_URL="postgresql://${PGVECTOR_USER}:${PGVECTOR_PASSWORD}@localhost:${PGVECTOR_PORT}/${PGVECTOR_DB}"

for _ in $(seq 1 "$PGVECTOR_WAIT_SECONDS"); do
  if "$PYTHON_BIN" -c "import psycopg; conn = psycopg.connect('${PGVECTOR_TEST_DB_URL}'); conn.close()" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! "$PYTHON_BIN" -c "import psycopg; conn = psycopg.connect('${PGVECTOR_TEST_DB_URL}'); conn.close()" >/dev/null 2>&1; then
  echo "error: host-side connection to ${PGVECTOR_TEST_DB_URL} did not become ready within ${PGVECTOR_WAIT_SECONDS}s" >&2
  exit 1
fi

echo "Running live PgVectorStore test against ${PGVECTOR_TEST_DB_URL}" >&2
"$PYTHON_BIN" -m unittest tests.test_postgres_vector_store.TestPgVectorStore.test_live_round_trip
