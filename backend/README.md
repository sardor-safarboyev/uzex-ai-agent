# UZEX backend

FastAPI application package for Milestone 1. From this directory:

```sh
uv sync --locked
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Checks: `uv run pytest` and `uv run ruff check .`.
See the root README for configuration and Docker commands.
