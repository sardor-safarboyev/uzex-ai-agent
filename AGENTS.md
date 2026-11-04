# Project rules

- Keep changes scoped to the requested milestone and preserve existing work.
- Use Python 3.11+ and uv exclusively for Python dependencies; update backend/uv.lock.
- Keep the FastAPI backend modular under backend/src/backend/.
- Run `cd backend && uv run pytest` and `uv run ruff check .` after backend changes.
- Validate Docker changes with `docker compose build` and a health endpoint check.
- Keep secrets, environment files, databases, and source datasets out of Git and images.
- Do not invent transactions or the final dataset schema.
- Future analytics must use DuckDB in read-only mode against the fixed supplied dataset.
- Groq, frontend, query engine, and Azure work require a later milestone.
- Do not change branches or remotes, commit, or push unless explicitly requested.
