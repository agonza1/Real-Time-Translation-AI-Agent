from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TranslationRequest(BaseModel):
    source_language: str = Field(default='en-US')
    target_language: str = Field(default='es-ES')
    source_language_label: str = Field(default='English')
    target_language_label: str = Field(default='Spanish')
    caller_number: Optional[str] = None
    call_id: Optional[str] = None
    signalwire_context: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranslationDecision(BaseModel):
    mode: str = 'local-webhook'
    decision: str = 'translate'
    source_language: str
    target_language: str
    source_language_label: str
    target_language_label: str
    target_leg: str = 'B'
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
