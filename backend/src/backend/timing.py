"""Safe stage timings: generated IDs and numbers, never request/provider content."""

import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

logger = logging.getLogger("uvicorn.error")
request_id = ContextVar("timing_request_id", default="-")


@contextmanager
def timing(stage: str, *, request: bool = False, attempt: int | None = None):
    token = request_id.set(uuid4().hex[:12]) if request else None
    started = time.perf_counter()
    try:
        yield
    finally:
        fields = {
            "event": "latency",
            "stage": stage,
            "request_id": request_id.get(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        if attempt is not None:
            fields["attempt"] = attempt
        logger.info(json.dumps(fields))
        if token is not None:
            request_id.reset(token)


def cooldown_skip():
    logger.info(
        json.dumps(
            {
                "event": "latency",
                "stage": "groq",
                "request_id": request_id.get(),
                "duration_ms": 0,
                "skipped": True,
                "reason": "cooldown",
            }
        )
    )
