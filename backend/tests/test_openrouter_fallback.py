"""Single-completion fallback tests. Every provider request uses MockTransport."""

import asyncio
import json

import httpx
import pytest

from backend.config import Settings
from backend.interpretation import Interpreter

MODEL = "nvidia/nemotron-3.5-lightning:free"
QUESTION = "Покажи число сделок по годам"
PLAN = {
    "version": "1.1",
    "language": "ru",
    "request": {
        "kind": "aggregate",
        "metrics": ["deal_count"],
        "group_by": ["deal_year"],
    },
}


def completion(plan=PLAN):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(plan),
                        "reasoning_details": [{"text": "ignored"}],
                    },
                }
            ]
        },
    )


def settings(**changes):
    return Settings(
        groq_api_key="primary-test-key",
        openrouter_api_key="fallback-test-key",
        groq_max_retries=0,
        **changes,
    )


@pytest.mark.parametrize(
    "semantic_request",
    [
        PLAN["request"],
        {"kind": "clarification", "reason": "currency", "question": "Which currency?"},
        {
            "kind": "unsupported",
            "reason": "unsupported_operation",
            "explanation": "Unsupported",
        },
    ],
)
def test_valid_primary_never_calls_openrouter(semantic_request):
    calls = []

    def handler(message):
        calls.append(message.url.host)
        assert message.url.host == "api.groq.com"
        return completion({**PLAN, "request": semantic_request})

    result = asyncio.run(
        Interpreter(settings(), transport=httpx.MockTransport(handler)).interpret(
            QUESTION
        )
    )
    assert result.outcome != "error" and calls == ["api.groq.com"]


@pytest.mark.parametrize(
    "failure", [429, 500, 401, "timeout", "network", "invalid_plan", "invalid_json"]
)
def test_primary_failure_uses_one_validated_fallback(failure):
    calls = []

    def handler(message):
        payload = json.loads(message.content)
        calls.append((message.url.host, payload))
        if message.url.host == "api.groq.com":
            assert message.headers["Authorization"] == "Bearer primary-test-key"
            if failure == "timeout":
                raise httpx.ReadTimeout("private-provider-body")
            if failure == "network":
                raise httpx.ConnectError("private-provider-body")
            if failure == "invalid_plan":
                return completion({"sql": "DROP TABLE deals"})
            if failure == "invalid_json":
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"content": "not json"},
                            }
                        ]
                    },
                )
            return httpx.Response(
                failure, headers={"Retry-After": "120"}, text="private-provider-body"
            )
        assert str(message.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert message.headers["Authorization"] == "Bearer fallback-test-key"
        assert payload["model"] == MODEL
        assert payload["response_format"] == {"type": "json_object"}
        assert len(payload["messages"]) == 2
        assert payload["messages"][1] == {"role": "user", "content": QUESTION}
        assert "reasoning" not in payload and "reasoning_details" not in payload
        return completion()

    result = asyncio.run(
        Interpreter(settings(), transport=httpx.MockTransport(handler)).interpret(
            QUESTION
        )
    )
    assert result.outcome == "plan" and result.plan.request.group_by == ["deal_year"]
    assert [host for host, _ in calls] == ["api.groq.com", "openrouter.ai"]
    assert "private-provider-body" not in result.model_dump_json()


@pytest.mark.parametrize(
    "secondary,status",
    [
        (429, "rate_limit"),
        (500, "provider_error"),
        (401, "provider_error"),
        ("timeout", "timeout"),
        ("sql", "invalid_response"),
    ],
)
def test_fallback_failure_is_not_retried_or_executed(secondary, status):
    calls = []

    def handler(message):
        calls.append(message.url.host)
        if message.url.host == "api.groq.com":
            return httpx.Response(429)
        if secondary == "timeout":
            raise httpx.ReadTimeout("fallback-test-key")
        if secondary == "sql":
            return completion(
                {
                    "version": "1.1",
                    "language": "ru",
                    "request": {
                        "kind": "aggregate",
                        "metrics": ["deal_count"],
                        "sql": "SELECT secret",
                    },
                }
            )
        return httpx.Response(secondary, text="fallback-test-key private-provider-body")

    configured = settings()
    configured.groq_max_retries = 3
    result = asyncio.run(
        Interpreter(configured, transport=httpx.MockTransport(handler)).interpret(
            QUESTION
        )
    )
    assert result.error == status and result.plan is None
    assert calls == ["api.groq.com", "openrouter.ai"]
    assert "fallback-test-key" not in result.model_dump_json()
    assert "secret" not in result.model_dump_json()


def test_templates_precede_both_providers_and_cooldown_skips_primary():
    calls = []

    def handler(message):
        calls.append(message.url.host)
        return (
            httpx.Response(429, headers={"Retry-After": "120"})
            if message.url.host == "api.groq.com"
            else completion()
        )

    interpreter = Interpreter(settings(), transport=httpx.MockTransport(handler))

    async def check():
        assert (
            await interpreter.interpret("2024-yilda nechta bitim tuzilgan?")
        ).outcome == "plan"
        assert calls == []
        assert (await interpreter.interpret(QUESTION)).outcome == "plan"
        assert (await interpreter.interpret(QUESTION)).outcome == "plan"

    asyncio.run(check())
    assert calls == ["api.groq.com", "openrouter.ai", "openrouter.ai"]


def test_optional_key_and_invalid_input_do_not_call_fallback():
    calls = []

    def handler(message):
        calls.append(message.url.host)
        return httpx.Response(429)

    configured = settings()
    configured.openrouter_api_key = None
    interpreter = Interpreter(configured, transport=httpx.MockTransport(handler))
    assert asyncio.run(interpreter.interpret(QUESTION)).error == "rate_limit"
    assert calls == ["api.groq.com"]
    assert (
        asyncio.run(
            Interpreter(settings(), transport=httpx.MockTransport(handler)).interpret(
                " "
            )
        ).error
        == "invalid_input"
    )
    assert calls == ["api.groq.com"]


def test_openrouter_environment_model_and_secret_redaction(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fallback-test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", MODEL)
    configured = Settings()
    assert configured.openrouter_model == MODEL
    assert configured.openrouter_api_key.get_secret_value() == "fallback-test-key"
    assert "fallback-test-key" not in repr(configured)
