"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI

from backend.api.database import router as database_router
from backend.api.health import router as health_router
from backend.config import Settings, get_settings
from backend.database.adapter import DuckDBAdapter
from backend.database.service import DatabaseService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    app = FastAPI(title=settings.app_name)
    app.state.settings = settings
    app.state.database_service = DatabaseService(
        DuckDBAdapter(settings), settings.database_metadata_max_columns
    )
    app.include_router(health_router)
    app.include_router(database_router)
    return app


app = create_app()
