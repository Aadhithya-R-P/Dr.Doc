"""Assemble the API and expose its server entry point."""

from fastapi import FastAPI

from app.config import Settings
from app.routes.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.settings = settings
    application.include_router(health_router)
    return application


app = create_app()
