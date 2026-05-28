#!/usr/bin/env python3
"""Local contract smoke test for the SignalWire translation agent.

This intentionally avoids external SignalWire/ngrok calls. It validates the app contract
that has broken during live tests: health, SDK SWML entrypoints, LaML speech loop,
public callback URL rewriting, and SWAIG argument parsing.
"""
from __future__ import annotations

import json
import os
import sys

os.environ["OPENAI_API_KEY"] = ""
from collections.abc import Iterable
from typing import Any

from fastapi.testclient import TestClient

from real_time_translation_ai_agent.app import app
from real_time_translation_ai_agent.config import get_settings
from real_time_translation_ai_agent.translation import TranslationRouter

PUBLIC_BASE = "https://contract-smoke.ngrok-free.app"
PUBLIC_HOST = "contract-smoke.ngrok-free.app"


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
    elif isinstance(value, str):
        yield value


def assert_ok(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def get_json_swml(client: TestClient, path: str = "/") -> dict[str, Any]:
    response = client.get(
        path,
        headers={
            "host": PUBLIC_HOST,
            "x-forwarded-host": PUBLIC_HOST,
            "x-forwarded-proto": "https",
        },
    )
    assert_ok(response.status_code == 200, f"{path} returned {response.status_code}: {response.text[:300]}")
    assert_ok("application/json" in response.headers.get("content-type", ""), f"{path} did not return JSON")
    return response.json()


def assert_public_urls(swml: dict[str, Any], label: str) -> None:
    urls = [item for item in iter_strings(swml) if item.startswith("http")]
    assert_ok(urls, f"{label} SWML did not include any absolute callback URLs")
    bad_urls = [url for url in urls if not url.startswith(PUBLIC_BASE)]
    assert_ok(not bad_urls, f"{label} SWML had non-public callback URLs: {bad_urls}")
    assert_ok(any("/swaig" in url or "/post_prompt" in url for url in urls), f"{label} SWML missing SDK callback URLs")


def assert_route_response(payload: dict[str, Any], expected_target: str) -> None:
    response = CLIENT.post("/swaig", json=payload)
    assert_ok(response.status_code == 200, f"/swaig returned {response.status_code}: {response.text[:300]}")
    body = response.json()
    body_text = json.dumps(body)
    assert_ok(expected_target in body_text, f"/swaig response did not include target {expected_target}: {body}")
    assert_ok("set_global_data" in body_text, f"/swaig response did not set global translation data: {body}")


CLIENT = TestClient(app)


def main() -> int:
    health = CLIENT.get("/health")
    assert_ok(health.status_code == 200, f"/health returned {health.status_code}")
    assert_ok(health.json().get("status") == "healthy", f"unexpected /health body: {health.text}")

    root_swml = get_json_swml(CLIENT, "/")
    assert_public_urls(root_swml, "root")

    sip_swml = get_json_swml(CLIENT, "/sip")
    assert_public_urls(sip_swml, "sip")

    laml = CLIENT.post(
        "/laml",
        headers={
            "host": PUBLIC_HOST,
            "x-forwarded-host": PUBLIC_HOST,
            "x-forwarded-proto": "https",
        },
    )
    assert_ok(laml.status_code == 200, f"/laml returned {laml.status_code}")
    assert_ok("application/xml" in laml.headers.get("content-type", ""), "/laml did not return XML")
    assert_ok('<Gather input="speech"' in laml.text, f"/laml missing speech gather: {laml.text}")
    assert_ok(f'action="{PUBLIC_BASE}/laml/translate"' in laml.text, f"/laml missing public translate action: {laml.text}")

    laml_translate = CLIENT.post(
        "/laml/translate",
        data={"SpeechResult": "I need help with my reservation", "CallSid": "smoke-call"},
        headers={
            "host": PUBLIC_HOST,
            "x-forwarded-host": PUBLIC_HOST,
            "x-forwarded-proto": "https",
        },
    )
    assert_ok(laml_translate.status_code == 200, f"/laml/translate returned {laml_translate.status_code}: {laml_translate.text}")
    assert_ok("Necesito ayuda con mi reservacion." in laml_translate.text, f"unexpected /laml/translate body: {laml_translate.text}")
    assert_ok(f"{PUBLIC_BASE}/laml" in laml_translate.text, f"/laml/translate missing public redirect: {laml_translate.text}")
    assert_route_response(
        {
            "function": "route_translation_call",
            "argument": {"raw": '{"source_language":"en-US","target_language":"es-ES"}'},
        },
        "es-ES",
    )
    assert_route_response(
        {
            "function": "route_translation_call",
            "argument": {"parsed": [{"target_language": "fr-FR", "target_language_label": "French"}]},
        },
        "fr-FR",
    )

    deterministic_translation = CLIENT.post(
        "/api/translate",
        json={
            "text": "I need help with my reservation.",
            "source_language": "en-US",
            "target_language": "es-ES",
            "source_language_label": "English",
            "target_language_label": "Spanish",
            "session_id": "smoke-session",
        },
    )
    assert_ok(deterministic_translation.status_code == 200, f"/api/translate returned {deterministic_translation.status_code}")
    deterministic_body = deterministic_translation.json()
    assert_ok(deterministic_body["provider"] == "deterministic-fallback", f"unexpected provider: {deterministic_body}")
    assert_ok(deterministic_body["translated_text"] == "Necesito ayuda con mi reservacion.", f"unexpected deterministic translation: {deterministic_body}")
    assert_ok(deterministic_body["fallback_used"] is False, f"expected phrasebook match: {deterministic_body}")

    split_translation = CLIENT.post(
        "/api/translate",
        json={
            "text": "I need help",
            "source_language": "en-US",
            "target_language": "es-ES",
            "source_language_label": "English",
            "target_language_label": "Spanish",
            "session_id": "smoke-session",
        },
    )
    assert_ok(split_translation.status_code == 200, f"/api/translate split returned {split_translation.status_code}")
    split_body = split_translation.json()
    assert_ok(split_body["translated_text"] == "Necesito ayuda.", f"unexpected split translation: {split_body}")

    swaig_translation = CLIENT.post(
        "/swaig",
        json={
            "function": "translate_spoken_text",
            "argument": {"parsed": [{"text": "I need help"}]},
            "call_id": "smoke-call",
            "ai_session_id": "smoke-session",
        },
    )
    assert_ok(swaig_translation.status_code == 200, f"/swaig translate returned {swaig_translation.status_code}")
    swaig_body = swaig_translation.json()
    assert_ok(swaig_body.get("response") == "Necesito ayuda.", f"/swaig translate missing response: {swaig_body}")
    assert_ok({"say": "Necesito ayuda."} in swaig_body.get("action", []), f"/swaig translate missing say action: {swaig_body}")

    fallback_translation = CLIENT.post(
        "/api/translate",
        json={
            "text": "Please transfer me to billing.",
            "source_language": "en-US",
            "target_language": "es-ES",
            "source_language_label": "English",
            "target_language_label": "Spanish",
        },
    )
    assert_ok(fallback_translation.status_code == 200, f"/api/translate fallback returned {fallback_translation.status_code}")
    fallback_body = fallback_translation.json()
    assert_ok(fallback_body["fallback_used"] is True, f"expected fallback path: {fallback_body}")
    assert_ok(fallback_body["translated_text"] == "[Spanish] Please transfer me to billing.", f"unexpected fallback translation: {fallback_body}")

    demo_session = CLIENT.post(
        "/api/demo/session",
        json={
            "transport": "pstn",
            "source_language": "en-US",
            "target_language": "es-ES",
            "source_language_label": "English",
            "target_language_label": "Spanish",
        },
        headers={
            "host": PUBLIC_HOST,
            "x-forwarded-host": PUBLIC_HOST,
            "x-forwarded-proto": "https",
        },
    )
    assert_ok(demo_session.status_code == 200, f"/api/demo/session returned {demo_session.status_code}")
    demo_session_body = demo_session.json()
    assert_ok(demo_session_body["transport"] == "pstn", f"unexpected demo session transport: {demo_session_body}")
    assert_ok(demo_session_body["call_webhook_url"] == f"{PUBLIC_BASE}/sip", f"unexpected demo call webhook: {demo_session_body}")
    assert_ok(len(demo_session_body["instructions"]) >= 4, f"expected demo instructions: {demo_session_body}")

    live_call = CLIENT.post(
        "/api/demo/live-call",
        json={
            "transport": "webrtc",
            "source_language": "en-US",
            "target_language": "es-ES",
            "source_language_label": "English",
            "target_language_label": "Spanish",
            "turns": [
                {"speaker": "caller", "text": "hello"},
                {"speaker": "caller", "text": "Please transfer me to billing."},
                {"speaker": "callee", "text": "hola"},
            ],
        },
    )
    assert_ok(live_call.status_code == 200, f"/api/demo/live-call returned {live_call.status_code}")
    live_call_body = live_call.json()
    assert_ok(live_call_body["transport"] == "webrtc", f"unexpected demo live-call transport: {live_call_body}")
    assert_ok(live_call_body["metadata"]["turn_count"] == 3, f"unexpected live-call turn count: {live_call_body}")
    assert_ok(live_call_body["transcript"][0]["translated_text"] == "Hola.", f"unexpected first translated turn: {live_call_body}")
    assert_ok(live_call_body["transcript"][1]["fallback_used"] is True, f"expected fallback in second turn: {live_call_body}")
    assert_ok(live_call_body["transcript"][2]["translated_text"] == "Hello.", f"unexpected reverse translation: {live_call_body}")

    import real_time_translation_ai_agent.translation as translation_module

    class FakeOpenAIResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "Por favor transferirme a facturacion."}
                        ],
                    }
                ]
            }

    class FakeOpenAIClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> "FakeOpenAIClient":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeOpenAIResponse:
            assert_ok(url == "https://api.openai.com/v1/responses", f"unexpected OpenAI URL: {url}")
            assert_ok(headers.get("Authorization") == "Bearer test-openai-key", "missing OpenAI auth header")
            assert_ok("Please transfer me to billing." in json["input"], "source text missing from OpenAI prompt")
            return FakeOpenAIResponse()

    original_client = translation_module.httpx.Client
    try:
        os.environ["OPENAI_API_KEY"] = "test-openai-key"
        get_settings.cache_clear()
        translation_module.httpx.Client = FakeOpenAIClient
        openai_translation = TranslationRouter().translate_turn(
            {
                "text": "Please transfer me to billing.",
                "source_language": "en-US",
                "target_language": "es-ES",
                "source_language_label": "English",
                "target_language_label": "Spanish",
            }
        )
    finally:
        translation_module.httpx.Client = original_client
        os.environ["OPENAI_API_KEY"] = ""
        get_settings.cache_clear()

    assert_ok(openai_translation["provider"] == "openai-responses", f"unexpected OpenAI provider: {openai_translation}")
    assert_ok(openai_translation["fallback_used"] is False, f"OpenAI translation should not be fallback: {openai_translation}")
    assert_ok(
        openai_translation["translated_text"] == "Por favor transferirme a facturacion.",
        f"unexpected OpenAI translated text: {openai_translation}",
    )

    print("translation agent contract smoke test passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - executable smoke test should print clean failure
        print(f"translation agent contract smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
