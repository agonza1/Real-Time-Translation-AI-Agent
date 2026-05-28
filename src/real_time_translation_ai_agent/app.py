from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .agent import LiveTranslationAgent
from .config import get_settings
from .logging_utils import get_logger, setup_logging
from .models import DemoSessionRequest, DemoSimulationRequest, TranslationTurnRequest

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


@app.post('/api/translate')
async def translate_turn(payload: TranslationTurnRequest):
    return agent.translation_router.translate_turn(payload.model_dump())


@app.post('/api/demo/session')
async def demo_session(payload: DemoSessionRequest, request: Request):
    public_base_url = (
        request.headers.get('x-forwarded-proto', 'http')
        + '://'
        + (request.headers.get('x-forwarded-host') or request.headers.get('host') or f'localhost:{settings.port}')
    )
    return agent.translation_router.build_demo_session(payload.model_dump(), public_base_url)


@app.post('/api/demo/live-call')
async def demo_live_call(payload: DemoSimulationRequest):
    return agent.translation_router.simulate_live_call(payload.model_dump())


app.include_router(agent.as_router(), prefix=agent.route)


def _public_base_url(request: Request) -> str:
    return (
        request.headers.get('x-forwarded-proto', 'http')
        + '://'
        + (request.headers.get('x-forwarded-host') or request.headers.get('host') or f'localhost:{settings.port}')
    ).rstrip('/')


def _laml_response(body: str) -> Response:
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n{body}\n</Response>\n',
        media_type='application/xml',
    )


@app.get('/laml')
@app.post('/laml')
async def laml_entry(request: Request):
    base = _public_base_url(request)
    action_url = escape(f'{base}/laml/translate')
    log.info('laml_entry', extra={'action_url': action_url})
    return _laml_response(
        f'  <Say voice="woman" language="en-US">Welcome to the English to Spanish translation line. Say a phrase in English after the beep.</Say>\n'
        f'  <Gather input="speech" action="{action_url}" method="POST" speechTimeout="auto" timeout="7" language="en-US">\n'
        f'    <Say voice="woman" language="en-US">Please speak now.</Say>\n'
        f'  </Gather>\n'
        f'  <Say voice="woman" language="en-US">I did not hear anything. Please try again.</Say>\n'
        f'  <Redirect method="POST">{escape(f"{base}/laml")}</Redirect>'
    )


@app.get('/laml/translate')
@app.post('/laml/translate')
async def laml_translate(request: Request):
    content_type = (request.headers.get('content-type') or '').lower()
    if 'application/json' in content_type:
        payload = await request.json()
        form = payload if isinstance(payload, dict) else {}
    else:
        body = (await request.body()).decode('utf-8', errors='replace')
        parsed = parse_qs(body)
        form = {key: values[0] for key, values in parsed.items() if values}
    spoken_text = str(form.get('SpeechResult') or form.get('speech_result') or '').strip()
    call_id = str(form.get('CallSid') or form.get('call_id') or '')
    if not spoken_text:
        log.info('laml_translate_empty', extra={'call_id': call_id})
        return _laml_response(
            '  <Say voice="woman" language="en-US">I did not catch that. Please try again.</Say>\n'
            f'  <Redirect method="POST">{escape(_public_base_url(request) + "/laml")}</Redirect>'
        )

    translation = agent.translation_router.translate_turn(
        {
            'text': spoken_text,
            'source_language': settings.default_source_language,
            'target_language': settings.default_target_language,
            'source_language_label': settings.default_source_label,
            'target_language_label': settings.default_target_label,
            'session_id': call_id or None,
            'call_id': call_id or None,
        }
    )
    translated_text = translation.get('translated_text') or spoken_text
    log.info(
        'laml_translate',
        extra={'call_id': call_id, 'spoken_text': spoken_text, 'translated_text': translated_text},
    )
    return _laml_response(
        f'  <Say voice="woman" language="es-ES">{escape(translated_text)}</Say>\n'
        f'  <Redirect method="POST">{escape(_public_base_url(request) + "/laml")}</Redirect>'
    )


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
