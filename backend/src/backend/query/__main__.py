"""Local structured-plan runner; never interprets natural language or SQL."""

import argparse
from pathlib import Path

from pydantic import ValidationError

from backend.config import Settings
from backend.query.engine import QueryEngine
from backend.semantic.models import QueryPlan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute a validated QueryPlan JSON file read-only"
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/uzex.duckdb")
    )
    args = parser.parse_args(argv)
    engine = QueryEngine(Settings(database_path=args.database))
    try:
        plan = QueryPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        plan = None
    response = engine.execute(plan)
    print(response.model_dump_json(indent=2))
    return 0 if response.result.outcome.status in {"answered", "no_match"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
