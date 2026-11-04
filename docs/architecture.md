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
