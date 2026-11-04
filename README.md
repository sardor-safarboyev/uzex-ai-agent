# UZEX AI Agent

A bilingual Uzbek/Russian AI agent for a fixed synthetic dataset of 500,000
exchange transactions. Milestone 3A adds read-only DuckDB access and catalog inspection.
No dataset, database, or Groq key is needed.

## Local development

Prerequisites: uv and Python 3.11+ (uv can download the pinned Python 3.11).
From the repository root:

```sh
cd backend
uv sync --locked
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```sh
curl --fail http://localhost:8000/health
```

Expected: HTTP 200 with `{"status":"ok"}`.

Run checks from the repository root:

```sh
cd backend
uv run pytest
uv run ruff check .
```

## Docker

Prerequisites: Docker Engine running and Docker Compose v2+.
From the repository root:

```sh
docker compose build
docker compose up -d
docker compose ps
curl --fail --retry 10 --retry-connrefused --retry-delay 1 http://localhost:8000/health
```

The API is exposed on localhost port 8000. Inspect logs or stop it with:

```sh
docker compose logs backend
docker compose down
```

## Configuration

`UZEX_APP_NAME` optionally sets the application title (default: `UZEX AI Agent`).
For a local process, export it in the shell before starting uvicorn:

```sh
export UZEX_APP_NAME="UZEX AI Agent"
```

Compose reads an optional root `.env` file; create it with `cp .env.example .env`
and edit its values if needed. Local Python reads environment variables directly
and does not automatically load `.env`. No configuration file is required.

See [architecture](docs/architecture.md) and [data contract](docs/data-contract.md).
Semantic query compilation, transaction analytics, Groq integration, React/Vite,
and Azure deployment are deferred.


## Database access and readiness

The application starts without a database. `/health` remains HTTP 200 with
`{"status":"ok"}`. `/ready` returns 503 with a sanitized reason when database
access is unavailable. Locally, an unset path produces
`{"status":"not_ready","reason":"not_configured"}`; in base Compose, the default
missing `/data/uzex.duckdb` produces reason `not_found`. An existing readable
DuckDB file gives HTTP 200 with `{"status":"ready","reason":null}`. Readiness
checks opening the database and `SELECT 1`; it does not verify UZEX schema,
expected tables, counts, records, or mappings. An empty valid database is ready.

Check readiness (503 is expected without a database):

```sh
curl --include http://localhost:8000/ready
```

To use an existing database locally, stop the prior server, then from the root:

```sh
export UZEX_DATABASE_PATH=/absolute/path/to/existing/database.duckdb
export UZEX_DATABASE_METADATA_ENABLED=true
cd backend
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Replace the path with a real supplied file; these commands do not create or
import one. Relative paths resolve from the process working directory. Keep the
file and its containing directories readable/traversable by the runtime user.
Only clean, compatible DuckDB snapshots should be served; close writers before
opening them here. Missing, invalid, locked, incompatible, or inaccessible files
produce readiness failures; the service never repairs or initializes a database.

`GET /dev/database` returns table/view names, catalog/schema identifiers, column
names, ordinal positions, SQL types, nullability, engine version and read-only
status. It omits rows, samples, defaults, comments, SQL definitions, and filesystem
paths. It returns 404 unless `UZEX_DATABASE_METADATA_ENABLED=true`; enable it only
in development because schema names themselves can be sensitive. No SQL or table
selection is accepted from HTTP clients.

```sh
curl --fail http://localhost:8000/dev/database
```

## Optional read-only Docker database mount

Base Compose has no database mount and needs no host data directory. To attach an
existing directory, use the optional overlay from the repository root:

```sh
export UZEX_DATABASE_DIRECTORY=/absolute/path/to/existing/database-directory
export UZEX_DATABASE_PATH=/data/uzex.duckdb
export UZEX_DATABASE_METADATA_ENABLED=true
docker compose -f compose.yaml -f compose.database.yaml config --quiet
docker compose -f compose.yaml -f compose.database.yaml up -d --build
curl --include http://localhost:8000/ready
curl --fail http://localhost:8000/dev/database
```

Set the container filename to the supplied file's name. The overlay mounts the
existing host directory at `/data` read-only and refuses to create a missing host
directory. The file is optional even within that directory: its absence reports
not_found without preventing application startup. Container UID/GID 10001 must
have read/traverse permissions. Databases and fixture files never enter the build
context or image. Stop this configuration with:

```sh
docker compose -f compose.yaml -f compose.database.yaml down
```

## Database resource settings

| Environment variable | Default | Accepted values / scope |
| --- | --- | --- |
| UZEX_DATABASE_PATH | unset locally; /data/uzex.duckdb in Compose | Existing file only; no in-memory special paths |
| UZEX_DATABASE_METADATA_ENABLED | false | Development metadata endpoint switch |
| UZEX_DATABASE_THREADS | 2 | 1–8 engine threads |
| UZEX_DATABASE_MEMORY_MB | 256 | 16–8192 MB engine memory budget |
| UZEX_DATABASE_MAX_CONNECTIONS | 2 | 1–8 active adapter connections per process; excess requests get busy |
| UZEX_DATABASE_QUERY_TIMEOUT_MS | 5000 | 1–60000 ms engine execution limit per query |
| UZEX_DATABASE_METADATA_MAX_COLUMNS | 2000 | 1–10000 catalog rows; overflow reports resource_limit |

Connections close after each operation, including errors. Engine settings are
locked before connections reach callers; external file/network access and
extension auto-install/load are disabled, and disk spilling is disabled. Memory
limits are DuckDB budgets, not hard process-RSS limits; connection gates are per
process, not deployment-wide. Query limits do not bound OS-level file-open time.
Compose's container healthcheck deliberately uses liveness, not database readiness.
The adapter is for trusted backend code, not untrusted SQL or Python sandboxing.

Tests build tiny temporary databases with explicitly invented test-only rows.
They verify write rejection, connection cleanup, resource settings/timeouts,
inspection, readiness, and error handling; they make no claims about UZEX data.
