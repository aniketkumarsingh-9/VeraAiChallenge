from __future__ import annotations

from fastapi import FastAPI
from datetime import datetime, timezone

from app import __version__
from app.application.service import ChallengeService
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.domain.conversation import ConversationEngine
from app.domain.engine import DecisionEngine
from app.persistence.database import Database
from app.persistence.repositories import ChallengeRepository



def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)
    started_at = datetime.now(tz=timezone.utc)
    database = Database(resolved_settings)
    database.create_tables()
    repository = ChallengeRepository(database.session_factory, suppression_days=resolved_settings.suppression_days)
    service = ChallengeService(repository, DecisionEngine(), ConversationEngine(), resolved_settings, started_at)

    app = FastAPI(title=resolved_settings.app_name, version=__version__)
    app.state.settings = resolved_settings
    app.state.started_at = started_at
    app.state.database = database
    app.state.repository = repository
    app.state.service = service

    app.include_router(router)
    app.include_router(router, prefix="/v1", include_in_schema=False)
    return app


app = create_app()
