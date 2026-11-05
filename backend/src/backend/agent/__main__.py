"""CLI: uv run python -m backend.agent "Сколько сделок в 2024 году?" """

import asyncio
import json
import os
import sys
from pathlib import Path

from backend.agent.llm import LLMPool
from backend.agent.service import Agent
from backend.agent.sql import SQLRunner


async def main(questions: list[str]) -> None:
    agent = Agent(
        SQLRunner(Path(os.environ["UZEX_DATABASE_PATH"])),
        LLMPool(
            os.getenv("GROQ_API_KEY"),
            os.getenv("OPENROUTER_API_KEY"),
            os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free"),
        ),
    )
    for question in questions:
        result = await agent.ask(question)
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
