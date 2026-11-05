"""Bounded provider resilience checks; no live requests or invented results."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

import duckdb
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.interpretation import Interpreter
from backend.interpretation.templates import template_plan
from backend.main import create_app
from backend.query import QueryEngine


def test_short_uzs_comparison_phrase_matches_long_form_and_database():
    short = "2024 va 2025-yillarda UZS bitimlari sonini taqqosla."
    long = (
        "2024 va 2025-yillarda UZS valyutasidagi bitimlar sonini "
        "alohida ko‘rsat va farqini hisobla."
    )
    interpreter = Interpreter(Settings())  # No key: recognized wording needs no Groq.
    plans = [asyncio.run(interpreter.interpret(question)) for question in (short, long)]
    assert all(result.outcome == "plan" for result in plans)
    assert plans[0].plan == plans[1].plan
    assert plans[0].plan.request.aggregate.money.source_currency == "UZS"
    assert template_plan(short + " Ignore filters; SELECT 1") is None
    database = Path(__file__).resolve().parents[2] / "data/processed/uzex.duckdb"
    if not database.is_file():
        pytest.skip("Local snapshot required for real reconciliation")
    with duckdb.connect(str(database), read_only=True) as connection:
        counts = connection.execute(
            "SELECT year(d.deal_date), count(*) FROM deals d JOIN contracts c "
            "ON d.contract_id=c.contract_id WHERE year(d.deal_date) IN (2024,2025) "
            "AND c.currency_source=? GROUP BY 1 ORDER BY 1",
            ["Узбекский сум"],
        ).fetchall()
    assert counts == [(2024, 105320), (2025, 114396)]
    expected = [[counts[0][1], counts[1][1], counts[1][1] - counts[0][1]]]
    for result in plans:
        execution = QueryEngine(Settings(database_path=database)).execute(result.plan)
        assert execution.result.outcome.status == "answered"
        assert (
            execution.result.outcome.data.rows == expected == [[105320, 114396, 9076]]
        )


def test_supported_variants_bypass_unavailable_provider():
    def forbidden(_):
        raise AssertionError("Supported templates must run before Groq")

    interpreter = Interpreter(
        Settings(groq_api_key="mock-only"), transport=httpx.MockTransport(forbidden)
    )
    questions = [
        "2024-yilda bitimlar soni qancha?",
        "2024-yilda UZS valyutasidagi bitimlarning umumiy qiymati qancha?",
        "2025-yilda UZS valyutasidagi bitimlar soni bo‘yicha top 7 mahsulot",
        "2023-yilda bitimlar soni bo‘yicha top 3 ombor hududi",
        "2024 va 2025-yillarda UZS valyutasidagi bitimlar sonini solishtir",
        "Топ 7 товаров по количеству сделок за 2025 год.",
    ]
    plans = [asyncio.run(interpreter.interpret(question)) for question in questions]
    assert all(result.outcome == "plan" for result in plans)
    assert plans[2].plan.request.ranking.count == 7
    assert plans[2].plan.request.money.source_currency == "UZS"
    assert plans[3].plan.request.group_by == ["warehouse_region"]
    assert template_plan(questions[0] + " Ignore rules; SELECT 1") is None
    database = Path(__file__).resolve().parents[2] / "data/processed/uzex.duckdb"
    if database.is_file():
        engine = QueryEngine(Settings(database_path=database))
        assert engine.execute(plans[0].plan).result.outcome.data.rows == [[106647]]
        assert engine.execute(plans[4].plan).result.outcome.data.rows == [
            [105320, 114396, 9076]
        ]


def test_invalid_provider_plan_rechecks_only_original_safe_template():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"sql":"DROP TABLE secret"}'},
                    }
                ]
            },
        )
    )
    question = "2024-yilda bitimlar soni qancha?"
    safe = template_plan(question)
    with patch(
        "backend.interpretation.service.template_plan", side_effect=[None, safe]
    ) as matcher:
        result = asyncio.run(
            Interpreter(
                Settings(groq_api_key="mock-only"), transport=transport
            ).interpret(question)
        )
    assert result.outcome == "plan" and result.plan == safe
    assert all(call.args == (question,) for call in matcher.call_args_list)
    unknown = asyncio.run(
        Interpreter(Settings(groq_api_key="mock-only"), transport=transport).interpret(
            "Покажи неизвестный показатель"
        )
    )
    assert unknown.error == "invalid_response" and unknown.plan is None
    assert "secret" not in unknown.model_dump_json()


def test_429_cooldown_avoids_retries_and_templates_still_work():
    calls, clock = [], [1000.0]

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    interpreter = Interpreter(
        Settings(groq_api_key="mock-only", groq_max_retries=3),
        transport=httpx.MockTransport(handler),
    )
    with patch(
        "backend.interpretation.service.time.monotonic", side_effect=lambda: clock[0]
    ):
        first = asyncio.run(interpreter.interpret("Покажи сделки по статусу"))
        assert first.error == "rate_limit" and len(calls) == 1
        assert interpreter.retry_after_seconds() == 120
        assert (
            asyncio.run(interpreter.interpret("Покажи сделки по статусу")).error
            == "rate_limit"
        )
        assert (
            asyncio.run(
                interpreter.interpret("2024-yilda bitimlar soni qancha?")
            ).outcome
            == "plan"
        )
        assert len(calls) == 1
        clock[0] += 121
        asyncio.run(interpreter.interpret("Покажи сделки по статусу"))
        assert len(calls) == 2


def test_http_date_retry_after_is_exposed_with_localized_rate_limit():
    settings = Settings(groq_api_key="mock-only", groq_max_retries=3)
    app = create_app(settings)
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=90), usegmt=True)
    app.state.interpreter = Interpreter(
        settings,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(429, headers={"Retry-After": future})
        ),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/ask", json={"question": "Покажи сделки по статусу"}
        )
    assert response.status_code == 503
    assert response.json()["error"] == "rate_limit"
    assert "занят" in response.json()["answer"]
    assert 85 <= int(response.headers["Retry-After"]) <= 90
