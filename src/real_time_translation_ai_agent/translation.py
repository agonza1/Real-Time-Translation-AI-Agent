from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4
import httpx

from .config import get_settings
from .logging_utils import get_logger
from .models import (
    DemoSessionDescriptor,
    DemoSessionRequest,
    DemoSimulationRequest,
    DemoSimulationResponse,
    TranslationDecision,
    TranslationRequest,
    TranslationTurnRequest,
    TranslationTurnResponse,
)


class TranslationRouter:
    def __init__(self, webhook_url: Optional[str] = None, auth_header: Optional[str] = None) -> None:
        self.webhook_url = webhook_url
        self.auth_header = auth_header
        self.log = get_logger('translation_router', component='translation-router')

    def route_translation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = TranslationRequest(**payload)

        if not self.webhook_url:
            self.log.info(
                'using_internal_local_webhook_logic',
                extra={
                    'source_language': request.source_language,
                    'target_language': request.target_language,
                    'call_id': request.call_id,
                },
            )
            return local_webhook_decision(request.model_dump())

        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        if self.auth_header:
            key, _, value = self.auth_header.partition(':')
            if key and value:
                headers[key.strip()] = value.strip()

        self.log.info(
            'calling_external_translation_webhook',
            extra={
                'webhook_url': self.webhook_url,
                'source_language': request.source_language,
                'target_language': request.target_language,
                'call_id': request.call_id,
            },
        )
        with httpx.Client(timeout=15.0) as client:
            response = client.post(self.webhook_url, json=request.model_dump(), headers=headers)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError('Translation webhook must return a JSON object')
            decision = TranslationDecision(**data)
            self.log.info(
                'external_translation_webhook_responded',
                extra={
                    'decision': decision.decision,
                    'target_leg': decision.target_leg,
                    'call_id': request.call_id,
                },
            )
            return decision.model_dump()

    def translate_turn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = TranslationTurnRequest(**payload)

        if self.webhook_url:
            translated = self._call_external_translation_turn(request)
            if translated is not None:
                return translated.model_dump()

        translated = self._call_openai_translation_turn(request)
        if translated is not None:
            return translated.model_dump()

        response = local_translate_turn(request.model_dump())
        self.log.info(
            'using_deterministic_translation_fallback',
            extra={
                'source_language': request.source_language,
                'target_language': request.target_language,
                'call_id': request.call_id,
                'session_id': request.session_id,
            },
        )
        return response

    def _call_openai_translation_turn(self, request: TranslationTurnRequest) -> TranslationTurnResponse | None:
        settings = get_settings()
        if not settings.openai_api_key:
            return None

        source_label = request.source_language_label or request.source_language
        target_label = request.target_language_label or request.target_language
        prompt = (
            f'Translate the following {source_label} speech into {target_label}. '
            'Return only the translated text, with no labels, quotes, commentary, or alternatives. '
            'Preserve the speaker intent and make it natural for a live phone interpreter.\n\n'
            f'Text: {request.text}'
        )
        body = {
            'model': settings.llm_model,
            'instructions': 'You are a real-time phone interpreter. Translate exactly what was said.',
            'input': prompt,
            'reasoning': {'effort': 'minimal'},
            'text': {'verbosity': 'low'},
            'max_output_tokens': 220,
        }
        headers = {
            'Authorization': f'Bearer {settings.openai_api_key}',
            'Content-Type': 'application/json',
        }

        try:
            with httpx.Client(timeout=12.0) as client:
                response = client.post('https://api.openai.com/v1/responses', json=body, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - phone demo should degrade instead of dropping call flow
            self.log.warning(
                'openai_translation_turn_failed',
                extra={
                    'call_id': request.call_id,
                    'session_id': request.session_id,
                    'model': settings.llm_model,
                    'error': str(exc),
                },
            )
            return None

        translated_text = _extract_openai_response_text(data)
        if not translated_text:
            self.log.warning(
                'openai_translation_turn_invalid_payload',
                extra={
                    'call_id': request.call_id,
                    'session_id': request.session_id,
                    'model': settings.llm_model,
                    'status': data.get('status') if isinstance(data, dict) else None,
                },
            )
            return None

        self.log.info(
            'openai_translation_turn_succeeded',
            extra={
                'source_language': request.source_language,
                'target_language': request.target_language,
                'call_id': request.call_id,
                'session_id': request.session_id,
                'model': settings.llm_model,
            },
        )
        return TranslationTurnResponse(
            provider='openai-responses',
            fallback_used=False,
            source_text=request.text,
            translated_text=translated_text,
            source_language=request.source_language,
            target_language=request.target_language,
            source_language_label=request.source_language_label,
            target_language_label=request.target_language_label,
            metadata={
                'call_id': request.call_id,
                'session_id': request.session_id,
                'model': settings.llm_model,
                'mode': 'realtime-openai-translation',
            },
        )

    def _call_external_translation_turn(self, request: TranslationTurnRequest) -> TranslationTurnResponse | None:
        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        if self.auth_header:
            key, _, value = self.auth_header.partition(':')
            if key and value:
                headers[key.strip()] = value.strip()

        endpoint = self.webhook_url.rstrip('/') + '/translate'
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(endpoint, json=request.model_dump(), headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - fallback path is intentional for MVP reliability
            self.log.warning(
                'external_translation_turn_failed',
                extra={
                    'webhook_url': endpoint,
                    'call_id': request.call_id,
                    'session_id': request.session_id,
                    'error': str(exc),
                },
            )
            return None

        if not isinstance(data, dict):
            self.log.warning(
                'external_translation_turn_invalid_payload',
                extra={'webhook_url': endpoint, 'call_id': request.call_id},
            )
            return None

        return TranslationTurnResponse(**data)

    def build_demo_session(self, payload: Dict[str, Any], public_base_url: str) -> Dict[str, Any]:
        request = DemoSessionRequest(**payload)
        session_id = f"demo-{request.transport}-{uuid4().hex[:10]}"
        normalized_base = public_base_url.rstrip('/')
        descriptor = DemoSessionDescriptor(
            session_id=session_id,
            transport=request.transport,
            source_language=request.source_language,
            target_language=request.target_language,
            source_language_label=request.source_language_label,
            target_language_label=request.target_language_label,
            swml_url=f'{normalized_base}/',
            laml_url=f'{normalized_base}/laml',
            call_webhook_url=f'{normalized_base}/sip',
            translate_url=f'{normalized_base}/api/translate',
            instructions=_build_demo_instructions(request.transport, normalized_base),
            metadata={
                'caller_number': request.caller_number,
                'transport_profile': 'browser-demo' if request.transport == 'webrtc' else 'phone-number-demo',
            },
        )
        self.log.info(
            'demo_session_built',
            extra={
                'session_id': session_id,
                'transport': request.transport,
                'source_language': request.source_language,
                'target_language': request.target_language,
            },
        )
        return descriptor.model_dump()

    def simulate_live_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = DemoSimulationRequest(**payload)
        session_id = request.session_id or f"sim-{request.transport}-{uuid4().hex[:10]}"
        events: list[dict[str, Any]] = [
            {
                'type': 'call.started',
                'transport': request.transport,
                'session_id': session_id,
            },
            {
                'type': 'prompt.played',
                'transport': request.transport,
                'session_id': session_id,
                'text': (
                    f'Welcome to the {request.source_language_label} to '
                    f'{request.target_language_label} translation line.'
                ),
            },
        ]
        transcript: list[dict[str, Any]] = []

        for index, turn in enumerate(request.turns, start=1):
            target_language = request.target_language
            target_language_label = request.target_language_label
            source_language = request.source_language
            source_language_label = request.source_language_label
            if turn.speaker == 'callee':
                target_language = request.source_language
                target_language_label = request.source_language_label
                source_language = request.target_language
                source_language_label = request.target_language_label

            translation = TranslationTurnResponse(
                **self.translate_turn(
                    TranslationTurnRequest(
                        text=turn.text,
                        source_language=source_language,
                        target_language=target_language,
                        source_language_label=source_language_label,
                        target_language_label=target_language_label,
                        session_id=session_id,
                        metadata={'turn_index': index, 'speaker': turn.speaker, 'transport': request.transport},
                    ).model_dump()
                )
            )

            heard_event = {
                'type': f'{turn.speaker}.heard',
                'turn_index': index,
                'text': turn.text,
                'language': source_language,
            }
            translated_event = {
                'type': 'translation.emitted',
                'turn_index': index,
                'speaker': turn.speaker,
                'translated_text': translation.translated_text,
                'target_language': target_language,
                'provider': translation.provider,
                'fallback_used': translation.fallback_used,
            }
            events.extend([heard_event, translated_event])
            transcript.append(
                {
                    'turn_index': index,
                    'speaker': turn.speaker,
                    'source_text': turn.text,
                    'translated_text': translation.translated_text,
                    'source_language': source_language,
                    'target_language': target_language,
                    'provider': translation.provider,
                    'fallback_used': translation.fallback_used,
                }
            )

        response = DemoSimulationResponse(
            session_id=session_id,
            transport=request.transport,
            events=events,
            transcript=transcript,
            metadata={
                'turn_count': len(request.turns),
                'mode': 'demo-live-call-simulation',
            },
        )
        self.log.info(
            'demo_live_call_simulated',
            extra={
                'session_id': session_id,
                'transport': request.transport,
                'turn_count': len(request.turns),
            },
        )
        return response.model_dump()


def _extract_openai_response_text(data: Dict[str, Any]) -> str:
    output_text = data.get('output_text')
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    for item in data.get('output') or []:
        if not isinstance(item, dict):
            continue
        for content in item.get('content') or []:
            if not isinstance(content, dict):
                continue
            if content.get('type') == 'output_text' and isinstance(content.get('text'), str):
                parts.append(content['text'])
    return ' '.join(part.strip() for part in parts if part.strip()).strip()


def local_webhook_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    request = TranslationRequest(**payload)
    log = get_logger('local_webhook', component='local-webhook')

    decision = TranslationDecision(
        source_language=request.source_language,
        target_language=request.target_language,
        source_language_label=request.source_language_label,
        target_language_label=request.target_language_label,
        message=(
            f'Starting MVP live translation from '
            f'{request.source_language_label} to {request.target_language_label}.'
        ),
        metadata={
            'policy': 'mvp-default',
            'target_leg': 'B',
            'call_id': request.call_id,
        },
    )
    log.info(
        'computed_local_translation_decision',
        extra={
            'source_language': request.source_language,
            'target_language': request.target_language,
            'call_id': request.call_id,
        },
    )
    return decision.model_dump()


PHRASEBOOK: dict[tuple[str, str], dict[str, str]] = {
    ('en-US', 'es-ES'): {
        'hello': 'Hola.',
        'how are you?': 'Como estas?',
        'i need help': 'Necesito ayuda.',
        'with my reservation': 'con mi reservacion.',
        'with my reserve': 'con mi reservacion.',
        'reservation': 'reservacion.',
        'reserve': 'reservacion.',
        'i need help with my reservation': 'Necesito ayuda con mi reservacion.',
        'i need help with my reserve': 'Necesito ayuda con mi reservacion.',
        'i need help with my reservation.': 'Necesito ayuda con mi reservacion.',
        'where is the hospital?': 'Donde esta el hospital?',
        'please speak slowly.': 'Por favor habla despacio.',
    },
    ('es-ES', 'en-US'): {
        'hola': 'Hello.',
        'necesito ayuda con mi reservacion.': 'I need help with my reservation.',
        'donde esta el hospital?': 'Where is the hospital?',
        'por favor habla despacio.': 'Please speak slowly.',
    },
}


def local_translate_turn(payload: Dict[str, Any]) -> Dict[str, Any]:
    request = TranslationTurnRequest(**payload)
    normalized = ' '.join(request.text.strip().lower().split())
    phrasebook = PHRASEBOOK.get((request.source_language, request.target_language), {})
    translated = phrasebook.get(normalized) or phrasebook.get(normalized.rstrip('.!?'))
    fallback_used = translated is None
    if translated is None:
        translated = f"[{request.target_language_label}] {request.text.strip()}"

    response = TranslationTurnResponse(
        provider='deterministic-fallback',
        fallback_used=fallback_used,
        source_text=request.text,
        translated_text=translated,
        source_language=request.source_language,
        target_language=request.target_language,
        source_language_label=request.source_language_label,
        target_language_label=request.target_language_label,
        metadata={
            'call_id': request.call_id,
            'session_id': request.session_id,
            'phrasebook_match': not fallback_used,
            'mode': 'mvp-local-loop',
        },
    )
    return response.model_dump()


def _build_demo_instructions(transport: str, public_base_url: str) -> list[str]:
    common = [
        'Start the backend and confirm /health returns status=healthy.',
        f'Use {public_base_url}/api/demo/session to generate a fresh demo session descriptor.',
        f'Use {public_base_url}/api/demo/live-call to simulate multi-turn translation behavior before a live test.',
    ]
    if transport == 'pstn':
        return common + [
            f'Point the SignalWire phone number webhook to {public_base_url}/ or {public_base_url}/laml.',
            'Place a PSTN call and compare live behavior against the simulated transcript.',
        ]
    return common + [
        f'Use {public_base_url}/sip as the browser/WebRTC call entrypoint.',
        'Open a browser-based call client and compare live behavior against the simulated transcript.',
    ]
