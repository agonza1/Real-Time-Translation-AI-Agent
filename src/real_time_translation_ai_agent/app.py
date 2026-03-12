from __future__ import annotations

from fastapi import FastAPI

from .agent import LiveTranslationAgent
from .config import get_settings
from .logging_utils import get_logger, setup_logging

setup_logging()
settings = get_settings()
log = get_logger('app', component='app')
agent = LiveTranslationAgent()
app: FastAPI = agent.get_app()


@app.on_event('startup')
async def startup_event() -> None:
    log.info(
        'application_starting',
        extra={
            'environment': settings.environment,
            'port': settings.port,
            'default_source_language': settings.default_source_language,
            'default_target_language': settings.default_target_language,
        },
    )
