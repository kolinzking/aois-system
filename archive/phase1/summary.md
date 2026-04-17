# Phase 1 — The Intelligence Core
## Summary at Close

---

## What Phase 1 Built
A production-grade log analysis API.
Send any infrastructure log. Get back structured incident analysis — severity, summary, action, confidence.
Routed across multiple LLM providers with cost tracking and guaranteed valid output.

---

## The Three Versions

### v1 — The Foundation
**Core idea:** one endpoint, Claude as brain, OpenAI as fallback.

What it introduced:
- FastAPI as the web layer
- Anthropic SDK called directly — tool use to force structured output
- Anthropic's native prompt caching (`cache_control: ephemeral`) — system prompt costs 10% after first call
- OpenAI SDK as fallback via JSON prompt engineering
- Pydantic model for output shape: summary, severity, suggested_action, confidence

The weakness: two providers meant two separate code paths.
Adding a third would mean writing more if/else. Not scalable.

---

### v2 — The Routing Layer
**Core idea:** stop calling providers directly. One interface, any model.

What it introduced:
- LiteLLM replaces both SDKs — one `litellm.completion()` call routes anywhere
- ROUTING_TIERS dict: premium (Claude) → standard (GPT-4o-mini) → fast (Groq) → local (Ollama)
- Tool definition moved to OpenAI format — LiteLLM translates per provider
- `provider` and `cost_usd` added to every response
- Tiered fallback: if requested tier fails, try standard before returning 503

The cost reality this revealed:
- Claude (premium): ~$0.012 per call
- GPT-4o-mini (standard): ~$0.000083 per call
- That is a 150x cost difference — routing decisions are infrastructure decisions

The weakness: no output validation guarantee.
If the LLM returned malformed JSON or a bad severity value, the call crashed.

---

### v3 — Reliable Intelligence
**Core idea:** make output failures impossible to reach the caller.

What it introduced:
- Instructor wraps LiteLLM — builds tool definition from the Pydantic model automatically
- `Literal["P1","P2","P3","P4"]` on severity — Pydantic rejects anything outside those values
- `ge=0.0, le=1.0` on confidence — bounds enforced at the type level
- `max_retries=2` — if the LLM returns invalid output, Instructor feeds the error back and retries
- Langfuse callback — two lines, every call traced to a dashboard automatically
- `Field(description=...)` on each field — descriptions become part of the LLM prompt

What was removed: the ANALYZE_TOOL dict, `json.loads()`, manual tool_call parsing.
The Pydantic model became the single source of truth for the output schema.

---

## How the Versions Relate

```
v1: Claude SDK ──────────────────────────────► structured output (Anthropic tool use)
         └── OpenAI SDK (fallback)

v2: LiteLLM ─────────────────────────────────► structured output (OpenAI tool format)
         └── ROUTING_TIERS [premium, standard, fast, local]
         └── cost_usd + provider on every response

v3: Instructor(LiteLLM) ─────────────────────► validated + retried structured output
         └── Pydantic model IS the schema
         └── Langfuse traces everything
```

Each version kept everything the previous built and added one focused layer.
The API shape (LogInput → IncidentAnalysis) never changed.
The routing tiers from v2 carried forward untouched into v3.

---

## What Phase 1 Leaves Behind for Phase 2

Going into Phase 2 (containerisation and security), AOIS is:
- A working FastAPI service with one endpoint: POST /analyze
- Routing across 4 tiers (premium, standard, fast, local)
- Validated output with automatic retry
- Observable via Langfuse when keys are provided
- Running locally via uvicorn

What it is not yet:
- Containerised — no Dockerfile, cannot be deployed
- Secured — no rate limiting, no input sanitisation, no prompt injection defence
- Scannable — no Trivy, no image signing, no SBOM
- Secrets-managed — API keys in a flat .env file

Phase 2 fixes all of that.

---

## Files in This Archive

```
archive/phase1/
├── v1/
│   ├── main.py     frozen v1 code — direct Anthropic + OpenAI SDKs
│   └── notes.md    line-by-line explanation of v1
├── v2/
│   ├── main.py     frozen v2 code — LiteLLM routing layer
│   └── notes.md    line-by-line explanation of v2
├── v3/
│   ├── main.py     frozen v3 code — Instructor + Langfuse
│   └── notes.md    line-by-line explanation of v3
└── summary.md      this file — phase overview
```
