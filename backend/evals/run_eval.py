"""End-to-end evaluation of the agent against independently computed answers.

Ground truth for each question is computed by a hand-written SQL over the
*physical* tables (main.*), not the agent's semantic views, so a mistake in
the semantic layer would also be caught. The agent's natural-language answer
must contain the expected values (numbers within display rounding / given
relative tolerance, names case-insensitively).

    cd backend && GROQ_API_KEY=... UZEX_DATABASE_PATH=... \
        uv run python evals/run_eval.py [--only id1,id2]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import duckdb

from backend.agent.llm import LLMPool
from backend.agent.service import Agent
from backend.agent.sql import SQLRunner
from backend.agent.verify import _NUMBER, _parse

HERE = Path(__file__).parent
MONTHS = {
    1: ["январ", "yanvar", "январь"],
    2: ["феврал", "fevral"],
    3: ["март", "mart"],
    4: ["апрел", "aprel"],
    5: ["мая", "май", "may"],
    6: ["июн", "iyun"],
    7: ["июл", "iyul"],
    8: ["август", "avgust"],
    9: ["сентябр", "sentabr", "sentyabr"],
    10: ["октябр", "oktabr", "oktyabr"],
    11: ["ноябр", "noyabr"],
    12: ["декабр", "dekabr"],
}
NO_DATA = [
    "нет данных",
    "нет сделок",
    "не найден",
    "отсутств",
    "не было",
    "mavjud emas",
    "topilmadi",
    "ma'lumot yo'q",
    "ma’lumot yo‘q",
    "ma‘lumot",
    "bo'lmagan",
    "bo‘lmagan",
    "qamrab olmaydi",
    "yo'q",
    "yo‘q",
    "0 ta",
    "**0**",
    "2022",
]


def norm(text: str) -> str:
    return re.sub(r"[‘’ʻ'`\"«»]", "", text).casefold()


def numbers_in(text: str) -> list[tuple[float, int]]:
    found = []
    for match in _NUMBER.finditer(text):
        parsed = _parse(match.group(1))
        if parsed:
            found.append(parsed)
    return found


def has_number(answer: str, expected: float, tolerance: float | None) -> bool:
    for value, decimals in numbers_in(answer):
        if tolerance:
            if expected == 0 and value == 0:
                return True
            if expected and abs(value - expected) / abs(expected) <= tolerance:
                return True
        elif abs(value - expected) <= 0.5 * 10**-decimals + 1e-9:
            return True
    return False


def grade(item: dict, truth: list, response: dict) -> tuple[bool, str]:
    answer = response.get("answer") or ""
    kind = item["expect"]
    tolerance = item.get("tolerance")
    checks = []
    if kind in ("numbers", "text_and_numbers"):
        for value in truth:
            if isinstance(value, (int, float)) or re.fullmatch(
                r"-?\d+(\.\d+)?", str(value)
            ):
                checks.append(
                    (f"number {value}", has_number(answer, float(value), tolerance))
                )
    if kind in ("text", "text_and_numbers"):
        text = str(truth[0])
        checks.append((f"text {text}", norm(text) in norm(answer)))
    if kind == "month":
        words = MONTHS[int(truth[0])]
        checks.append((f"month {truth[0]}", any(w in answer.casefold() for w in words)))
    if kind == "nodata":
        checks.append(
            ("no-data statement", any(w in answer.casefold() for w in NO_DATA))
        )
    failed = [name for name, ok in checks if not ok]
    return (not failed and bool(checks)), ", ".join(failed)


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="  %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--pause", type=float, default=2.0)
    args = parser.parse_args()
    database = Path(os.environ["UZEX_DATABASE_PATH"])
    items = json.loads((HERE / "questions.json").read_text())
    if args.only:
        wanted = set(args.only.split(","))
        items = [i for i in items if i["id"] in wanted]
    truth_db = duckdb.connect(str(database), read_only=True)
    truths = {i["id"]: list(truth_db.execute(i["truth"]).fetchone()) for i in items}
    truth_db.close()
    agent = Agent(
        SQLRunner(database),
        LLMPool(
            os.getenv("GROQ_API_KEY"),
            os.getenv("OPENROUTER_API_KEY"),
            os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free"),
        ),
    )
    rows, passed = [], 0
    for item in items:
        truth = truths[item["id"]]
        started = time.monotonic()
        response = await agent.ask(item["q"])
        seconds = round(time.monotonic() - started, 2)
        ok, why = grade(item, truth, response)
        passed += ok
        models = sorted(
            {t.get("model") for t in response.get("trace", []) if t.get("model")}
        )
        rows.append(
            {
                "id": item["id"],
                "question": item["q"],
                "truth": [str(t) for t in truth],
                "pass": ok,
                "why": why,
                "seconds": seconds,
                "status": response.get("status"),
                "verified": (response.get("verification") or {}).get("ok"),
                "models": models,
                "answer": response.get("answer"),
                "sql": [q.get("sql") for q in response.get("queries", [])],
            }
        )
        mark = "PASS" if ok else "FAIL"
        print(f"{mark} {item['id']:<26} {seconds:>5}s {why}", flush=True)
        if not ok:
            print("   answer:", (response.get("answer") or "")[:400].replace("\n", " | "))
            print("   sql:", " ;; ".join(q.get("sql", "") for q in response.get("queries", []))[:400].replace("\n", " "))
        await asyncio.sleep(args.pause)
    total = len(items)
    print(f"\n{passed}/{total} passed")
    out = HERE / "results.json"
    out.write_text(
        json.dumps(
            {"passed": passed, "total": total, "rows": rows},
            ensure_ascii=False,
            indent=1,
        )
    )
    lines = [
        "# Evaluation results",
        "",
        f"**{passed}/{total} passed.** Median latency "
        f"{sorted(r['seconds'] for r in rows)[len(rows) // 2]} s.",
        "",
        "| id | question | expected | pass | s | numbers verified |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['question']} | {', '.join(r['truth'])} | "
            f"{'✅' if r['pass'] else '❌ ' + r['why']} | {r['seconds']} | "
            f"{'✓' if r['verified'] else '—'} |"
        )
    (HERE / "results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
