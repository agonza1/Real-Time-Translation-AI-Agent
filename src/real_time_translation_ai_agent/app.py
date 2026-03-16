from __future__ import annotations

from fastapi import FastAPI, Request, Response

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


# Bypass SDK catch-all auth path for demo use: expose / and /swaig directly.
@app.get('/')
async def public_root(request: Request):
    return await agent._handle_root_request(request)


@app.post('/')
async def public_root_post(request: Request):
    return await agent._handle_root_request(request)


@app.post('/swaig')
@app.post('/swaig/')
async def public_swaig(request: Request):
    return await agent._handle_swaig_request(request, Response())
