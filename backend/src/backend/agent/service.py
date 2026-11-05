"""Agent orchestration: plan SQL -> execute (with self-repair) -> grounded answer -> verify.

`run()` is an async generator of progress events so the UI can stream stages;
the final event has type "final" and carries the full, cacheable response.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

from backend.agent.llm import LLMError, LLMPool
from backend.agent.prompts import answer_system, planner_system
from backend.agent.sql import QueryResult, SQLRejected, SQLRunner
from backend.agent.verify import verify_answer

log = logging.getLogger("uzex.agent")

PLANNER_MODELS = [
    "groq:openai/gpt-oss-120b",
    "groq:qwen/qwen3.8-27b",
    "groq:openai/gpt-oss-20b",
]
ANSWER_MODELS = [
    "groq:qwen/qwen3.8-27b",
    "groq:openai/gpt-oss-120b",
    "groq:openai/gpt-oss-20b",
]
MAX_REPAIRS = 2
ROWS_FOR_LLM = 30

_UZ_CYRL = re.compile(r"[ўқғҳЎҚҒҲ]")
_UZ_LATIN = re.compile(
    r"(o['‘’ʻ`]|g['‘’ʻ`]|\b(qancha|nechta|qaysi|necha|yil|yilda|bitim|savdo|hajm|eng|"
    r"bo'yicha|boʻyicha|ko'p|jami|summa|mahsulot|sotuvchi|xaridor|viloyat|oy|uchun|"
    r"nima|qanday|qayerda|ulushi|o'rtacha|narx|necha|birja|tonna|bilan|va|bo'lgan)\b)",
    re.IGNORECASE,
)
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_UZ_CYRL_WORDS = re.compile(
    r"\b(қанча|нечта|йил|битим|энг|бўйича|жами|қайси|савдо)\b", re.I
)


def detect_language(text: str) -> str:
    if _UZ_CYRL.search(text) or _UZ_CYRL_WORDS.search(text):
        return "uz_cyrl"
    if _CYRILLIC.search(text):
        return "ru"
    if _UZ_LATIN.search(text):
        return "uz"
    return "ru" if re.search(r"[a-z]", text, re.I) is None else "uz"


class Agent:
    def __init__(self, runner: SQLRunner, llm: LLMPool, cache_size: int = 500):
        self.runner = runner
        self.llm = llm
        self._planner_system = planner_system()
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._cache_size = cache_size
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="duckdb")

    # ------------------------------------------------------------------ helpers
    async def _sql(self, sql: str) -> QueryResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, self.runner.run, sql)

    @staticmethod
    def _cache_key(question: str, language: str, history: list[dict]) -> str:
        base = re.sub(r"\s+", " ", question.strip().lower())
        hist = "|".join(h.get("question", "") for h in history[-2:])
        return f"{language}::{hist}::{base}"

    def _remember(self, key: str, value: dict) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    @staticmethod
    def _compact(result: QueryResult) -> dict:
        return {
            "columns": result.columns,
            "rows": result.rows[:ROWS_FOR_LLM],
            "row_count": result.row_count,
            "truncated": result.truncated or result.row_count > ROWS_FOR_LLM,
        }

    # --------------------------------------------------------------------- main
    async def run(
        self, question: str, language: str = "auto", history: list[dict] | None = None
    ) -> AsyncIterator[dict]:
        started = time.monotonic()
        history = history or []
        detected = detect_language(question)
        lang = detected if language in ("auto", "", None) else language
        key = self._cache_key(question, lang, history)
        if key in self._cache:
            cached = dict(self._cache[key])
            cached["cached"] = True
            cached["timings"] = {
                **cached.get("timings", {}),
                "total_s": round(time.monotonic() - started, 2),
            }
            yield {"type": "final", "data": cached}
            return

        trace: list[dict] = []
        timings: dict[str, float] = {}
        yield {"type": "stage", "stage": "planning"}

        # ---- 1. plan
        user_msg = self._planner_user_message(question, lang, history)
        messages = [
            {"role": "system", "content": self._planner_system},
            {"role": "user", "content": user_msg},
        ]
        t0 = time.monotonic()
        try:
            plan, completion = await self._plan(messages)
        except LLMError as error:
            yield {
                "type": "final",
                "data": self._error(lang, "llm_unavailable", str(error), started),
            }
            return
        timings["plan_s"] = round(time.monotonic() - t0, 2)
        trace.append(
            {
                "step": "plan",
                "model": completion.model,
                "seconds": completion.seconds,
                "tokens": completion.prompt_tokens + completion.completion_tokens,
            }
        )
        lang = self._answer_language(lang, language, plan)

        if not plan.get("queries"):
            message = plan.get("clarify") or ""
            data = self._base(lang, question, plan, started, trace, timings)
            data.update(
                status="clarify", answer=message or self._text(lang, "no_query")
            )
            self._remember(key, data)
            yield {"type": "final", "data": data}
            return

        yield {
            "type": "plan",
            "understanding": plan.get("understanding", ""),
            "queries": [q.get("sql", "") for q in plan["queries"]],
        }

        # ---- 2. execute, repairing failed/empty queries
        yield {"type": "stage", "stage": "querying"}
        t0 = time.monotonic()
        results, plan = await self._execute_with_repair(messages, plan, trace)
        timings["sql_s"] = round(time.monotonic() - t0, 2)
        if results is None:
            data = self._base(lang, question, plan, started, trace, timings)
            data.update(
                status="error",
                error="sql_failed",
                answer=self._text(lang, "sql_failed"),
            )
            yield {"type": "final", "data": data}
            return
        yield {"type": "results", "results": results}

        # ---- 3. answer + verify
        yield {"type": "stage", "stage": "answering"}
        t0 = time.monotonic()
        answer, verification = await self._answer(question, lang, plan, results, trace)
        timings["answer_s"] = round(time.monotonic() - t0, 2)

        data = self._base(lang, question, plan, started, trace, timings)
        data.update(
            status="answered", answer=answer, results=results, verification=verification
        )
        self._remember(key, data)
        yield {"type": "final", "data": data}

    async def ask(
        self, question: str, language: str = "auto", history: list[dict] | None = None
    ) -> dict:
        final: dict = {}
        async for event in self.run(question, language, history):
            if event["type"] == "final":
                final = event["data"]
        return final

    # ---------------------------------------------------------------- planning
    def _planner_user_message(
        self, question: str, lang: str, history: list[dict]
    ) -> str:
        parts = [f"Today: {dt.date.today().isoformat()}."]
        for turn in history[-2:]:
            q = (turn.get("question") or "")[:300]
            sql = " ; ".join(turn.get("sql") or [])[:600]
            if q:
                parts.append(f"Previous question: {q}\nIts SQL: {sql}")
        if history:
            parts.append(
                "The new question may be a follow-up: reuse filters from the previous one if it is incomplete."
            )
        parts.append(f"Question ({lang}): {question}")
        return "\n".join(parts)

    async def _plan(self, messages: list[dict]):
        completion = await self.llm.complete(
            messages,
            preference=PLANNER_MODELS,
            json_mode=True,
            max_tokens=2500,
            reasoning_effort="medium",
            need_tokens=3500,
            max_wait=60,
        )
        plan = json.loads(completion.content)
        if not isinstance(plan, dict):
            raise LLMError("plan_not_object")
        queries = plan.get("queries") or []
        if not isinstance(queries, list):
            queries = []
        clean = []
        for q in queries[:3]:
            if (
                isinstance(q, dict)
                and isinstance(q.get("sql"), str)
                and q["sql"].strip()
            ):
                clean.append(
                    {"purpose": str(q.get("purpose") or ""), "sql": q["sql"].strip()}
                )
            elif isinstance(q, str) and q.strip():
                clean.append({"purpose": "", "sql": q.strip()})
        plan["queries"] = clean
        return plan, completion

    async def _execute_with_repair(self, messages, plan, trace):
        convo = list(messages)
        for attempt in range(MAX_REPAIRS + 1):
            results, problems = [], []
            for index, query in enumerate(plan["queries"]):
                try:
                    result = await self._sql(query["sql"])
                    entry = {
                        "purpose": query["purpose"],
                        **self._compact(result),
                        "sql": result.sql,
                        "ms": result.ms,
                    }
                    results.append(entry)
                    if result.row_count == 0 or _all_empty(result):
                        problems.append(
                            f"Query {index + 1} returned no rows/only NULLs."
                        )
                except SQLRejected as error:
                    problems.append(f"Query {index + 1} rejected: {error}")
                except Exception as error:  # duckdb errors
                    message = str(error).split("\n")[0][:400]
                    problems.append(f"Query {index + 1} failed: {message}")
            if problems:
                log.warning("sql attempt %s: %s", attempt + 1, problems)
            trace.append(
                {
                    "step": "sql",
                    "attempt": attempt + 1,
                    "problems": problems,
                    "ms": sum(r.get("ms", 0) for r in results),
                }
            )
            hard_failure = len(results) < len(plan["queries"])
            if not problems:
                return results, plan
            if attempt == MAX_REPAIRS:
                return (results if not hard_failure and results else None), plan
            # Empty results are legitimate (e.g. a year with no data) — ask once to double-check filters.
            if not hard_failure and attempt >= 1:
                return results, plan
            convo += [
                {"role": "assistant", "content": json.dumps(plan, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": "\n".join(problems)
                    + (
                        "\nFix the SQL: check column names and DuckDB syntax; re-check EVERY WHERE condition — "
                        "is each filter really requested by the user, and does the value exist exactly (see value lists)? "
                        "Text values are Russian Cyrillic (e.g. '%аи 92%', not '%ai 92%'); regions are Uzbek Latin. "
                        "Remove filters the user did not ask for. If an empty result is genuinely correct "
                        "(e.g. period outside the data), return the same queries unchanged. "
                        "Return the full JSON again."
                    ),
                },
            ]
            try:
                plan, completion = await self._plan(convo)
            except LLMError:
                return (results if not hard_failure and results else None), plan
            trace.append(
                {
                    "step": "repair",
                    "model": completion.model,
                    "seconds": completion.seconds,
                    "tokens": completion.prompt_tokens + completion.completion_tokens,
                }
            )
            if not plan.get("queries"):
                return (results if not hard_failure and results else None), plan
        return None, plan

    # ----------------------------------------------------------------- answer
    async def _answer(self, question, lang, plan, results, trace):
        payload = {
            "question": question,
            "computed": plan.get("understanding", ""),
            "results": [
                {
                    "purpose": r["purpose"],
                    "columns": r["columns"],
                    "rows": r["rows"],
                    "row_count": r["row_count"],
                }
                for r in results
            ],
        }
        messages = [
            {"role": "system", "content": answer_system(lang)},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, default=str),
            },
        ]
        answer = ""
        verification = None
        for attempt in range(2):
            try:
                completion = await self.llm.complete(
                    messages,
                    preference=ANSWER_MODELS,
                    json_mode=False,
                    max_tokens=900,
                    reasoning_effort="low",
                    need_tokens=1500,
                    max_wait=40,
                )
            except LLMError:
                break
            log.info("answer by %s in %ss", completion.model, completion.seconds)
            trace.append(
                {
                    "step": "answer",
                    "attempt": attempt + 1,
                    "model": completion.model,
                    "seconds": completion.seconds,
                    "tokens": completion.prompt_tokens + completion.completion_tokens,
                }
            )
            answer = _clean_answer(completion.content)
            verification = verify_answer(answer, results, question)
            if verification.ok:
                break
            messages += [
                {"role": "assistant", "content": answer},
                {
                    "role": "user",
                    "content": (
                        "These numbers are not in the results: "
                        + ", ".join(verification.unverified)
                        + ". Rewrite the answer using only numbers exactly as they appear in the results."
                    ),
                },
            ]
        if not answer:
            answer = fallback_answer(lang, plan, results)
            verification = verify_answer(answer, results, question)
        return answer, verification.as_dict() if verification else None

    # ------------------------------------------------------------- formatting
    def _answer_language(self, lang, requested, plan):
        if requested not in ("auto", "", None):
            return requested
        proposed = plan.get("language")
        if lang == "uz_cyrl":
            return lang
        return proposed if proposed in ("ru", "uz") else lang

    def _base(self, lang, question, plan, started, trace, timings):
        timings["total_s"] = round(time.monotonic() - started, 2)
        return {
            "question": question,
            "language": lang,
            "understanding": plan.get("understanding", ""),
            "queries": plan.get("queries", []),
            "trace": trace,
            "timings": timings,
            "cached": False,
        }

    def _error(self, lang, code, detail, started):
        log.warning("agent error %s: %s", code, detail)
        return {
            "language": lang,
            "status": "error",
            "error": code,
            "answer": self._text(lang, code),
            "queries": [],
            "results": [],
            "trace": [],
            "timings": {"total_s": round(time.monotonic() - started, 2)},
            "cached": False,
        }

    @staticmethod
    def _text(lang, code):
        texts = {
            "llm_unavailable": {
                "ru": "Сервис ИИ сейчас перегружен (лимит запросов). Повторите вопрос через несколько секунд.",
                "uz": "Sun'iy intellekt xizmati hozir band (so'rovlar limiti). Bir necha soniyadan so'ng qayta urinib ko'ring.",
                "uz_cyrl": "Сунъий интеллект хизмати ҳозир банд. Бир неча сониядан сўнг қайта уриниб кўринг.",
            },
            "sql_failed": {
                "ru": "Не удалось построить корректный запрос к данным. Переформулируйте вопрос, пожалуйста.",
                "uz": "Ma'lumotlarga to'g'ri so'rov tuzib bo'lmadi. Savolni boshqacha ifodalab ko'ring.",
                "uz_cyrl": "Маълумотларга тўғри сўров тузиб бўлмади. Саволни бошқача ифодалаб кўринг.",
            },
            "no_query": {
                "ru": "Этот вопрос не относится к данным биржевых сделок.",
                "uz": "Bu savol birja bitimlari ma'lumotlariga tegishli emas.",
                "uz_cyrl": "Бу савол биржа битимлари маълумотларига тегишли эмас.",
            },
        }
        return texts.get(code, texts["sql_failed"]).get(
            lang, texts.get(code, texts["sql_failed"])["ru"]
        )


def _all_empty(result: QueryResult) -> bool:
    if not result.rows:
        return True
    return all(v is None or v == 0 for row in result.rows for v in row)


def _clean_answer(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    return text


def _fmt(value) -> str:
    if isinstance(value, (int, float)) or (
        isinstance(value, str) and re.fullmatch(r"-?\d+(\.\d+)?", value)
    ):
        number = float(value)
        decimals = 2 if not float(number).is_integer() else 0
        text = f"{number:,.{decimals}f}".replace(",", " ").replace(".", ",")
        return text
    return str(value)


def fallback_answer(lang: str, plan: dict, results: list[dict]) -> str:
    """Deterministic answer used when no LLM is available for writing."""
    lines = [f"**{plan.get('understanding') or ''}**".strip()]
    for result in results:
        if result["purpose"]:
            lines.append(f"{result['purpose']}:")
        for row in result["rows"][:10]:
            lines.append(
                "- "
                + "; ".join(
                    f"{c}: {_fmt(v)}"
                    for c, v in zip(result["columns"], row, strict=False)
                )
            )
    return "\n".join(line for line in lines if line and line != "****")
