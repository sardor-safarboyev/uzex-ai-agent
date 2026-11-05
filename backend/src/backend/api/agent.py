"""HTTP endpoints for the agentic analyst: JSON and streaming (SSE)."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/agent", tags=["agent"])


class Turn(BaseModel):
    question: str = Field(default="", max_length=2000)
    sql: list[str] = Field(default_factory=list, max_length=3)


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: Literal["auto", "ru", "uz", "uz_cyrl"] = "auto"
    history: list[Turn] = Field(default_factory=list, max_length=4)


EXAMPLES = [
    {"lang": "ru", "q": "Сколько сделок было заключено в 2024 году?"},
    {"lang": "uz", "q": "2025-yilda jami savdo hajmi so'mda qancha bo'lgan?"},
    {"lang": "ru", "q": "Топ-5 товаров по сумме сделок за 2025 год"},
    {"lang": "uz", "q": "Qaysi viloyatda eng ko'p bitim tuzilgan?"},
    {"lang": "ru", "q": "Средневзвешенная цена хлопка-сырца за кг по годам"},
    {"lang": "uz", "q": "Eksport bitimlari soni va dollardagi summasi qancha?"},
    {"lang": "ru", "q": "Кто был крупнейшим покупателем в 2025 году?"},
    {"lang": "uz", "q": "2026-yilda oylar bo'yicha bitimlar soni"},
    {"lang": "ru", "q": "Сколько сделок аннулировано и какая это доля?"},
    {"lang": "uz_cyrl", "q": "2024 йилда буғдой бўйича нечта битим тузилган?"},
]


def _agent(request: Request):
    return getattr(request.app.state, "agent", None)


def _unavailable():
    return JSONResponse(
        status_code=503,
        content={
            "status": "error",
            "error": "agent_unavailable",
            "answer": "Agent is not configured (database or LLM key missing).",
        },
    )


@router.get("/examples")
def examples() -> list[dict]:
    return EXAMPLES


@router.get("/status")
def status(request: Request) -> dict:
    agent = _agent(request)
    if agent is None:
        return {"ready": False}
    return {"ready": True, "models": agent.llm.status()}


@router.post("/ask")
async def ask(body: AgentRequest, request: Request):
    agent = _agent(request)
    if agent is None:
        return _unavailable()
    async with request.app.state.agent_slots:
        return await agent.ask(
            body.question, body.language, [t.model_dump() for t in body.history]
        )


@router.post("/stream")
async def stream(body: AgentRequest, request: Request):
    agent = _agent(request)
    if agent is None:
        return _unavailable()

    async def events():
        async with request.app.state.agent_slots:
            queue_iter = agent.run(
                body.question, body.language, [t.model_dump() for t in body.history]
            )
            try:
                async for event in queue_iter:
                    if await request.is_disconnected():
                        break
                    payload = json.dumps(event, ensure_ascii=False, default=str)
                    yield f"data: {payload}\n\n"
            except asyncio.CancelledError:
                raise
            except Exception:  # never leak internals into the stream
                error = {
                    "type": "final",
                    "data": {
                        "status": "error",
                        "error": "internal",
                        "answer": "Internal error.",
                    },
                }
                yield f"data: {json.dumps(error)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
