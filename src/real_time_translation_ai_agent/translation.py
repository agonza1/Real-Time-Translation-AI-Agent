from __future__ import annotations

from typing import Any, Dict, Optional
import httpx


class TranslationRouter:
    def __init__(self, webhook_url: Optional[str] = None, auth_header: Optional[str] = None) -> None:
        self.webhook_url = webhook_url
        self.auth_header = auth_header

    def route_translation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.webhook_url:
            return {
                'mode': 'local-fallback',
                'decision': 'translate',
                'target_language': payload.get('target_language'),
                'source_language': payload.get('source_language'),
                'message': (
                    f"Routing call for live translation from {payload.get('source_language_label')} "
                    f"to {payload.get('target_language_label')}."
                ),
            }

        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        if self.auth_header:
            key, _, value = self.auth_header.partition(':')
            if key and value:
                headers[key.strip()] = value.strip()

        with httpx.Client(timeout=15.0) as client:
            response = client.post(self.webhook_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError('Translation webhook must return a JSON object')
            return data
