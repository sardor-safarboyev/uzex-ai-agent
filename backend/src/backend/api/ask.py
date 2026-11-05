"""Natural language -> validated logical plan -> deterministic read-only answer."""

import asyncio
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field, StrictStr
from starlette.concurrency import run_in_threadpool

from backend.query.models import QueryExecution
from backend.semantic.models import ContractModel, QueryPlan

router = APIRouter(prefix="/api", tags=["questions"])


class AskRequest(ContractModel):
    question: Annotated[StrictStr, Field(min_length=1, max_length=4000)]
    language: Literal["auto", "uz", "ru"] = "auto"


def response_language(question: str, override: str = "auto") -> Literal["uz", "ru"]:
    """Conservative cues from question words, never from source-name script alone."""
    if override in {"uz", "ru"}:
        return override
    words = set(re.findall(r"[^\W\d_]+", question.lower()))
    if words & {
        "bitimlar",
        "bitim",
        "qancha",
        "nechta",
        "jami",
        "битимлар",
        "қанча",
        "нечта",
    }:
        return "uz"
    if words & {
        "сколько",
        "сделок",
        "сделки",
        "сумма",
        "какова",
        "покажи",
        "переведи",
        "конвертируй",
    }:
        return "ru"
    return "uz"


class AskResponse(ContractModel):
    language: Literal["uz", "ru"]
    status: Literal[
        "answered", "no_match", "insufficient_data", "ambiguous", "unsupported", "error"
    ]
    answer: str
    reason: str | None = None
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
    reason = None
    scope = execution.scope
    if scope:
        request = scope.request
        reason = getattr(request, "reason", None)
        aggregate = getattr(request, "aggregate", request)
        money = getattr(aggregate, "money", None)
        if money and money.mode == "convert_to_uzs":
            reason = "currency_conversion"

    if status == "unsupported" and result.outcome.explanation in {
        "Unverified source unit labels prevent applying "
        "the requested unit policy safely.",
        "The selected scope contains physical units "
        "outside the semantic allowlist; their values "
        "cannot be represented or combined.",
    }:
        reason = "unsupported_unit"
    if status in {"unsupported", "ambiguous"}:
        answer = REASONS[result.language].get(reason, answer)
    if status == "answered":
        data = result.outcome.data
        if len(data.rows) == len(data.columns) == 1:
            column = data.columns[0]
            value = data.rows[0][0]
            if value is not None:
                label = messages.get(column.field, column.field)
                suffix = " ".join(str(v) for v in (column.currency, column.unit) if v)
                answer = f"{label}: {value}{' ' + suffix if suffix else ''}"
                if column.field == "deal_count":
                    count = f"{int(value):,}".replace(",", " ")
                    answer = (
                        f"Jami {count} ta bitim qayd etilgan."
                        if result.language == "uz"
                        else f"Всего зарегистрировано {count} сделок."
                    )
    return AskResponse(
        language=result.language,
        status=status,
        answer=answer,
        reason=reason,
        execution=execution,
        error=result.outcome.code if status == "error" else None,
    )


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request, response: Response) -> AskResponse:
    language = response_language(body.question, body.language)
    state = request.app.state
    # Reject saturation instead of accumulating an unbounded provider request queue.
    try:
        await asyncio.wait_for(state.ask_slots.acquire(), timeout=0.05)
    except TimeoutError:
        response.status_code = 503
        return AskResponse(
            language=language,
            status="error",
            error="busy",
            answer=MESSAGES[language]["error"],
        )
    try:
        interpretation = await state.interpreter.interpret(body.question)
        if interpretation.outcome == "error":
            response.status_code = 503
            return AskResponse(
                language=language,
                status="error",
                error=interpretation.error,
                answer=(
                    RETRY[language]
                    if interpretation.error == "rate_limit"
                    else MESSAGES[language]["error"]
                ),
            )
        plan = QueryPlan.model_validate(
            {**interpretation.plan.model_dump(), "language": language}
        )
        execution = await run_in_threadpool(
            state.query_engine.execute,
            plan,
        )
        result = present(execution)
        if result.status == "error":
            response.status_code = 503
        return result
    except Exception:
        # Do not return exception strings, provider bodies, SQL, paths or secrets.
        response.status_code = 503
        return AskResponse(
            language=language,
            status="error",
            error="internal_error",
            answer=MESSAGES[language]["error"],
        )
    finally:
        state.ask_slots.release()


RETRY = {
    "uz": "Xizmat band. Birozdan so‘ng qayta urinib ko‘ring.",
    "ru": "Сервис занят. Повторите попытку позже.",
}
REASONS = {
    "uz": {
        "currency_conversion": (
            "USD dan UZS ga o‘tkazish qo‘llanmaydi: kursni qo‘llash "
            "va yaxlitlash qoidalari tasdiqlanmagan."
        ),
        "unverified_mapping": (
            "Nom yoki identifikator mosligi tasdiqlanmagan. "
            "Manbadagi aniq nomni ko‘rsating."
        ),
        "unavailable_data": "Bu so‘rov uchun kerakli ma’lumot mavjud emas.",
        "unsupported_unit": (
            "So‘ralgan o‘lchov birligi yoki birliklarni o‘tkazish "
            "qoidasi tasdiqlanmagan."
        ),
        "unsupported_date": (
            "Bu sana filtri qo‘llanmaydi. Aniq boshlanish va tugash "
            "sanalarini ko‘rsating."
        ),
        "currency": "Qaysi valyuta kerak: USD yoki UZS?",
        "unit": "Qaysi o‘lchov birligi kerak?",
    },
    "ru": {
        "currency_conversion": (
            "Перевод USD в UZS не поддерживается: правила "
            "применения курса и округления не проверены."
        ),
        "unverified_mapping": (
            "Соответствие названия или идентификатора не проверено. "
            "Укажите точное название из источника."
        ),
        "unavailable_data": "Данные, необходимые для этого запроса, отсутствуют.",
        "unsupported_unit": (
            "Запрошенная единица или правила пересчёта единиц не проверены."
        ),
        "unsupported_date": (
            "Этот фильтр дат не поддерживается. Укажите точные даты начала и окончания."
        ),
        "currency": "Какая валюта нужна: USD или UZS?",
        "unit": "Какая единица измерения нужна?",
    },
}
