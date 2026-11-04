"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI

from backend.api.health import router as health_router
from backend.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name)
    app.include_router(health_router)
    return app


app = create_app()
