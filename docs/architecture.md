# Architecture

Milestone 1 provides a stateless FastAPI backend with one public endpoint:
`GET /health` returns HTTP 200 and `{"status":"ok"}`. It confirms process health
and does not access external services or data.

The application factory and ASGI entry point live in `backend/src/backend/main.py`.
Routes live in `api/`; centralized pydantic-settings configuration lives in
`config.py`. Settings are read from environment variables prefixed with `UZEX_`
and cached per process. Restart the process after configuration changes.

Python dependencies are managed by uv and recorded in `backend/uv.lock`.
pytest exercises the HTTP endpoint; Ruff checks Python source and tests.
Docker runs the locked production dependencies as a non-root user. Compose binds
the API to `127.0.0.1:8000` and checks its health without third-party tools.

Later milestones will add Uzbek/Russian question interpretation via Groq,
read-only DuckDB analytics over the supplied fixed 500,000-transaction synthetic
dataset, a React/Vite frontend, and Azure deployment. None is implemented or
required for startup in Milestone 1.

Milestone 2 adds `backend.semantic`: a versioned Pydantic query-plan contract and
an immutable semantic metric registry. Plans distinguish aggregate requests from
clarification and unsupported outcomes. Logical identifiers remain independent
of physical columns. Cross-field validation enforces currency/unit compatibility.
There is no execution path; successful validation does not establish dataset
mapping readiness. See [semantic contract](semantic-contract.md) and
[query plan](query-plan.md). Groq interpretation and deterministic compilation
remain future work; Groq must never generate executable SQL.

Milestone 2.1 refines the same semantic package with version 1.1 lookup and period
comparison requests, numeric predicates, normalized product identity, mass-unit
policies, explicit broker roles and delivery completion, and a future typed
execution-result envelope. No executor, SQL compiler, or data mappings are added.
See [execution result](execution-result.md) for outcome and coverage semantics.

## Milestone 3A database boundary

`backend.database.adapter.DuckDBAdapter` provides one context-managed connection
per operation. It checks for an existing regular file, opens it with read_only=True,
and always closes the connection/releases its process-local semaphore slot.
Configuration is centralized in Settings; no database is opened during app
construction or startup. There is no implicit create, migration, import, writable
fallback, connection pool, or global DuckDB default connection.

The adapter applies bounded connections, engine memory/threads, a native query
execution timeout, disabled disk spilling, disabled external access and automatic
extensions, and locked engine settings. Read-only mode protects the persistent
database; trusted Python callers still hold a connection and can create temporary
in-memory objects. This boundary is not an arbitrary-SQL sandbox. Future semantic
compilation must remain deterministic and separate from this access layer.

`backend.database.service.DatabaseService` supplies typed readiness and bounded
catalog inspection. The latter uses one fixed, parameterized information_schema
query and no user-supplied SQL, identifiers, table scans or view evaluation. Table
identity includes catalog and schema. Errors are translated into stable public
codes. Unsupported/corrupt/locked files fail closed, with no automatic recovery.

`GET /health` remains independent liveness. `GET /ready` reports database
availability (200 ready, 503 not_ready with reason), not dataset validity.
`GET /dev/database` is development metadata only, disabled by default (404), and
returns 503 on database/inspection failure. No raw transaction endpoint is added.

Base Compose starts without a database. The optional compose.database.yaml overlay
mounts an existing directory read-only at /data without auto-creating host paths.
The non-root runtime user requires read/traverse permissions. The Docker liveness
probe keeps running even while database readiness fails. Only temporary test
fixtures contain invented data; no production schema, query compiler, or Groq
integration is introduced. The semantic modules from Milestones 2–2.1 coexist
with this layer but are not a runtime dependency of database access.
