"""FastAPI application factory and ASGI entry point."""

import asyncio

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.ask import AskResponse, error_message, response_language
from backend.api.ask import router as ask_router
from backend.api.database import router as database_router
from backend.api.health import router as health_router
from backend.config import Settings, get_settings
from backend.database.adapter import DuckDBAdapter
from backend.database.service import DatabaseService
from backend.interpretation import Interpreter
from backend.query import QueryEngine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    app = FastAPI(
        title=settings.app_name,
        docs_url=None if settings.production else "/docs",
        redoc_url=None if settings.production else "/redoc",
        openapi_url=None if settings.production else "/openapi.json",
    )
    app.state.settings = settings

    @app.exception_handler(RequestValidationError)
    async def invalid_question(request, error):
        if request.url.path != "/api/ask":
            return await request_validation_exception_handler(request, error)
        body = error.body if isinstance(error.body, dict) else {}
        question = body.get("question", "")
        override = body.get("language", "auto")
        language = response_language(
            question if isinstance(question, str) else "",
            override if isinstance(override, str) else "auto",
        )
        result = AskResponse(
            language=language,
            status="error",
            error="invalid_input",
            answer=error_message(language, "invalid_input"),
        )
        return JSONResponse(status_code=422, content=result.model_dump(mode="json"))

    app.state.interpreter = Interpreter(settings)
    app.state.query_engine = QueryEngine(settings)
    app.state.ask_slots = asyncio.Semaphore(settings.ask_max_concurrent)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            allow_credentials=False,
        )
    app.state.database_service = DatabaseService(
        DuckDBAdapter(settings), settings.database_metadata_max_columns
    )
    app.include_router(ask_router)
    app.include_router(health_router)
    app.include_router(database_router)
    return app


app = create_app()
