"""OpenAI-compatible chat clients with per-model rate-limit aware fallback.

Groq's free tier limits tokens per minute *per model*, so the pool rotates
across several Groq models (each has its own budget) and finally OpenRouter.
Rate-limit headers are tracked so an exhausted model is skipped instantly
instead of waiting for a 429.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("uzex.agent.llm")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(Exception):
    pass


@dataclass
class ModelSlot:
    provider: str  # "groq" | "openrouter"
    model: str
    url: str
    key: str
    extra: dict = field(default_factory=dict)
    remaining_tokens: int | None = None
    tokens_reset_at: float = 0.0
    cooldown_until: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    def available(self, need_tokens: int) -> bool:
        now = time.monotonic()
        if now < self.cooldown_until:
            return False
        if self.remaining_tokens is not None and now < self.tokens_reset_at:
            return self.remaining_tokens >= need_tokens
        return True

    def wait_hint(self, need_tokens: int) -> float:
        now = time.monotonic()
        waits = [max(0.0, self.cooldown_until - now)]
        if self.remaining_tokens is not None and self.remaining_tokens < need_tokens:
            waits.append(max(0.0, self.tokens_reset_at - now))
        return max(waits)


_DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+)ms)?")


def _seconds(text: str | None) -> float:
    """Parse Groq reset values like '1m26.4s', '922ms', '7.5s'."""
    if not text:
        return 0.0
    match = _DURATION.fullmatch(text.strip())
    if not match:
        try:
            return float(text)
        except ValueError:
            return 0.0
    minutes, seconds, millis = match.groups()
    return float(minutes or 0) * 60 + float(seconds or 0) + float(millis or 0) / 1000


@dataclass
class Completion:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float


class LLMPool:
    def __init__(
        self,
        groq_key: str | None,
        openrouter_key: str | None,
        openrouter_model: str,
        timeout: float = 30.0,
    ):
        self.slots: dict[str, ModelSlot] = {}
        if groq_key:
            self._add(
                "groq",
                "openai/gpt-oss-120b",
                GROQ_URL,
                groq_key,
                {"include_reasoning": False},
            )
            self._add(
                "groq",
                "qwen/qwen3.8-27b",
                GROQ_URL,
                groq_key,
                {"reasoning_effort": "none"},
            )
            self._add(
                "groq",
                "openai/gpt-oss-20b",
                GROQ_URL,
                groq_key,
                {"include_reasoning": False},
            )
        if openrouter_key:
            self._add(
                "openrouter", openrouter_model, OPENROUTER_URL, openrouter_key, {}
            )
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0))

    def _add(self, provider, model, url, key, extra):
        slot = ModelSlot(provider, model, url, key, extra)
        self.slots[slot.label] = slot

    @property
    def configured(self) -> bool:
        return bool(self.slots)

    def ordered(self, preference: list[str]) -> list[ModelSlot]:
        chosen = [self.slots[p] for p in preference if p in self.slots]
        rest = [s for s in self.slots.values() if s not in chosen]
        return chosen + rest

    async def complete(
        self,
        messages: list[dict],
        *,
        preference: list[str],
        json_mode: bool = True,
        max_tokens: int = 1500,
        reasoning_effort: str | None = None,
        need_tokens: int = 3000,
        max_wait: float = 20.0,
    ) -> Completion:
        if not self.slots:
            raise LLMError("no_provider_configured")
        deadline = time.monotonic() + max_wait
        last_error = "unavailable"
        while True:
            slots = self.ordered(preference)
            ready = [s for s in slots if s.available(need_tokens)]
            for slot in ready:
                try:
                    return await self._call(
                        slot, messages, json_mode, max_tokens, reasoning_effort
                    )
                except LLMError as error:
                    last_error = str(error)
                    log.warning("llm %s failed: %s", slot.label, last_error)
            # Everything is busy: wait for the soonest budget refill, bounded.
            wait = min((s.wait_hint(need_tokens) for s in slots), default=1.0)
            wait = max(0.5, min(wait, 8.0))
            if time.monotonic() + wait > deadline:
                raise LLMError(last_error)
            await asyncio.sleep(wait)

    async def _call(self, slot, messages, json_mode, max_tokens, reasoning_effort):
        body = {
            "model": slot.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            **slot.extra,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if reasoning_effort and "gpt-oss" in slot.model:
            body["reasoning_effort"] = reasoning_effort
        started = time.monotonic()
        try:
            response = await self._client.post(
                slot.url,
                headers={"Authorization": f"Bearer {slot.key}"},
                json=body,
            )
        except httpx.HTTPError as error:
            slot.cooldown_until = time.monotonic() + 5
            raise LLMError(f"network:{type(error).__name__}") from error
        self._track(slot, response)
        if response.status_code == 429:
            retry = _seconds(response.headers.get("retry-after")) or 10.0
            slot.cooldown_until = time.monotonic() + min(retry, 90.0)
            raise LLMError("rate_limited")
        if response.status_code >= 400:
            # json_validate_failed etc: let the next model try.
            detail = response.text[:300].replace("\n", " ")
            if response.status_code >= 500:
                slot.cooldown_until = time.monotonic() + 10
            raise LLMError(f"http_{response.status_code}:{detail}")
        try:
            data = response.json()
            content = data["choices"][0]["message"].get("content") or ""
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError) as error:
            raise LLMError("bad_response") from error
        if not content.strip():
            raise LLMError("empty_response")
        if json_mode:
            try:
                json.loads(_strip_fences(content))
            except ValueError as error:
                raise LLMError("invalid_json") from error
        return Completion(
            content=_strip_fences(content) if json_mode else content.strip(),
            model=slot.label,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            seconds=round(time.monotonic() - started, 2),
        )

    @staticmethod
    def _track(slot: ModelSlot, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining-tokens")
        if remaining is not None:
            try:
                slot.remaining_tokens = int(float(remaining))
                reset = _seconds(response.headers.get("x-ratelimit-reset-tokens"))
                slot.tokens_reset_at = time.monotonic() + reset
            except ValueError:
                pass

    def status(self) -> list[dict]:
        now = time.monotonic()
        return [
            {
                "model": s.label,
                "cooling_down": now < s.cooldown_until,
                "remaining_tokens": s.remaining_tokens
                if now < s.tokens_reset_at
                else None,
            }
            for s in self.slots.values()
        ]

    async def aclose(self):
        await self._client.aclose()


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text
