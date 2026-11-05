"""Natural language -> validated logical plan -> deterministic read-only answer."""

import asyncio
import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field, StrictStr
from starlette.concurrency import run_in_threadpool

from backend.api.availability import Availability, availability_message, requested_years
from backend.api.summaries import count_summary
from backend.database.errors import DatabaseAccessError
from backend.interpretation.templates import template_plan, yearly_count_claim
from backend.query.models import QueryExecution
from backend.query.snapshot import InsufficientSnapshot
from backend.semantic.models import ContractModel, QueryPlan
from backend.timing import timing

router = APIRouter(prefix="/api", tags=["questions"])
logger = logging.getLogger(__name__)


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


class CountVerification(ContractModel):
    year: int
    claimed_count: Annotated[int, Field(strict=True, ge=0)]
    actual_count: Annotated[int, Field(strict=True, ge=0)]
    matches: bool


class AskResponse(ContractModel):
    language: Literal["uz", "ru"]
    status: Literal[
        "answered", "no_match", "insufficient_data", "ambiguous", "unsupported", "error"
    ]
    answer: str
    reason: str | None = None
    execution: QueryExecution | None = None
    availability: Availability | None = None
    verification: CountVerification | None = None
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
    if status in {"unsupported", "ambiguous", "insufficient_data"}:
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
    answer = count_summary(execution) or answer
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
    with timing("total", request=True):
        return await _ask(body, request, response)


async def _ask(body: AskRequest, request: Request, response: Response) -> AskResponse:
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
            answer=error_message(language, "busy"),
        )
    try:
        years = requested_years(body.question)
        if years and state.settings.database_path is not None:
            with timing("duckdb_coverage"):
                available = await run_in_threadpool(state.query_engine.dataset_years)
            missing = sorted(years - set(available))
            if missing and available:
                availability = Availability(
                    available_years=available, missing_years=missing
                )
                return AskResponse(
                    language=language,
                    status="insufficient_data",
                    reason="outside_coverage",
                    availability=availability,
                    answer=availability_message(availability, language),
                )
        interpretation = await state.interpreter.interpret(body.question)
        if interpretation.outcome == "error":
            if interpretation.error == "rate_limit":
                response.headers["Retry-After"] = str(
                    max(1, state.interpreter.retry_after_seconds())
                )
            logger.warning(
                "ask_failed stage=interpretation code=%s", interpretation.error
            )
            response.status_code = 503
            return AskResponse(
                language=language,
                status="error",
                error=interpretation.error,
                answer=error_message(language, interpretation.error),
            )
        plan = QueryPlan.model_validate(
            {**interpretation.plan.model_dump(), "language": language}
        )
        with timing("duckdb"):
            execution = await run_in_threadpool(state.query_engine.execute, plan)
        result = present(execution)
        claim = yearly_count_claim(body.question)
        if (
            claim
            and result.status == "answered"
            and plan.request == template_plan(body.question).request
        ):
            actual = execution.result.outcome.data.rows[0][0]
            result.verification = CountVerification(
                year=claim[0],
                claimed_count=claim[1],
                actual_count=actual,
                matches=claim[1] == actual,
            )
            count = f"{actual:,}".replace(",", " ")
            if language == "uz":
                verdict = (
                    "Tasdiq to‘g‘ri." if claim[1] == actual else "Tasdiq noto‘g‘ri."
                )
                result.answer = (
                    f"{verdict} {claim[0]}-yilda amalda {count} ta bitim qayd etilgan."
                )
            else:
                verdict = (
                    "Утверждение верно."
                    if claim[1] == actual
                    else "Утверждение неверно."
                )
                result.answer = (
                    f"{verdict} В {claim[0]} году фактически "
                    f"зарегистрировано {count} сделок."
                )
        if result.status == "error":
            logger.warning("ask_failed stage=execution code=%s", result.error)
            result.answer = error_message(language, result.error)
            response.status_code = 503
        return result
    except (DatabaseAccessError, InsufficientSnapshot):
        logger.warning("ask_failed stage=coverage code=execution_failed")
        response.status_code = 503
        return AskResponse(
            language=language,
            status="error",
            error="execution_failed",
            answer=error_message(language, "execution_failed"),
        )
    except Exception:
        # Do not return exception strings, provider bodies, SQL, paths or secrets.
        logger.error("ask_failed stage=api code=internal_error")
        response.status_code = 503
        return AskResponse(
            language=language,
            status="error",
            error="internal_error",
            answer=error_message(language, "internal_error"),
        )
    finally:
        state.ask_slots.release()


