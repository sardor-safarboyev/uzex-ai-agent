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

## Offline profiling boundary (Milestone 3B.1)

`backend.profiling` is a standalone CLI, with strict CSV/provenance checks,
observed-header profiling recipes, transient DuckDB diagnostics, and JSON/Markdown
report rendering. It is not imported by the FastAPI app, uses no runtime database
path, and does not call the read-only runtime adapter: it intentionally builds
in-memory VARCHAR tables to analyze local source files. No persistent database,
production import, semantic compilation, normalization service or LLM integration
is added. The existing runtime database and semantic models are preserved.

Reports record hashes before/after profiling, versions, deterministic counts,
parsing failures and join/cardinality/rate-coverage evidence. Structurally invalid
sources fail closed for downstream diagnostics. Quality warnings remain visible
without changing source rows. Candidate relationships and unsafe joins are
explicit diagnostics rather than physical schema commitments. The existing
.gitignore excludes raw sources, processed data, and local reports.

## Offline ingestion boundary (Milestone 3B.2)

`backend.ingestion` is separate from both FastAPI and the profiling command. It
pins the profile manifest, verifies immutable source hashes, creates a temporary
transactional DuckDB snapshot, retains exact strings in raw tables, and materializes
explicit typed mappings in main tables. Source provenance, build identity and
validation evidence live in audit tables. It reopens the closed snapshot read-only
for independent reconciliation before atomic publication under data/processed/.

The runtime adapter and API remain read-only and never import/invoke ingestion.
The independent offline validator also opens the database read-only, but permits
CSV reads solely for source reconciliation. No SQL compiler or LLM interpretation
is introduced. Unverified FX, unit/identity and duration semantics remain explicit
rather than being guessed. The [physical schema](physical-schema.md) documents
all observed headers, typed fields, derived values, provenance and semantic gaps.

## Deterministic query boundary (Milestone 3C)

`backend.query` revalidates QueryPlan objects, compiles closed allowlisted
SELECT/WITH templates with bound values, verifies the ingestion boundary, and
executes through the existing DuckDBAdapter. Exact primary-key joins preserve
fact grain. Scope/metric/predicate coverage checks precede bounded result queries.
Typed results keep insufficient evidence distinct from no_match, and carry scope,
source evidence, provenance and limit warnings through an additive wrapper.

FX and unverified entity normalization remain unsupported. Exact unit multipliers
and rational price comparisons avoid floating-point conversion/ranking errors.
The package exposes a Python service and local plan-file CLI, with no arbitrary
SQL input or new HTTP query route. Runtime API/database access remains read-only;
no ingestion, LLM calls or natural-language generation is introduced. See
[execution support](query-execution.md) for precise semantics and limits.
