from __future__ import annotations

from typing import Any, Dict, Optional
import httpx

from .logging_utils import get_logger
from .models import TranslationDecision, TranslationRequest


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
