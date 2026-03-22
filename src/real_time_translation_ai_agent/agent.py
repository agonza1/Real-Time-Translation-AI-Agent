from __future__ import annotations

from typing import Any, Dict, Optional
import json

from fastapi import Request, Response

from signalwire_agents import AgentBase
from signalwire_agents.core.function_result import SwaigFunctionResult

from .config import get_settings
from .logging_utils import get_logger
from .translation import TranslationRouter


class LiveTranslationAgent(AgentBase):
    def __init__(self) -> None:
        settings = get_settings()
        basic_auth = None
        if settings.swml_basic_auth_user and settings.swml_basic_auth_password:
            basic_auth = (settings.swml_basic_auth_user, settings.swml_basic_auth_password)

        super().__init__(
            name='live-translation-agent',
            route='/',
            host=settings.host,
            port=settings.port,
            basic_auth=basic_auth,
            use_pom=True,
            suppress_logs=not settings.debug,
        )

        self.settings = settings
        self.logx = get_logger('live_translation_agent', component='agent')
        webhook_url = None if settings.use_local_webhook else settings.translation_webhook_url
        self.translation_router = TranslationRouter(
            webhook_url=webhook_url,
            auth_header=settings.translation_webhook_auth_header,
        )

        self.prompt_add_section(
            'Role',
            (
                'You are a live call translation orchestrator. '
                'You help detect the caller translation need, confirm source and target languages, '
                'and trigger the translation routing workflow as quickly as possible.'
            ),
        )
        self.prompt_add_section(
            'Behavior',
            (
                'Be concise. Confirm languages clearly. If the user asks for translation, '
                'use the route_translation_call tool. If the request is ambiguous, ask a short clarifying question. '
                'Start speaking immediately when the call is answered with a short greeting and ask what language the caller needs.'
            ),
        )
        self.prompt_add_section(
            'Defaults',
            (
                f"Default source language: {settings.default_source_label} ({settings.default_source_language}). "
                f"Default target language: {settings.default_target_label} ({settings.default_target_language})."
            ),
        )

        self.set_params({
            'wait_for_user': False,
            'end_of_speech_timeout': 500,
        })

        self.add_language(
            name=settings.default_source_label,
            code=settings.default_source_language,
            voice=settings.default_voice,
            model=settings.llm_model,
        )
        self.add_language(
            name=settings.default_target_label,
            code=settings.default_target_language,
            voice=settings.default_voice,
            model=settings.llm_model,
        )
        self.set_post_prompt(
            'Hello, this is the live translation assistant. What language do you need today?'
        )

        self.logx.info(
            'agent_initialized',
            extra={
                'default_source_language': settings.default_source_language,
                'default_target_language': settings.default_target_language,
                'use_local_webhook': settings.use_local_webhook,
                'external_webhook_enabled': bool(webhook_url),
            },
        )

    def _build_webhook_url(self, endpoint: str, query_params=None):
        base = self.settings.public_base_url or getattr(self, '_proxy_url_base', None)
        if base:
            base = base.rstrip('/')
            endpoint = endpoint.strip('/')
            url = f"{base}/{endpoint}/"
            if query_params:
                from urllib.parse import urlencode
                url += '?' + urlencode(query_params)
            return url
        return super()._build_webhook_url(endpoint, query_params)

    def _check_basic_auth(self, request: Request) -> bool:
        return True

    async def _handle_root_request(self, request: Request):
        self._detect_proxy_from_request(request)
        settings = self.settings
        public_base = settings.public_base_url or getattr(self, '_proxy_url_base', None)
        if public_base:
            public_base = public_base.rstrip('/')
            self._proxy_url_base = public_base
        body = {}
        call_id = None
        if request.method == 'POST':
            raw_body = await request.body()
            if raw_body:
                try:
                    body = await request.json()
                except Exception:
                    body = {}
            call_id = body.get('call_id') if isinstance(body, dict) else None
            if not call_id and isinstance(body, dict) and 'call' in body:
                call_id = (body.get('call') or {}).get('call_id')
        else:
            call_id = request.query_params.get('call_id')

        modifications = None
        try:
            modifications = self.on_swml_request(body if isinstance(body, dict) else {}, None, request)
        except Exception:
            modifications = None

        test_swml = {
            'version': '1.0.0',
            'sections': {
                'main': [
                    {'answer': {}},
                    {'tts': {'text': 'Hello. This is a SignalWire audio test. If you can hear this, audio playback is working.'}},
                ]
            },
        }
        return Response(content=json.dumps(test_swml), media_type='application/json')

    async def _handle_swaig_request(self, request: Request, response: Response):
        self._detect_proxy_from_request(request)
        settings = self.settings
        public_base = settings.public_base_url or getattr(self, '_proxy_url_base', None)
        if public_base:
            public_base = public_base.rstrip('/')
            self._proxy_url_base = public_base
        try:
            body = await request.json()
        except Exception:
            body = {}

        function_name = body.get('function') if isinstance(body, dict) else None
        raw_argument = body.get('argument') if isinstance(body, dict) else None
        args = {}
        if isinstance(raw_argument, dict):
            raw = raw_argument.get('raw')
            if isinstance(raw, str):
                try:
                    args = json.loads(raw)
                except Exception:
                    args = {}
            else:
                args = raw_argument

        if function_name == 'startup_hook':
            result = self.startup_hook(args=args, raw_data=body if isinstance(body, dict) else {})
            return result.to_dict()

        if function_name == 'route_translation_call':
            result = self.route_translation_call(args=args, raw_data=body if isinstance(body, dict) else {})
            return result.to_dict()

        return {"error": f"Unknown function: {function_name}"}

    @AgentBase.tool(
        name='startup_hook',
        description='Runs when the call starts so the agent speaks first and begins interaction.',
        parameters={
            'type': 'object',
            'properties': {},
        },
    )
    def startup_hook(
        self,
        args: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> SwaigFunctionResult:
        result = SwaigFunctionResult('Hello, this is the live translation assistant. What language do you need today?')
        result.say('Hello, this is the live translation assistant. What language do you need today?')
        result.wait_for_user(enabled=True)
        result.set_end_of_speech_timeout(500)
        return result

    @AgentBase.tool(
        name='route_translation_call',
        description='Route an incoming call into the live translation workflow using the selected source and target languages.',
        parameters={
            'type': 'object',
            'properties': {
                'source_language': {'type': 'string'},
                'target_language': {'type': 'string'},
                'source_language_label': {'type': 'string'},
                'target_language_label': {'type': 'string'},
                'caller_number': {'type': 'string'},
                'call_id': {'type': 'string'},
            },
            'required': ['target_language'],
        },
    )
    def route_translation_call(
        self,
        args: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> SwaigFunctionResult:
        settings = self.settings
        args = args or {}
        payload: Dict[str, Any] = {
            'source_language': args.get('source_language') or settings.default_source_language,
            'target_language': args.get('target_language') or settings.default_target_language,
            'source_language_label': args.get('source_language_label') or settings.default_source_label,
            'target_language_label': args.get('target_language_label') or settings.default_target_label,
            'caller_number': args.get('caller_number'),
            'call_id': args.get('call_id') or (raw_data or {}).get('call_id'),
            'signalwire_context': settings.signalwire_context,
            'metadata': {
                'raw_data_present': bool(raw_data),
            },
        }

        self.logx.info(
            'routing_translation_call',
            extra={
                'source_language': payload['source_language'],
                'target_language': payload['target_language'],
                'call_id': payload['call_id'],
            },
        )

        decision = self.translation_router.route_translation(payload)
        message = decision.get('message') or (
            f"Starting live translation from {payload['source_language_label']} to {payload['target_language_label']}."
        )

        result = SwaigFunctionResult(message)
        result.add_action('set_global_data', {
            'translation_route': decision,
            'translation_source_language': payload['source_language'],
            'translation_target_language': payload['target_language'],
        })
        return result
