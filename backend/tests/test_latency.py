"""Mocked provider latency paths; no live calls or source/database changes."""

import asyncio
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_openrouter_fallback import QUESTION, completion, settings

from backend.config import Settings
from backend.interpretation import Interpreter
from backend.main import create_app


def timings(caplog):
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "uvicorn.error"
        and record.message.startswith('{"event": "latency"')
    ]


def test_cooldown_and_fast_failover_have_safe_provider_timings(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    calls, code = [], [503]

    def handler(request):
        calls.append(request.url.host)
        return (
            httpx.Response(code[0], headers={"Retry-After": "120"})
            if request.url.host == "api.groq.com"
            else completion()
        )

    configured = settings()
    configured.groq_max_retries = 3
    interpreter = Interpreter(configured, transport=httpx.MockTransport(handler))

    async def check():
        assert (await interpreter.interpret(QUESTION)).outcome == "plan"
        assert calls == ["api.groq.com", "openrouter.ai"]
        code[0] = 429
        assert (await interpreter.interpret(QUESTION)).outcome == "plan"
        assert (await interpreter.interpret(QUESTION)).outcome == "plan"
        assert calls == [
            "api.groq.com",
            "openrouter.ai",
            "api.groq.com",
            "openrouter.ai",
            "openrouter.ai",
        ]
        assert (
            await interpreter.interpret("2024-yilda nechta bitim tuzilgan?")
        ).outcome == "plan"
        assert len(calls) == 5

    asyncio.run(check())
    records = timings(caplog)
    assert {record["stage"] for record in records} >= {"template", "groq", "openrouter"}
    assert any(
        record.get("skipped") and record["reason"] == "cooldown" for record in records
    )
    assert "test-key" not in json.dumps(records) and QUESTION not in json.dumps(records)


def test_bounded_independent_provider_timeouts():
    for field in ("groq_timeout_seconds", "openrouter_timeout_seconds"):
        for value in (0, 121):
            with pytest.raises(ValidationError):
                Settings(**{field: value})
    calls = []

    async def slow(request):
        calls.append(request.url.host)
        await asyncio.sleep(0.1)
        return completion()

    configured = settings(groq_timeout_seconds=0.01, openrouter_timeout_seconds=0.01)
    configured.groq_max_retries = 3
    result = asyncio.run(
        Interpreter(configured, transport=httpx.MockTransport(slow)).interpret(QUESTION)
    )
    assert result.error == "timeout"
    assert calls == ["api.groq.com", "openrouter.ai"]


def test_total_and_execution_logs_share_generated_id_without_content(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    app = create_app(Settings())

    def forbidden(_):
        raise AssertionError("A deterministic query must never call providers")

    app.state.interpreter = Interpreter(
        settings(), transport=httpx.MockTransport(forbidden)
    )
    question = "2024-yilda barcha USD bitimlarini UZS ga aylantir."
    with TestClient(app) as client:
        response = client.post("/api/ask", json={"question": question})
    assert response.status_code == 200 and response.json()["status"] == "unsupported"
    records = timings(caplog)
    assert {record["stage"] for record in records} == {"template", "duckdb", "total"}
    assert len({record["request_id"] for record in records}) == 1
    assert records[0]["request_id"] != "-"
    assert all(record["duration_ms"] >= 0 for record in records)
    assert question not in json.dumps(records) and "test-key" not in json.dumps(records)
