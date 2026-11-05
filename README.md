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

## Offline source CSV profiling (Milestone 3B.1)

From the repository root, with the nine supplied files already in `data/raw/`:

```sh
uv run --project backend python -m backend.profiling
```

The command writes `data/reports/profile.json` and `data/reports/profile.md`.
Explicit paths and a DuckDB memory budget can be supplied:

```sh
uv run --project backend python -m backend.profiling \
  --raw-dir data/raw --report-dir data/reports --memory-mb 1024
```

It strictly validates decoding, CSV quoting and widths, retains every loaded
field as VARCHAR (including leading zeros), and uses a transient in-memory
DuckDB workspace. The runtime database adapter, database path and API are not
used. Raw files are never rewritten, records are not silently skipped, names
are not merged, and no import database or SQL compiler is created. A malformed
source fails explicitly; it is not partially loaded for downstream joins.

Reports contain source SHA-256 hashes, tool/code versions, exact counts, empty
and null-marker diagnostics, diagnostic date/decimal parsing, duplicate keys,
source categories/name scripts, join multiplicities, and transaction-date USD
rate coverage. Samples are bounded; aggregate counts use all validated records.
Exit 0 means profiling completed, including possible quality warnings; exit 1
means a source or analysis failure. CLI configuration errors exit 2. The reports
must be outside the source directory. Repeating with the same files, code,
Python/DuckDB versions and memory setting produces identical report contents.

