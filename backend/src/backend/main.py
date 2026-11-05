"""FastAPI application factory and ASGI entry point."""

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
