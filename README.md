# UZEX AI Agent

A bilingual Uzbek/Russian AI agent for a fixed synthetic dataset of 500,000
exchange transactions. Milestone 1 implements the FastAPI foundation only.
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
DuckDB analytics, Groq integration, React/Vite, and Azure deployment are deferred.
