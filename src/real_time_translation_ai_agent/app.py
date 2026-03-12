from __future__ import annotations

from fastapi import FastAPI

from .agent import LiveTranslationAgent
from .config import get_settings
from .logging_utils import get_logger, setup_logging
from .models import TranslationRequest
from .translation import local_webhook_decision

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
            'use_local_webhook': settings.use_local_webhook,
        },
    )


@app.post('/internal/translation-webhook')
async def internal_translation_webhook(request: TranslationRequest):
    decision = local_webhook_decision(request.model_dump())
    log.info(
        'internal_translation_webhook_called',
        extra={
            'source_language': request.source_language,
            'target_language': request.target_language,
            'call_id': request.call_id,
        },
    )
    return decision


@app.get('/debug/config')
async def debug_config():
    return {
        'environment': settings.environment,
        'port': settings.port,
        'use_local_webhook': settings.use_local_webhook,
        'local_webhook_path': settings.local_webhook_path,
        'translation_webhook_url': settings.translation_webhook_url,
        'default_source_language': settings.default_source_language,
        'default_target_language': settings.default_target_language,
    }
