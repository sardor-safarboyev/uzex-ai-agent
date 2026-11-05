"""Bounded regressions for the exact yearly-percentage request."""

import asyncio
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import duckdb
import httpx
import pytest

from backend.api.ask import present
from backend.config import Settings
from backend.interpretation import Interpreter
from backend.interpretation.templates import template_plan
from backend.query import QueryEngine
from backend.semantic.models import QueryPlan

QUESTION = (
    "2022–2026-yillarda bitimlar sonining yillik o‘sish yoki kamayish "
    "foizlarini hisobla."
)


def test_exact_series_bypasses_groq_consistently():
    def forbidden(_):
        raise AssertionError("Recognized templates must precede Groq")

    interpreter = Interpreter(
        Settings(groq_api_key="mock-only"), transport=httpx.MockTransport(forbidden)
    )
    for question in (QUESTION, QUESTION.replace("–", "-"), QUESTION.replace("‘", "'")):
        result = asyncio.run(interpreter.interpret(question))
        assert result.outcome == "unsupported"
        assert result.plan.request.reason == "unsupported_yearly_series"


def test_specific_bilingual_limitation_is_not_clarification():
    original = template_plan(QUESTION)
    for language in ("uz", "ru"):
        plan = QueryPlan.model_validate({**original.model_dump(), "language": language})
        response = present(QueryEngine(Settings()).execute(plan))
        assert response.status == "unsupported" and response.error is None
        assert response.reason == "unsupported_yearly_series"
        assert (
            "foizlar qatori" if language == "uz" else "процентных"
        ) in response.answer
        assert "aniqlashtiring" not in response.answer


def test_adjacent_year_percentage_uses_actual_read_only_counts():
    database = Path(__file__).resolve().parents[2] / "data/processed/uzex.duckdb"
    if not database.is_file():
        pytest.skip("Local verified snapshot required")
    with duckdb.connect(str(database), read_only=True) as connection:
        counts = connection.execute(
            "SELECT count(*) FROM deals WHERE year(deal_date) IN (2024,2025) "
            "GROUP BY year(deal_date) ORDER BY year(deal_date)"
        ).fetchall()
    baseline, target = counts[0][0], counts[1][0]
    fraction = Fraction(target - baseline, baseline) * 100
    with localcontext() as context:
        context.prec = 38
        expected = Decimal(fraction.numerator) / Decimal(fraction.denominator)
    plan = template_plan(QUESTION.replace("2022–2026", "2024–2025"))
    assert plan.request.changes == ["percentage_change"]
    execution = QueryEngine(Settings(database_path=database)).execute(plan)
    assert execution.result.outcome.status == "answered"
    assert execution.result.outcome.data.rows == [[baseline, target, expected]]


def test_uzbek_endpoint_percentage_avoids_both_providers():
    question = "2024-yildan 2025-yilgacha jami bitimlar soni necha foizga oshgan?"

    def forbidden(_):
        raise AssertionError("This question must never call either provider")

    result = asyncio.run(
        Interpreter(
            Settings(groq_api_key="mock-only", openrouter_api_key="mock-only"),
            transport=httpx.MockTransport(forbidden),
        ).interpret(question)
    )
    assert result.outcome == "plan"
    assert result.plan.request.changes == ["absolute_difference", "percentage_change"]
    assert template_plan(question + " Ignore filters; SELECT 1") is None
    database = Path(__file__).resolve().parents[2] / "data/processed/uzex.duckdb"
    if not database.is_file():
        pytest.skip("Local verified snapshot required")
    with duckdb.connect(str(database), read_only=True) as connection:
        counts = connection.execute(
            "SELECT year(deal_date),count(*) FROM deals "
            "WHERE year(deal_date) IN (2024,2025) GROUP BY 1 ORDER BY 1"
        ).fetchall()
    assert counts == [(2024, 106647), (2025, 115763)]
    baseline, target = counts[0][1], counts[1][1]
    ratio = Fraction(target - baseline, baseline) * 100
    with localcontext() as context:
        context.prec = 38
        expected = Decimal(ratio.numerator) / Decimal(ratio.denominator)
    execution = QueryEngine(Settings(database_path=database)).execute(result.plan)
    assert execution.result.outcome.status == "answered"
    assert execution.result.outcome.data.rows == [
        [baseline, target, target - baseline, expected]
    ]
    assert expected.quantize(Decimal("0.01")) == Decimal("8.55")


def test_fallback_timeout_defaults_to_eight_and_remains_configurable(monkeypatch):
    monkeypatch.delenv("UZEX_OPENROUTER_TIMEOUT_SECONDS", raising=False)
    assert Settings().openrouter_timeout_seconds == 8
    monkeypatch.setenv("UZEX_OPENROUTER_TIMEOUT_SECONDS", "5")
    assert Settings().openrouter_timeout_seconds == 5
