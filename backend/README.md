# UZEX backend

FastAPI application package with optional read-only DuckDB inspection. From this directory:

```sh
uv sync --locked
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Checks: `uv run pytest` and `uv run ruff check .`.
See the root README for configuration and Docker commands.
