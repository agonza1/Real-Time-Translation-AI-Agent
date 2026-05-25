from __future__ import annotations

from typing import Any, Dict, Optional
import httpx

from .logging_utils import get_logger
from .models import (
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
    normalized = request.text.strip().lower()
    phrasebook = PHRASEBOOK.get((request.source_language, request.target_language), {})
    translated = phrasebook.get(normalized)
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
