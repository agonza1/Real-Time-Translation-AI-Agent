from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
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


class DemoSessionRequest(BaseModel):
    transport: Literal['webrtc', 'pstn'] = 'webrtc'
    source_language: str = Field(default='en-US')
    target_language: str = Field(default='es-ES')
    source_language_label: str = Field(default='English')
    target_language_label: str = Field(default='Spanish')
    caller_number: Optional[str] = None


class DemoSessionDescriptor(BaseModel):
    session_id: str
    transport: Literal['webrtc', 'pstn']
    source_language: str
    target_language: str
    source_language_label: str
    target_language_label: str
    swml_url: str
    laml_url: str
    call_webhook_url: str
    translate_url: str
    instructions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DemoTurn(BaseModel):
    speaker: Literal['caller', 'callee'] = 'caller'
    text: str = Field(min_length=1)


class DemoSimulationRequest(BaseModel):
    session_id: Optional[str] = None
    transport: Literal['webrtc', 'pstn'] = 'webrtc'
    source_language: str = Field(default='en-US')
    target_language: str = Field(default='es-ES')
    source_language_label: str = Field(default='English')
    target_language_label: str = Field(default='Spanish')
    turns: List[DemoTurn] = Field(default_factory=list)


class DemoSimulationResponse(BaseModel):
    session_id: str
    transport: Literal['webrtc', 'pstn']
    events: List[Dict[str, Any]] = Field(default_factory=list)
    transcript: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
