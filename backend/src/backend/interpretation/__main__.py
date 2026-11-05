"""Development CLI: emits plans, never model-generated answers or numbers."""

import argparse
import asyncio

from backend.config import Settings
from backend.interpretation import Interpreter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Interpret a question; no DB execution"
    )
    parser.add_argument("question")
    args = parser.parse_args()
    result = asyncio.run(Interpreter(Settings()).interpret(args.question))
    print(result.model_dump_json(indent=2))
    return 0 if result.outcome == "plan" else 1


if __name__ == "__main__":
    raise SystemExit(main())
