from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .agent import LiveTranslationAgent
from .config import get_settings
from .logging_utils import get_logger, setup_logging

setup_logging()
settings = get_settings()
log = get_logger('app', component='app')
agent = LiveTranslationAgent()
app = FastAPI(redirect_slashes=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
@app.post('/health')
async def health_check():
    return {
        'status': 'healthy',
        'agent': agent.get_name(),
        'route': agent.route,
        'functions': len(agent._tool_registry._swaig_functions),
    }


@app.get('/api-status')
@app.post('/api-status')
async def api_status():
    """Health check endpoint for external probes."""
    return {'status': 'ok', 'healthy': True}


@app.get('/ready')
@app.post('/ready')
async def readiness_check():
    return {
        'status': 'ready',
        'agent': agent.get_name(),
        'route': agent.route,
        'functions': len(agent._tool_registry._swaig_functions),
    }


@app.get('/status')
@app.post('/status')
async def status():
    """Alias for /api-status for convenience."""
    return {'status': 'ok', 'healthy': True}


app.include_router(agent.as_router(), prefix=agent.route)


LAML_REDIRECT = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Response>\n  <Redirect method=\"POST\">/sip</Redirect>\n</Response>\n"""


@app.get('/laml')
@app.post('/laml')
async def laml_entry():
    return Response(content=LAML_REDIRECT, media_type='application/xml')


@app.get('/sip')
@app.post('/sip')
async def sip_entry(request: Request):
    return await agent._handle_root_request(request)


@app.on_event('startup')
async def startup_event() -> None:
    log.info(
        'application_starting',
        extra={
            'environment': settings.environment,
            'port': settings.port,
            'default_source_language': settings.default_source_language,
            'default_target_language': settings.default_target_language,
            'inbound_entrypoint': '/',
        },
    )
