from __future__ import annotations

from typing import Any, Dict, Optional

from signalwire_agents import AgentBase
from signalwire_agents.core.function_result import SwaigFunctionResult

from .config import get_settings
from .logging_utils import get_logger
from .translation import TranslationRouter


class LiveTranslationAgent(AgentBase):
    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            name='live-translation-agent',
            route='/',
            host=settings.host,
            port=settings.port,
            basic_auth=(settings.swml_basic_auth_user, settings.swml_basic_auth_password),
            use_pom=True,
            suppress_logs=not settings.debug,
        )

        self.settings = settings
        self.logx = get_logger('live_translation_agent', component='agent')
        self.translation_router = TranslationRouter(
            webhook_url=settings.translation_webhook_url,
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
                'use the route_translation_call tool. If the request is ambiguous, ask a short clarifying question.'
            ),
        )
        self.prompt_add_section(
            'Defaults',
            (
                f"Default source language: {settings.default_source_label} ({settings.default_source_language}). "
                f"Default target language: {settings.default_target_label} ({settings.default_target_language})."
            ),
        )

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

        self.logx.info(
            'agent_initialized',
            extra={
                'default_source_language': settings.default_source_language,
                'default_target_language': settings.default_target_language,
                'use_local_webhook': settings.use_local_webhook,
            },
        )

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
