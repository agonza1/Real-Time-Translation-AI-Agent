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


class TranslationTurnRequest(BaseModel):
    text: str = Field(min_length=1)
    source_language: str = Field(default='en-US')
    target_language: str = Field(default='es-ES')
    source_language_label: str = Field(default='English')
    target_language_label: str = Field(default='Spanish')
    call_id: Optional[str] = None
    session_id: Optional[str] = None
    provider: str = Field(default='auto')
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranslationTurnResponse(BaseModel):
    provider: str
    fallback_used: bool = False
    source_text: str
    translated_text: str
    source_language: str
    target_language: str
    source_language_label: str
    target_language_label: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
