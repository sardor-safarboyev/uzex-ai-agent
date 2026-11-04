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
