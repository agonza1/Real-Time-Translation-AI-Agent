# Real-Time-Translation-AI-Agent

Real-time translation AI agent orchestrator built with Python, `uv`, FastAPI, and the SignalWire Agents SDK.

## What this MVP does

- exposes a SignalWire-compatible agent endpoint
- answers incoming calls through SignalWire Agents SDK
- confirms source and target languages
- triggers a translation-routing tool (`route_translation_call`)
- optionally forwards routing decisions to your own translation webhook/orchestrator
- exposes health and metadata endpoints for local testing

## Architecture

SignalWire handles telephony, media, and AI runtime plumbing.
This app focuses on orchestration:

1. SignalWire sends the incoming call to this agent.
2. The agent gathers or confirms translation intent.
3. The `route_translation_call` tool decides how to route translation.
4. The tool either:
   - uses a local fallback decision, or
   - POSTs to `TRANSLATION_WEBHOOK_URL` for custom orchestration.

## Quick start

```bash
uv sync
cp .env.example .env
uv run python -m real_time_translation_ai_agent.main
```

Server defaults to `http://localhost:3000`.

Useful endpoints:

- `GET /health`
- `GET /ready`
- `GET /` → SWML document (basic auth required)
- `POST /swaig` → SWAIG tool calls (basic auth required)

## Environment variables

At minimum, set:

- `OPENAI_API_KEY` or another LLM provider key supported by your SignalWire setup
- `SIGNALWIRE_SPACE`
- `SIGNALWIRE_PROJECT`
- `SIGNALWIRE_TOKEN`

Optional:

- `SWML_BASIC_AUTH_USER` and `SWML_BASIC_AUTH_PASSWORD` for the SignalWire-facing endpoints
- `TRANSLATION_WEBHOOK_URL` to hand routing off to your own orchestration service
- `PUBLIC_BASE_URL` if you want a stable externally reachable URL
- language defaults for the first demo

## Example local tool call

```bash
curl -s http://localhost:3000/swaig \
  -u signalwire:dev-password-change-me \
  -H 'content-type: application/json' \
  -d '{
    "function": "route_translation_call",
    "argument": {"raw": "{\"source_language\":\"en-US\",\"target_language\":\"es-ES\"}"}
  }' | jq
```

## Next recommended steps

- wire this endpoint to a SignalWire number / context
- add a real translation webhook implementation
- persist call/session state
- add transcript logging and demo UI
- record an end-to-end demo once credentials are loaded