Both raw data and reports are locally Git-ignored under the existing project
rules. Reports contain source names and identifier examples; do not publish them
as public API data. See [profiling method and findings](docs/data-contract.md#milestone-3b1-reproducible-source-profiling).

## Offline validated database build (Milestone 3B.2)

From the repository root, after profiling the nine supplied CSVs:

```sh
uv run --project backend python -m backend.ingestion build
uv run --project backend python -m backend.ingestion validate
```

The builder verifies the hashes in `data/reports/profile.json` and requires exactly
500,000 deals. It creates `data/processed/uzex.duckdb` through a temporary snapshot,
validates all source fields, typed values, keys, joins and rate coverage, reopens
read-only for another check, and replaces the destination atomically only on
success. Failure preserves an existing snapshot. Stop database readers before
rebuilding. Neither command is triggered by application startup or HTTP requests.

Build reports: `data/reports/build-validation.json` and `build-validation.md`.
Independent validation writes `validation.json` and `validation.md` and never
modifies the database. Commands exit 0 for passed validation (unresolved business
semantics remain reported), or 1 for failures. Resource/path options:

```sh
uv run --project backend python -m backend.ingestion build \
  --raw-dir data/raw --manifest data/reports/profile.json \
  --database data/processed/uzex.duckdb --report-dir data/reports --memory-mb 1024
```

Source strings and record references are retained in `raw.*`; typed tables are in
`main.*`; manifests and check evidence are in `audit.*`. See the complete
[physical schema and semantic mappings](docs/physical-schema.md).

USD conversion remains deferred pending rounding and timezone rules; matched
transaction-date rates are retained as evidence. Original amounts/currencies,
lot quantity, lot size, per-deal physical volume, source unit labels, official
status and NULL workflow values remain separate. No product/company fuzzy merge
or broker-INN-to-participant join is introduced.

To use the built snapshot with the existing read-only API, start a new process:

```sh
export UZEX_DATABASE_PATH="$PWD/data/processed/uzex.duckdb"
uv run --project backend uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

For the existing Compose database overlay, set UZEX_DATABASE_DIRECTORY to the
absolute `data/processed/` directory and UZEX_DATABASE_PATH to `/data/uzex.duckdb`.
The mount remains read-only. Database/report artifacts remain Git-ignored.

`cd backend && uv run pytest` runs synthetic ingestion failure tests and the
full-dataset build/reconciliation test when all nine local CSVs and the profile
manifest exist; that test skips on CI installations without the ignored data.

## Deterministic read-only queries (Milestone 3C)

Run a structured plan against the validated snapshot from the repository root:

```sh
uv run --project backend python -m backend.query \
  --plan docs/examples/deal-count.json --database data/processed/uzex.duckdb
```

Python callers use `QueryEngine(Settings(database_path=...)).execute(query_plan)`.
Only revalidated QueryPlan objects enter the compiler/executor; arbitrary SQL is
never accepted. The typed wrapper carries scope, source evidence, coverage,
provenance, limits and warnings. Runtime database writes and ingestion remain
unavailable through query execution. No new HTTP endpoint is introduced.

Source-currency aggregates, approved unit metrics, exact kg/tonne conversion,
weighted prices, bounded grouping/ranking, exact lookup and period comparisons
are supported. Unverified USD conversion and normalized product/alias mappings
return typed unsupported results. Unknown metric/predicate values yield
insufficient_data rather than partial numerical answers. See
[supported patterns and limitations](docs/query-execution.md).

`UZEX_QUERY_MAX_RESULTS` optionally caps returned rows at 1–1000; existing database
memory, query timeout, thread and connection settings apply. Real reconciliation
results are written locally to `data/reports/query-integration.json` and `.md` by
`cd backend && uv run pytest tests/test_query_integration.py -q`.


## Milestone 4A minimal development interpreter

Set `GROQ_API_KEY` in the process environment (never pass it in a question).
From the repository root:

```sh
uv run --project backend python -m backend.interpretation "Bitimlar soni qancha?"
```

This development CLI prints a validated logical plan, never a numerical answer.
It does not load `.env` automatically, access the database, or expose an HTTP endpoint.
Pass the plan to the existing QueryEngine for deterministic answers; never display
model prose as an answer. Uzbek Latin, Uzbek Cyrillic and Russian are prompted;
real model language quality has not been benchmarked. Exact lookup, counts,
source-currency totals, grouping, rankings, explicit date ranges and comparisons
use the unchanged compiler contract. Ambiguous questions request clarification.
Product aliases, normalized IDs and USD conversion remain unsupported.

Settings: `GROQ_API_KEY` (secret), `UZEX_GROQ_MODEL` (default
`openai/gpt-oss-20b`), `UZEX_GROQ_TIMEOUT_SECONDS` (20),
`UZEX_GROQ_MAX_RETRIES` (2, maximum 3), `UZEX_GROQ_STRUCTURED_OUTPUT` (false).
Default JSON object mode is validated locally with Pydantic. Set structured output
true only for a model supporting JSON schema (e.g. `openai/gpt-oss-20b`);
best-effort schema mode preserves the existing schema's optional fields.
See [Groq output modes](https://console.groq.com/docs/structured-outputs).
No automatic fallback changes the selected model or relaxes validation.
Only rate limits, server and network failures are retried, with bounded backoff;
provider bodies, exceptions and credentials are never returned. Invalid/truncated
JSON produces a safe error code. Clarification/unsupported prose uses fixed text.
Prompt rules reduce injection risk; schema validation and compiler allowlists
provide the execution boundary. Semantic interpretation still depends on model
accuracy; a valid plan is not proof that it matches user intent.


## End-to-end web MVP

Prerequisites: the existing validated `data/processed/uzex.duckdb`, Docker Compose,
and `.env` containing `GROQ_API_KEY`. No ingestion runs on startup.

### Start the production containers locally

```sh
cd /home/sardor/projects/uzex-ai-agent
docker compose -f compose.yaml -f compose.web.yaml up -d --build
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8080/ready
```

Open **http://127.0.0.1:8080**. The browser uses the nginx same-origin `/api` proxy.
Only the backend receives the key; neither images nor frontend builds include `.env`.
The database is an existing file bind-mounted read-only, never copied into an image.
The base Compose configuration is preserved; add `compose.web.yaml` for this MVP.

```sh
curl --fail-with-body http://127.0.0.1:8080/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Bitimlar soni qancha?","language":"uz"}'
curl --fail http://127.0.0.1:8080/api/examples
```

`POST /api/ask` accepts only question (1–4000 characters) and optional language
(uz/ru). It calls Groq for a locally validated QueryPlan, then the unchanged
compiler/read-only QueryEngine. Answer text is a deterministic template over
execution results; no model-generated answer or numerical claim is displayed.
`execution` contains result columns (including currency/unit metadata), rows,
coverage, source hashes, scope, warnings, provenance and periods where available.
Decimals are JSON strings to preserve precision. Source text remains untranslated.
Clarification, no_match, unsupported and insufficient_data return typed nonanswers;
provider/database errors and busy limits return a safe typed response with HTTP 503.
Invalid request shapes return HTTP 422. Groq retries/timeouts, database statement
limits, shared connection limits and a bounded ask concurrency limit apply.
Compose caps returned rows at 100 by default (`UZEX_QUERY_MAX_RESULTS`, max 1000).
`UZEX_ASK_MAX_CONCURRENT` defaults to 4 for direct backend startup.

### Development without Docker

Terminal 1, from repository root (load `.env` into backend only):

```sh
UZEX_DATABASE_PATH="$PWD/data/processed/uzex.duckdb" \
  uv run --project backend --env-file .env uvicorn backend.main:app \
  --host 127.0.0.1 --port 8000
```

Terminal 2:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/api` to localhost:8000.
For a separate API origin set `VITE_API_BASE_URL` at frontend build time and set
`UZEX_CORS_ORIGINS='["https://your-frontend.example"]'` on the backend. Never put
secrets in `VITE_` variables. The UI toggle changes labels and examples; the
question itself determines successful interpretation language.

### Production deployment on a Docker host

Copy this checkout, the validated snapshot and a protected backend `.env` to the
host. Use the same command with an explicit public bind behind your HTTPS ingress:

```sh
UZEX_WEB_BIND=0.0.0.0 UZEX_WEB_PORT=8080 \
  docker compose -f compose.yaml -f compose.web.yaml up -d --build
```

Point your HTTPS ingress to port 8080; backend port 8000 remains loopback-only.
The production overlay disables metadata, Swagger, ReDoc and OpenAPI endpoints.
This is an unauthenticated MVP: use a controlled demo audience or ingress access
controls; no hosted domain, TLS certificate or cloud account is provisioned here.
USD conversion, fuzzy product aliases and unverified unit mappings remain unsupported.
Ambiguous date years/currencies/entity names request clarification, never defaults.

Checks:

```sh
cd backend
uv run pytest tests/test_ask.py tests/test_interpretation.py -q
uv run pytest
uv run ruff check .
cd ../frontend
npm ci && npm run build
cd ..
docker compose -f compose.yaml -f compose.web.yaml build
```

Automated Groq calls are mocked. The real-data API smoke verifies all advertised
example scopes and the 500,000 count, checking the snapshot fingerprint unchanged.


### Presentation regression checks

This demo uses synthetic transactions, not real or live UZEX trading data.
The UI language toggle formats answers, units, warnings and coverage labels in
Uzbek or Russian. Decimal strings are grouped without rounding or conversion to
floating point; original API values remain accessible under the technical details.
Detailed evidence is collapsed by default, while actual coverage counts and state
remain visible. Source product names and official status labels are not translated.

```sh
cd frontend
npm test
npm run build
```

Tests use Node's built-in runner and mocked API responses. When Google Chrome is
available, they also exercise language toggling, native evidence disclosure,
mobile overflow, request deduplication and safe nonanswer states in headless Chrome.
No live Groq calls are made by these regression tests.
