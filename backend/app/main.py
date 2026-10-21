"""Assemble the API and expose its server entry point."""

from fastapi import FastAPI

from app.config import Settings
from app.routes.health import router as health_router
from app.routes.documents import router as documents_router
from app.routes.questions import router as questions_router
from app.upload_limits import UploadLimitsMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.settings = settings
    application.include_router(health_router)
    application.include_router(documents_router)
    application.include_router(questions_router)
    application.add_middleware(UploadLimitsMiddleware)
    return application


app = create_app()