RETRY = {
    "uz": "Xizmat band. Birozdan so‘ng qayta urinib ko‘ring.",
    "ru": "Сервис занят. Повторите попытку позже.",
}
ERROR_MESSAGES = {
    "uz": {
        "configuration": (
            "Til xizmati sozlanmagan. Xizmat administratoriga murojaat qiling."
        ),
        "invalid_input": "Savol 1–4000 belgidan iborat bo‘lishi kerak.",
        "invalid_response": (
            "Til xizmati yaroqli so‘rov rejasini qaytarmadi. "
            "Keyinroq qayta urinib ko‘ring."
        ),
        "provider_error": "Til xizmati mavjud emas. Keyinroq urinib ko‘ring.",
        "rate_limit": RETRY["uz"],
        "busy": RETRY["uz"],
        "timeout": "Til xizmati javob bermadi. Qayta urinib ko‘ring.",
        "execution_failed": "Ma’lumotlar bazasiga so‘rov bajarilmadi.",
        "validation_failed": "So‘rov rejasini tekshirib bo‘lmadi.",
        "internal_error": "So‘rovni xavfsiz bajarib bo‘lmadi.",
    },
    "ru": {
        "configuration": "Языковой сервис не настроен. Обратитесь к администратору.",
        "invalid_input": "Вопрос должен содержать от 1 до 4000 символов.",
        "invalid_response": (
            "Языковой сервис вернул некорректный план. Повторите попытку позже."
        ),
        "provider_error": "Языковой сервис недоступен. Попробуйте позже.",
        "rate_limit": RETRY["ru"],
        "busy": RETRY["ru"],
        "timeout": "Языковой сервис не ответил. Попробуйте снова.",
        "execution_failed": "Не удалось выполнить запрос к базе данных.",
        "validation_failed": "Не удалось проверить план запроса.",
        "internal_error": "Не удалось безопасно выполнить запрос.",
    },
}


def error_message(language: str, code: str | None) -> str:
    return ERROR_MESSAGES[language].get(code, MESSAGES[language]["error"])


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
        "currency": (
            "Bitimlarning umumiy qiymatini UZS yoki USD valyutasida hisoblaymi?"
        ),
        "ambiguous_metric": "Qaysi mezon kerak: bitimlar soni yoki jismoniy hajm?",
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
        "currency": "Рассчитать общую стоимость сделок в UZS или USD?",
        "ambiguous_metric": (
            "По какому показателю: количеству сделок или физическому объёму?"
        ),
        "unit": "Какая единица измерения нужна?",
    },
}

REASONS["uz"].update(
    {
        "unavailable_profit": (
            "To‘plamda sof foyda va xarajatlar ma’lumoti yo‘q. "
            "Bitim qiymati foyda emas."
        ),
        "unavailable_employees": "To‘plamda kompaniyalar xodimlari soni mavjud emas.",
        "unavailable_tax": (
            "To‘plamda to‘langan soliq summalari yo‘q. "
            "QQS maqomi soliq to‘lovini bildirmaydi."
        ),
        "unsupported_causality": (
            "To‘plam yetakchilik sabablarini aniqlashga imkon bermaydi. "
            "Reyting uchun bitimlar soni yoki jismoniy hajmni tanlang."
        ),
        "unsupported_statistic": (
            "Mediana tasdiqlangan hisoblash amallari orasida yo‘q."
        ),
        "unsupported_yearly_series": (
            "Bir nechta yil uchun ketma-ket yillik foizlar qatori qo‘llanmaydi. "
            "Ikki qo‘shni yilni ko‘rsating, masalan: 2024–2025-yillarda "
            "bitimlar sonining yillik o‘sish yoki kamayish foizlarini hisobla."
        ),
        "unsupported_forecast": (
            "Prognoz hisoblanmaydi; faqat mavjud manba bitimlari tahlil qilinadi."
        ),
    }
)
REASONS["ru"].update(
    {
        "unavailable_profit": (
            "В наборе нет чистой прибыли и расходов. "
            "Стоимость сделок не является прибылью."
        ),
        "unavailable_employees": "В наборе нет численности сотрудников компаний.",
        "unavailable_tax": (
            "В наборе нет сумм уплаченных налогов. "
            "Статус плательщика НДС не подтверждает уплату налога."
        ),
        "unsupported_causality": (
            "Набор не позволяет установить причины лидерства. "
            "Для рейтинга выберите количество сделок или физический объём."
        ),
        "unsupported_statistic": "Медиана не входит в проверенные операции расчёта.",
        "unsupported_yearly_series": (
            "Последовательный ряд годовых процентных изменений не поддерживается. "
            "Можно сравнить два соседних года, например 2024 и 2025."
        ),
        "unsupported_forecast": (
            "Прогнозирование не поддерживается; анализируются только имеющиеся сделки."
        ),
    }
)
