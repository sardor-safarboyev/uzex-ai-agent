"""Natural language -> validated logical plan -> deterministic read-only answer."""

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field, StrictStr
from starlette.concurrency import run_in_threadpool

from backend.query.models import QueryExecution
from backend.semantic.models import ContractModel, QueryPlan

router = APIRouter(prefix="/api", tags=["questions"])


class AskRequest(ContractModel):
    question: Annotated[StrictStr, Field(min_length=1, max_length=4000)]
    language: Literal["uz", "ru"] = "uz"


class AskResponse(ContractModel):
    language: Literal["uz", "ru"]
    status: Literal[
        "answered", "no_match", "insufficient_data", "ambiguous", "unsupported", "error"
    ]
    answer: str
    execution: QueryExecution | None = None
    error: (
        Literal[
            "configuration",
            "invalid_input",
            "invalid_response",
            "rate_limit",
            "timeout",
            "provider_error",
            "busy",
            "execution_failed",
            "internal_error",
            "validation_failed",
        ]
        | None
    ) = None


class Example(ContractModel):
    id: str
    uz: str
    ru: str


EXAMPLES = [
    Example(id="count", uz="Bitimlar soni qancha?", ru="Сколько всего сделок?"),
    Example(
        id="sum",
        uz="UZS valyutasidagi bitimlarning jami summasi qancha?",
        ru="Какова общая сумма сделок в UZS?",
    ),
    Example(
        id="regions",
        uz="Viloyatlar bo‘yicha bitimlar soni qancha?",
        ru="Сколько сделок по каждому региону склада?",
    ),
    Example(
        id="year",
        uz="2024-yilda bitimlar soni qancha?",
        ru="Сколько сделок за 2024 год?",
    ),
]


def example_plan(example_id: str, language: str = "uz") -> QueryPlan:
    """Expected semantic scopes, used for offline example verification only."""
    fields = {
        "count": {},
        "sum": {
            "metrics": ["deal_value"],
            "money": {"mode": "source", "source_currency": "UZS"},
        },
        "regions": {"group_by": ["warehouse_region"]},
        "year": {"date_range": {"start": "2024-01-01", "end": "2024-12-31"}},
    }[example_id]
    return QueryPlan.model_validate(
        {
            "version": "1.1",
            "language": language,
            "request": {"kind": "aggregate", "metrics": ["deal_count"], **fields},
        }
    )


@router.get("/examples", response_model=list[Example])
def examples() -> list[Example]:
    return EXAMPLES


MESSAGES = {
    "uz": {
        "answered": "Natija: {count} qator. Tafsilotlar va manbalar quyida.",
        "no_match": "So‘rovga mos bitim topilmadi.",
        "insufficient_data": "Aniq javob uchun ma’lumot yetarli emas.",
        "ambiguous": (
            "So‘rov, sana, valyuta, o‘lchov birligi yoki aniq nomni aniqlashtiring."
        ),
        "unsupported": "Bu so‘rov tasdiqlangan qoidalar bilan qo‘llanmaydi.",
        "error": (
            "So‘rov bajarilmadi. Qayta urinib ko‘ring yoki sozlamalarni tekshiring."
        ),
        "deal_count": "Bitimlar soni",
        "deal_value": "Jami summa",
        "physical_volume": "Jismoniy hajm",
        "delivered_lots": "Yetkazilgan lotlar",
        "average_unit_price": "O‘rtacha birlik narxi",
    },
    "ru": {
        "answered": "Результат: строк — {count}. Данные и источники ниже.",
        "no_match": "Сделки по этому запросу не найдены.",
        "insufficient_data": "Недостаточно данных для достоверного ответа.",
        "ambiguous": "Уточните запрос, даты, валюту, единицу или точное название.",
        "unsupported": "Запрос не поддерживается проверенными правилами.",
        "error": "Запрос не выполнен. Повторите попытку или проверьте настройки.",
        "deal_count": "Количество сделок",
        "deal_value": "Общая сумма",
        "physical_volume": "Физический объём",
        "delivered_lots": "Поставленные лоты",
        "average_unit_price": "Средняя цена за единицу",
    },
}


def present(execution: QueryExecution) -> AskResponse:
    result = execution.result
    status = result.outcome.status
    messages = MESSAGES[result.language]
    answer = messages[status].format(count=execution.returned_rows)
    if status == "answered":
        data = result.outcome.data
        if len(data.rows) == len(data.columns) == 1:
            column = data.columns[0]
            value = data.rows[0][0]
            if value is not None:
                label = messages.get(column.field, column.field)
                suffix = " ".join(str(v) for v in (column.currency, column.unit) if v)
                answer = f"{label}: {value}{' ' + suffix if suffix else ''}"
    return AskResponse(
        language=result.language,
        status=status,
        answer=answer,
        execution=execution,
        error=result.outcome.code if status == "error" else None,
    )


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request, response: Response) -> AskResponse:
    state = request.app.state
    # Reject saturation instead of accumulating an unbounded provider request queue.
    try:
        await asyncio.wait_for(state.ask_slots.acquire(), timeout=0.05)
    except TimeoutError:
        response.status_code = 503
        return AskResponse(
            language=body.language,
            status="error",
            error="busy",
            answer=MESSAGES[body.language]["error"],
        )
    try:
        interpretation = await state.interpreter.interpret(body.question)
        if interpretation.outcome == "error":
            response.status_code = 503
            return AskResponse(
                language=body.language,
                status="error",
                error=interpretation.error,
                answer=MESSAGES[body.language]["error"],
            )
        execution = await run_in_threadpool(
            state.query_engine.execute,
            interpretation.plan,
        )
        result = present(execution)
        if result.status == "error":
            response.status_code = 503
        return result
    except Exception:
        # Do not return exception strings, provider bodies, SQL, paths or secrets.
        response.status_code = 503
        return AskResponse(
            language=body.language,
            status="error",
            error="internal_error",
            answer=MESSAGES[body.language]["error"],
        )
    finally:
        state.ask_slots.release()
