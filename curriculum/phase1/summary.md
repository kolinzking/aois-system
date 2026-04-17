# Phase 1 — The Intelligence Core

## What was built
A log analysis API. Send any infrastructure log, get back structured incident data:
severity (P1–P4), summary, suggested action, confidence score.

## Versions
- **v1** — FastAPI + Claude (primary) + OpenAI (fallback). Direct SDK calls. Prompt caching active.
- **v2** — LiteLLM routing layer. Four tiers: premium, standard, fast, local. Cost tracked per call.
- **v3** — Instructor wraps LiteLLM. Output guaranteed valid via Pydantic. Langfuse traces every call.

## State at close
Single endpoint: `POST /analyze`. Runs locally on port 8000.
Routes across Claude, GPT-4o-mini, Groq, Ollama. Output always validated. Observable when Langfuse keys present.

## What Phase 2 picks up
The API works but cannot be deployed. No Dockerfile, no secrets management, no security hardening. Phase 2 fixes that.
