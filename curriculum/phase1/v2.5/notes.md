# v2.5 — AI Gateway: The Control Plane Around LLM Routing

⏱ **Estimated time: 5–7 hours**

---

## Prerequisites

v2 LiteLLM gateway working. Redis and Postgres running via Docker Compose.

```bash
# LiteLLM routes correctly across tiers
python3 test.py
# ✓ claude tier: 200 OK, cost logged
# ✓ groq tier: 200 OK, cost logged

# Redis is reachable
redis-cli ping
# PONG

# Postgres is reachable
psql $DATABASE_URL -c "SELECT version();" | head -1
# PostgreSQL 15.x ...

# Docker Compose stack is healthy
docker compose ps --format "table {{.Name}}\t{{.Status}}"
# aois          running
# redis         running
# postgres      running
```

---

## Learning Goals

By the end you will be able to:

- Explain why a routing layer (LiteLLM) and a control plane (AI Gateway) are different concerns
- Build a FastAPI gateway that enforces per-team budget limits using Redis counters
- Detect and redact PII from prompts before they leave your network
- Implement semantic caching so identical or near-identical prompts return cached responses
- Write an immutable audit log of every LLM call to Postgres
- Apply per-key rate limits independently from per-user budget limits
- Explain what happens in each failure mode: budget exhausted, cache miss, PII detected, rate limit hit

---

## The Problem This Solves

In v2 you built model routing: Claude for P1/P2, Groq for volume. That solves *which model gets called*. It does not solve:

- **Cost spiral**: a team's agent loop burns $200 in one night because nothing enforced a limit
- **Data leakage**: a log line containing a user's email or SSN goes into an OpenAI training pipeline
- **Wasted spend**: the same analysis runs 50 times because different callers do not know the result is cached
- **Accountability gap**: an LLM gave bad advice, but there is no record of exactly what prompt was sent and what was returned

Every enterprise that moves from "dev experiment" to "production AI" hits all four of these within the first month. The AI Gateway is the layer that addresses them — built once, enforced across every caller.

The mental model: **LiteLLM is the router. The AI Gateway is the control plane around the router.** The gateway decides whether to let a request through, transform it, serve it from cache, and log the result. LiteLLM is what the gateway calls when it decides to proceed.

```
Caller (kafka/consumer.py, main.py, agent)
    ↓
AI Gateway  ← rate limit, budget check, PII redact, cache lookup
    ↓ (cache miss, within budget)
LiteLLM Proxy  ← model routing (Claude, Groq, Bedrock, Ollama)
    ↓
LLM API (Claude, Groq, etc.)
    ↓
AI Gateway  ← cache write, audit log, budget debit
    ↓
Caller
```

---

## Architecture Decisions

### Budget Storage: Redis

Per-user and per-team spending counters live in Redis. Why Redis and not Postgres?

- Counters need atomic increment: `INCRBYFLOAT user:alice:cost_usd 0.016` — Redis is built for this
- Budget checks happen on every request: Redis latency is <1ms; Postgres is 5-15ms
- TTLs are natural: `EXPIRE team:platform:cost_usd 86400` resets the daily budget automatically

Budget enforcement in Postgres would require a SELECT then UPDATE inside a transaction on every request — serializable isolation to avoid races, high lock contention, and a 10-15ms overhead per call. Redis INCR is atomic by design.

### Semantic Cache: Redis + Hash

For exact caching: `SHA256(model + system_prompt + user_message)` → response.

For semantic (near-identical) caching: generate an embedding of the user message, store in Redis, query by cosine similarity threshold. Near-identical prompts ("OOMKilled pod exit 137" vs "pod killed OOMKilled exit code 137") return the same cached analysis.

In v2.5 you will implement exact caching (SHA256 hash). Semantic/embedding-based caching appears in v3.5 alongside RAG. Exact caching alone reduces costs by 30-50% in production systems with repeated patterns.

### Audit Log: Postgres

Every LLM call gets one immutable row:
- `request_id` (UUID)
- `api_key_id`
- `user_id` / `team_id`
- `model`
- `prompt_hash` (SHA256 of the full prompt — not the plaintext, for privacy)
- `response_hash`
- `input_tokens`, `output_tokens`, `cost_usd`
- `latency_ms`
- `cache_hit` (bool)
- `pii_detected` (bool)
- `created_at`

Why store hashes and not plaintext? Audit logs answer "who called what model at what cost" — not "what exactly did they write". The hash allows deduplication (find repeated prompts) without storing personal data. If you need the plaintext for debugging, it is in the caller's logs — not in a queryable audit table that every analyst can access.

### PII Detection: Regex + Heuristics

Production PII detection uses ML models (Microsoft Presidio, AWS Comprehend). For v2.5 you will use regex patterns covering the most common cases:

- Email: `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`
- SSN: `\d{3}-\d{2}-\d{4}`
- Credit card: `\b(?:\d{4}[-\s]?){3}\d{4}\b`
- IP address: `\b(?:\d{1,3}\.){3}\d{1,3}\b`
- UK National Insurance: `[A-Z]{2}\d{6}[A-Z]`
- Phone (E.164): `\+?1?\s?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}`

Detected PII is replaced with `[REDACTED_EMAIL]`, `[REDACTED_SSN]`, etc. before the prompt leaves the gateway. The redaction map is not stored (replaced labels are sufficient for the LLM to reason about the incident).

This is not a complete PII solution — it is a defense-in-depth layer. Medical record numbers, internal employee IDs, and contextual PII (names that appear in a specific context) require ML-based detection. The regex layer catches the obvious structural patterns that commonly appear in SRE logs.

---

## Building the Gateway

### Database Schema

First, create the audit log table. This goes in the Postgres instance from your Docker Compose stack.

```bash
psql $DATABASE_URL <<'SQL'
CREATE TABLE IF NOT EXISTS llm_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    request_id      UUID NOT NULL DEFAULT gen_random_uuid(),
    api_key_id      TEXT NOT NULL,
    user_id         TEXT,
    team_id         TEXT,
    model           TEXT NOT NULL,
    prompt_hash     TEXT NOT NULL,
    response_hash   TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        NUMERIC(10, 8),
    latency_ms      INTEGER,
    cache_hit       BOOLEAN NOT NULL DEFAULT FALSE,
    pii_detected    BOOLEAN NOT NULL DEFAULT FALSE,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_api_key ON llm_audit_log(api_key_id, created_at DESC);
CREATE INDEX idx_audit_team ON llm_audit_log(team_id, created_at DESC);
CREATE INDEX idx_audit_model ON llm_audit_log(model, created_at DESC);
SQL
# CREATE TABLE
# CREATE INDEX
# CREATE INDEX
# CREATE INDEX
```

Also create the budget configuration table:

```bash
psql $DATABASE_URL <<'SQL'
CREATE TABLE IF NOT EXISTS budget_config (
    id              SERIAL PRIMARY KEY,
    entity_type     TEXT NOT NULL,  -- 'team' or 'user'
    entity_id       TEXT NOT NULL,
    daily_limit_usd NUMERIC(10, 4) NOT NULL,
    monthly_limit_usd NUMERIC(10, 4),
    alert_threshold NUMERIC(4, 3) DEFAULT 0.8,  -- alert at 80% of limit
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_type, entity_id)
);

-- seed some test data
INSERT INTO budget_config (entity_type, entity_id, daily_limit_usd, monthly_limit_usd)
VALUES
    ('team', 'platform',  5.00,  100.00),
    ('team', 'security',  2.00,   40.00),
    ('user', 'alice',     1.00,   20.00),
    ('user', 'bob',       0.50,   10.00)
ON CONFLICT DO NOTHING;
SQL
# CREATE TABLE
# INSERT 0 4
```

### PII Redaction Module

```python
# gateway/pii.py
import re
from dataclasses import dataclass, field

@dataclass
class RedactionResult:
    text: str
    detections: list[str] = field(default_factory=list)

    @property
    def pii_detected(self) -> bool:
        return len(self.detections) > 0

_PATTERNS = [
    ("EMAIL",    re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')),
    ("SSN",      re.compile(r'\b\d{3}-\d{2}-\d{4}\b')),
    ("CC",       re.compile(r'\b(?:\d{4}[\-\s]?){3}\d{4}\b')),
    ("PHONE",    re.compile(r'\+?1?\s?(?:\(\d{3}\)|\d{3})[\-.\s]?\d{3}[\-.\s]?\d{4}')),
    ("IP",       re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b')),
    ("NI",       re.compile(r'\b[A-Z]{2}\d{6}[A-Z]\b')),
]

def redact(text: str) -> RedactionResult:
    result = text
    detections: list[str] = []
    for label, pattern in _PATTERNS:
        if pattern.search(result):
            detections.append(label)
            result = pattern.sub(f"[REDACTED_{label}]", result)
    return RedactionResult(text=result, detections=detections)
```

### Semantic Cache Module

```python
# gateway/cache.py
import hashlib
import json
import redis.asyncio as aioredis
import os

_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 hour default

def _cache_key(model: str, system: str, user: str) -> str:
    payload = json.dumps({"model": model, "system": system, "user": user},
                         sort_keys=True)
    return "aois:cache:" + hashlib.sha256(payload.encode()).hexdigest()

async def get_cached(redis: aioredis.Redis, model: str, system: str, user: str) -> str | None:
    key = _cache_key(model, system, user)
    return await redis.get(key)

async def set_cached(redis: aioredis.Redis, model: str, system: str, user: str,
                     response: str) -> None:
    key = _cache_key(model, system, user)
    await redis.setex(key, _TTL_SECONDS, response)

async def cache_stats(redis: aioredis.Redis) -> dict:
    keys = await redis.keys("aois:cache:*")
    return {"cached_responses": len(keys), "ttl_seconds": _TTL_SECONDS}
```

### Budget Enforcement Module

```python
# gateway/budget.py
import redis.asyncio as aioredis
import asyncpg
import os
from datetime import date

_DAILY_PREFIX   = "aois:budget:daily"
_MONTHLY_PREFIX = "aois:budget:monthly"

def _daily_key(entity_type: str, entity_id: str) -> str:
    today = date.today().isoformat()
    return f"{_DAILY_PREFIX}:{entity_type}:{entity_id}:{today}"

def _monthly_key(entity_type: str, entity_id: str) -> str:
    month = date.today().strftime("%Y-%m")
    return f"{_MONTHLY_PREFIX}:{entity_type}:{entity_id}:{month}"

async def check_budget(redis: aioredis.Redis, db: asyncpg.Pool,
                       team_id: str, user_id: str) -> tuple[bool, str]:
    """Returns (allowed, reason). Checks team then user limits."""
    for entity_type, entity_id in [("team", team_id), ("user", user_id)]:
        if not entity_id:
            continue
        row = await db.fetchrow(
            "SELECT daily_limit_usd FROM budget_config WHERE entity_type=$1 AND entity_id=$2",
            entity_type, entity_id
        )
        if not row:
            continue
        limit = float(row["daily_limit_usd"])
        spent_raw = await redis.get(_daily_key(entity_type, entity_id))
        spent = float(spent_raw or 0)
        if spent >= limit:
            return False, f"{entity_type}:{entity_id} daily budget exhausted (${spent:.4f} / ${limit:.4f})"
    return True, "ok"

async def debit_budget(redis: aioredis.Redis, team_id: str, user_id: str,
                       cost_usd: float) -> None:
    """Atomically increments spend counters. TTL ensures daily/monthly auto-reset."""
    for entity_type, entity_id in [("team", team_id), ("user", user_id)]:
        if not entity_id:
            continue
        daily_key = _daily_key(entity_type, entity_id)
        await redis.incrbyfloat(daily_key, cost_usd)
        await redis.expire(daily_key, 86400)  # 24h TTL
        monthly_key = _monthly_key(entity_type, entity_id)
        await redis.incrbyfloat(monthly_key, cost_usd)
        await redis.expire(monthly_key, 32 * 86400)  # 32 days TTL

async def budget_status(redis: aioredis.Redis, db: asyncpg.Pool,
                        entity_type: str, entity_id: str) -> dict:
    row = await db.fetchrow(
        "SELECT daily_limit_usd, monthly_limit_usd FROM budget_config "
        "WHERE entity_type=$1 AND entity_id=$2",
        entity_type, entity_id
    )
    if not row:
        return {"entity": f"{entity_type}:{entity_id}", "status": "no budget configured"}
    daily_spent_raw  = await redis.get(_daily_key(entity_type, entity_id))
    monthly_spent_raw = await redis.get(_monthly_key(entity_type, entity_id))
    daily_spent   = float(daily_spent_raw or 0)
    monthly_spent = float(monthly_spent_raw or 0)
    daily_limit   = float(row["daily_limit_usd"])
    monthly_limit = float(row["monthly_limit_usd"] or 0)
    return {
        "entity": f"{entity_type}:{entity_id}",
        "daily":   {"spent": round(daily_spent, 6),   "limit": daily_limit,   "remaining": round(daily_limit - daily_spent, 6)},
        "monthly": {"spent": round(monthly_spent, 6), "limit": monthly_limit, "remaining": round(monthly_limit - monthly_spent, 6)},
    }
```

### Audit Log Module

```python
# gateway/audit.py
import asyncpg
import hashlib
import time
import uuid

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

async def log_call(db: asyncpg.Pool, *, api_key_id: str, user_id: str, team_id: str,
                   model: str, prompt: str, response: str | None, input_tokens: int,
                   output_tokens: int, cost_usd: float, latency_ms: int,
                   cache_hit: bool, pii_detected: bool, error: str | None) -> str:
    request_id = str(uuid.uuid4())
    await db.execute("""
        INSERT INTO llm_audit_log
          (request_id, api_key_id, user_id, team_id, model,
           prompt_hash, response_hash, input_tokens, output_tokens, cost_usd,
           latency_ms, cache_hit, pii_detected, error)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
    """,
        request_id, api_key_id, user_id, team_id, model,
        _hash(prompt),
        _hash(response) if response else None,
        input_tokens, output_tokens, cost_usd,
        latency_ms, cache_hit, pii_detected, error
    )
    return request_id
```

---

## ▶ STOP — do this now

Before the gateway app, verify the database setup:

```bash
psql $DATABASE_URL -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public';"
#   table_name
# ─────────────────
#  llm_audit_log
#  budget_config
# (2 rows)

psql $DATABASE_URL -c "SELECT entity_type, entity_id, daily_limit_usd FROM budget_config;"
#  entity_type │ entity_id │ daily_limit_usd
# ─────────────┼───────────┼─────────────────
#  team        │ platform  │            5.00
#  team        │ security  │            2.00
#  user        │ alice     │            1.00
#  user        │ bob       │            0.50
```

If the table does not exist, re-run the SQL block above. If `gen_random_uuid()` fails, your Postgres version is below 13 — use `uuid_generate_v4()` after enabling the `uuid-ossp` extension: `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`.

---

### The Gateway Application

```python
# gateway/gateway.py
"""
AI Gateway — sits between callers and the LiteLLM proxy.
Enforces: rate limits, budget checks, PII redaction, semantic cache, audit log.
Run: uvicorn gateway.gateway:app --port 8001 --reload
"""
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Literal
import redis.asyncio as aioredis
import asyncpg
import litellm
import os
import time
import logging
from dotenv import load_dotenv

from .pii    import redact
from .cache  import get_cached, set_cached, cache_stats
from .budget import check_budget, debit_budget, budget_status
from .audit  import log_call

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gateway")

app = FastAPI(title="AOIS AI Gateway", version="2.5")

# ---------------------------------------------------------------------------
# State — Redis and Postgres pools initialised at startup
# ---------------------------------------------------------------------------
_redis: aioredis.Redis | None = None
_db:    asyncpg.Pool   | None = None

SYSTEM_PROMPT = """You are AOIS, an expert SRE AI assistant.
Analyze the provided log or alert and return a JSON object with:
  summary, severity (P1-P4), suggested_action, confidence (0-1)."""

# Cost per 1M tokens (approximate, updated manually when pricing changes)
_COST_PER_1M = {
    "claude-haiku-4-5-20251001": {"in": 0.80,  "out": 4.00},
    "claude-sonnet-4-6":         {"in": 3.00,  "out": 15.00},
    "groq/llama-3.1-8b-instant": {"in": 0.05,  "out": 0.08},
    "default":                   {"in": 1.00,  "out": 3.00},
}

def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _COST_PER_1M.get(model, _COST_PER_1M["default"])
    return (input_tokens * rates["in"] + output_tokens * rates["out"]) / 1_000_000

@app.on_event("startup")
async def startup():
    global _redis, _db
    _redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    _db    = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    log.info("Gateway: Redis and Postgres connected")

@app.on_event("shutdown")
async def shutdown():
    if _redis: await _redis.aclose()
    if _db:    await _db.close()

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class GatewayRequest(BaseModel):
    log:     str   = Field(..., min_length=1, max_length=5000)
    model:   str   = Field(default="claude-haiku-4-5-20251001")
    team_id: str   = Field(default="platform")
    user_id: str   = Field(default="")

class GatewayResponse(BaseModel):
    summary:          str
    severity:         Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence:       float
    model_used:       str
    cache_hit:        bool
    pii_detected:     bool
    cost_usd:         float
    latency_ms:       int
    request_id:       str

# ---------------------------------------------------------------------------
# Rate limiter — simple token bucket per API key in Redis
# ---------------------------------------------------------------------------
_RATE_LIMIT_RPM = int(os.getenv("GATEWAY_RATE_LIMIT_RPM", "60"))

async def _check_rate_limit(api_key: str) -> bool:
    key = f"aois:ratelimit:{api_key}:{int(time.time()) // 60}"
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, 60)
    return count <= _RATE_LIMIT_RPM

# ---------------------------------------------------------------------------
# Main gateway endpoint
# ---------------------------------------------------------------------------
@app.post("/v1/analyze", response_model=GatewayResponse)
async def analyze(
    req: GatewayRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    t0 = time.time()

    # 1. Rate limit
    if not await _check_rate_limit(x_api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # 2. Budget check
    allowed, reason = await check_budget(_redis, _db, req.team_id, req.user_id)
    if not allowed:
        raise HTTPException(status_code=402, detail=f"Budget exhausted: {reason}")

    # 3. PII redaction
    redacted = redact(req.log)
    clean_log = redacted.text
    if redacted.pii_detected:
        log.warning("PII detected and redacted: %s", redacted.detections)

    # 4. Cache lookup (exact match on redacted log + model)
    cached = await get_cached(_redis, req.model, SYSTEM_PROMPT, clean_log)
    if cached:
        import json
        data = json.loads(cached)
        latency_ms = int((time.time() - t0) * 1000)
        request_id = await log_call(
            _db,
            api_key_id=x_api_key[:8], user_id=req.user_id, team_id=req.team_id,
            model=req.model, prompt=clean_log, response=cached,
            input_tokens=0, output_tokens=0, cost_usd=0.0,
            latency_ms=latency_ms, cache_hit=True, pii_detected=redacted.pii_detected,
            error=None,
        )
        return GatewayResponse(**data, cache_hit=True, pii_detected=redacted.pii_detected,
                               cost_usd=0.0, latency_ms=latency_ms, request_id=request_id,
                               model_used=req.model)

    # 5. Call LLM via LiteLLM
    error_msg = None
    response_text = None
    input_tokens = output_tokens = 0
    cost_usd = 0.0

    try:
        response = await litellm.acompletion(
            model=req.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Analyze this log:\n\n{clean_log}"},
            ],
            max_tokens=512,
            temperature=0.1,
        )
        response_text  = response.choices[0].message.content
        input_tokens   = response.usage.prompt_tokens
        output_tokens  = response.usage.completion_tokens
        cost_usd       = _estimate_cost(req.model, input_tokens, output_tokens)
    except Exception as e:
        error_msg = str(e)
        log.error("LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")
    finally:
        latency_ms = int((time.time() - t0) * 1000)
        request_id = await log_call(
            _db,
            api_key_id=x_api_key[:8], user_id=req.user_id, team_id=req.team_id,
            model=req.model, prompt=clean_log, response=response_text,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
            latency_ms=latency_ms, cache_hit=False, pii_detected=redacted.pii_detected,
            error=error_msg,
        )

    # 6. Budget debit
    await debit_budget(_redis, req.team_id, req.user_id, cost_usd)

    # 7. Parse response and cache it
    import json, re
    analysis = {"summary": response_text, "severity": "P3",
                "suggested_action": "investigate", "confidence": 0.7}
    json_match = re.search(r'\{[^{}]+\}', response_text or "", re.DOTALL)
    if json_match:
        try:
            analysis = json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    cache_payload = json.dumps({**analysis, "model_used": req.model})
    await set_cached(_redis, req.model, SYSTEM_PROMPT, clean_log, cache_payload)

    return GatewayResponse(
        **analysis,
        model_used=req.model,
        cache_hit=False,
        pii_detected=redacted.pii_detected,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        request_id=request_id,
    )

# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------
@app.get("/v1/budget/{entity_type}/{entity_id}")
async def get_budget(entity_type: str, entity_id: str,
                     x_api_key: str = Header(..., alias="X-API-Key")):
    return await budget_status(_redis, _db, entity_type, entity_id)

@app.get("/v1/cache/stats")
async def get_cache_stats(x_api_key: str = Header(..., alias="X-API-Key")):
    return await cache_stats(_redis)

@app.get("/v1/audit/recent")
async def get_recent_audit(limit: int = 20,
                           x_api_key: str = Header(..., alias="X-API-Key")):
    rows = await _db.fetch("""
        SELECT request_id, api_key_id, team_id, model, cost_usd,
               latency_ms, cache_hit, pii_detected, error, created_at
        FROM llm_audit_log
        ORDER BY created_at DESC
        LIMIT $1
    """, limit)
    return [dict(r) for r in rows]

@app.get("/health")
async def health():
    await _redis.ping()
    await _db.fetchval("SELECT 1")
    return {"status": "healthy", "service": "ai-gateway"}
```

---

## ▶ STOP — do this now

Run the gateway and test each layer individually:

```bash
# Install asyncpg if not already present
pip install asyncpg redis

# Start the gateway (separate terminal)
uvicorn gateway.gateway:app --port 8001 --reload
# INFO: Uvicorn running on http://127.0.0.1:8001

# Test: basic call through the gateway
curl -s -X POST http://localhost:8001/v1/analyze \
  -H "X-API-Key: test-key-001" \
  -H "Content-Type: application/json" \
  -d '{"log":"pod OOMKilled exit code 137","team_id":"platform","user_id":"alice"}' | jq .
# {
#   "summary": "Pod terminated due to out-of-memory condition",
#   "severity": "P2",
#   "suggested_action": "increase memory limits or investigate memory leak",
#   "confidence": 0.92,
#   "model_used": "claude-haiku-4-5-20251001",
#   "cache_hit": false,
#   "pii_detected": false,
#   "cost_usd": 0.000042,
#   "latency_ms": 1243,
#   "request_id": "..."
# }

# Test: cache hit — same request, should return instantly
curl -s -X POST http://localhost:8001/v1/analyze \
  -H "X-API-Key: test-key-001" \
  -H "Content-Type: application/json" \
  -d '{"log":"pod OOMKilled exit code 137","team_id":"platform","user_id":"alice"}' | jq '{cache_hit,latency_ms,cost_usd}'
# {
#   "cache_hit": true,
#   "latency_ms": 3,    ← 3ms vs 1243ms — cache working
#   "cost_usd": 0       ← $0 for cached response
# }
```

---

## Testing PII Redaction

```bash
# Test: log containing an email address
curl -s -X POST http://localhost:8001/v1/analyze \
  -H "X-API-Key: test-key-001" \
  -H "Content-Type: application/json" \
  -d '{"log":"User john.doe@company.com triggered auth failure — IP 192.168.1.50","team_id":"security"}' | jq '{pii_detected,summary}'
# {
#   "pii_detected": true,
#   "summary": "Authentication failure for user [REDACTED_EMAIL] from [REDACTED_IP]"
# }

# Verify the redacted prompt was what reached the LLM (check gateway logs):
# INFO: PII detected and redacted: ['EMAIL', 'IP']
```

```python
# gateway/test_pii.py — run directly to verify all patterns
from gateway.pii import redact

cases = [
    ("user alice@corp.com failed login",                     ["EMAIL"]),
    ("payment card 4532-0151-1283-0000 declined",            ["CC"]),
    ("employee SSN 123-45-6789 in audit trail",              ["SSN"]),
    ("call from +1 (555) 867-5309 regarding incident",       ["PHONE"]),
    ("pod at 10.0.1.45 OOMKilled",                           ["IP"]),
    ("NI number AB123456C found in config",                  ["NI"]),
    ("disk pressure on node — no PII here",                  []),
]
for text, expected in cases:
    result = redact(text)
    status = "PASS" if set(result.detections) == set(expected) else "FAIL"
    print(f"{status}: {text[:45]!r} → detections={result.detections}")
```

```bash
python3 -m gateway.test_pii
# PASS: 'user alice@corp.com failed login'          → detections=['EMAIL']
# PASS: 'payment card 4532-0151-1283-0000 declined' → detections=['CC']
# PASS: 'employee SSN 123-45-6789 in audit trail'   → detections=['SSN']
# PASS: 'call from +1 (555) 867-5309 regarding i...' → detections=['PHONE']
# PASS: 'pod at 10.0.1.45 OOMKilled'                → detections=['IP']
# PASS: 'NI number AB123456C found in config'        → detections=['NI']
# PASS: 'disk pressure on node — no PII here'        → detections=[]
```

---

## Testing Budget Enforcement

```bash
# Check alice's current budget
curl -s http://localhost:8001/v1/budget/user/alice \
  -H "X-API-Key: test-key-001" | jq .
# {
#   "entity": "user:alice",
#   "daily": {"spent": 0.000042, "limit": 1.0, "remaining": 0.999958},
#   "monthly": {"spent": 0.000042, "limit": 20.0, "remaining": 19.999958}
# }

# Simulate exhausted budget in Redis
redis-cli SET "aois:budget:daily:user:alice:$(date +%Y-%m-%d)" 1.001
# OK

# Now the same request should be blocked
curl -s -X POST http://localhost:8001/v1/analyze \
  -H "X-API-Key: test-key-001" \
  -H "Content-Type: application/json" \
  -d '{"log":"disk pressure","team_id":"platform","user_id":"alice"}' | jq .
# {
#   "detail": "Budget exhausted: user:alice daily budget exhausted ($1.0010 / $1.0000)"
# }

# Clean up test budget
redis-cli DEL "aois:budget:daily:user:alice:$(date +%Y-%m-%d)"
# (integer) 1
```

---

## Querying the Audit Log

After running several requests through the gateway, query the audit log to confirm it is recording correctly:

```sql
-- Recent calls with cost breakdown
SELECT
    request_id,
    team_id,
    model,
    input_tokens,
    output_tokens,
    ROUND(cost_usd::numeric, 8) AS cost_usd,
    latency_ms,
    cache_hit,
    pii_detected,
    created_at
FROM llm_audit_log
ORDER BY created_at DESC
LIMIT 10;
```

```bash
psql $DATABASE_URL -c "
SELECT team_id, model, COUNT(*) as calls,
       SUM(cost_usd) as total_cost,
       ROUND(AVG(latency_ms)) as avg_latency_ms,
       SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
       SUM(CASE WHEN pii_detected THEN 1 ELSE 0 END) as pii_hits
FROM llm_audit_log
GROUP BY team_id, model
ORDER BY total_cost DESC;
"
#  team_id  │          model           │ calls │ total_cost │ avg_latency_ms │ cache_hits │ pii_hits
# ───────────┼──────────────────────────┼───────┼────────────┼────────────────┼────────────┼──────────
#  platform  │ claude-haiku-4-5-...     │     5 │ 0.00021    │           1156 │          4 │        1
#  security  │ claude-haiku-4-5-...     │     2 │ 0.00009    │           1089 │          0 │        1
```

The cache_hits:calls ratio tells you your cache hit rate. In AOIS with recurring log patterns (OOMKilled, CrashLoopBackOff, disk pressure), this rate climbs quickly. 4 cache hits in 5 calls = 80% hit rate = 80% cost reduction on those calls.

---

## ▶ STOP — do this now

Run this audit query and answer:
1. What is your cache hit rate after 10 requests?
2. Was any PII detected? Which pattern triggered?
3. What is the total cost across all calls so far?

If cache_hits is 0 after identical requests, the cache key is not matching — add debug logging to `get_cached` to print the key being looked up.

---

## Wiring the Gateway into AOIS

The Kafka consumer (`kafka/consumer.py`) currently calls `main.py`'s `analyze()` directly as a Python import. To route through the gateway:

```python
# In kafka/consumer.py — replace direct analyze() call with gateway HTTP call
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8001")
GATEWAY_KEY = os.getenv("GATEWAY_API_KEY", "internal-consumer-key")

async def analyze_via_gateway(log_text: str, tier: str = "groq") -> dict:
    model = "groq/llama-3.1-8b-instant" if tier in ("fast", "volume") else "claude-haiku-4-5-20251001"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{GATEWAY_URL}/v1/analyze",
            headers={"X-API-Key": GATEWAY_KEY},
            json={"log": log_text, "model": model, "team_id": "platform"},
        )
        r.raise_for_status()
        return r.json()
```

When this is in place, every Kafka-consumed log goes through: rate check → budget check → PII redaction → cache lookup → LLM → audit log → budget debit. One control point for all callers.

---

## Common Mistakes

### 1. asyncpg vs psycopg2

The gateway uses `asyncpg` (async Postgres driver). It uses positional parameters (`$1`, `$2`) not the `%s` format used by psycopg2.

```python
# Wrong (psycopg2 style — will error with asyncpg)
await db.execute("INSERT INTO t VALUES (%s, %s)", (a, b))

# Correct (asyncpg style)
await db.execute("INSERT INTO t VALUES ($1, $2)", a, b)
```

---

### 2. Redis INCRBYFLOAT rounding

`INCRBYFLOAT` in Redis returns a string. When comparing to a budget limit:

```python
# Wrong — comparing string to float always True
spent = await redis.get(key)
if spent >= limit:  # "0.000042" >= 1.0 → TypeError or True depending on Python version

# Correct
spent = float(await redis.get(key) or 0)
if spent >= limit:
```

---

### 3. Cache key collision across models

If you forget to include `model` in the cache key, a cached Groq response can be returned for a Claude request. The response format may differ (Groq returns plainer text without JSON structure), breaking the response parser.

Always include model in the key:
```python
# The cache key must encode model + system + user to prevent cross-model collisions
payload = json.dumps({"model": model, "system": system, "user": user}, sort_keys=True)
```

---

### 4. Audit log blocking the response

The audit log INSERT should not block the response to the caller. In the current implementation it is `await`ed inside `finally:` — this is correct because it runs after the LLM returns and before the function returns. It does not add to the user-perceived latency of the LLM call.

If you move it outside `finally`, a database error would result in an unlogged call — you lose the audit trail for that request. Keep it in `finally`.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'gateway'`

Run the gateway as a package from the project root:

```bash
# From /home/collins/aois-system/:
uvicorn gateway.gateway:app --port 8001 --reload
# NOT: cd gateway && uvicorn gateway:app
```

The `gateway/` directory needs `__init__.py`:

```bash
touch /home/collins/aois-system/gateway/__init__.py
```

---

### Budget check returns `no budget configured` for known team

```bash
psql $DATABASE_URL -c "SELECT * FROM budget_config WHERE entity_id='platform';"
# (0 rows)
```

The INSERT ... ON CONFLICT DO NOTHING ran before the UNIQUE constraint was created. Drop and re-run:

```bash
psql $DATABASE_URL -c "TRUNCATE budget_config; INSERT INTO budget_config ..."
```

---

### Gateway returns 502 when LiteLLM is not running

The gateway calls LiteLLM directly via `litellm.acompletion` — it does not require a separate LiteLLM proxy process. The LiteLLM library is imported and used inline. If you get 502, the API key is missing or the model name is wrong:

```bash
# Check API keys are in .env and loaded
grep -E "ANTHROPIC|GROQ" .env
# ANTHROPIC_API_KEY=sk-ant-...
# GROQ_API_KEY=gsk_...
```

---

## Connection to Later Phases

### To v3.5 (RAG)
The exact cache in v2.5 matches on identical prompts. v3.5 adds semantic (embedding-based) caching where similar prompts (same incident, slightly different wording) hit the cache. The `get_cached`/`set_cached` interface in `gateway/cache.py` is designed to accept a drop-in replacement that queries a vector store instead of a hash key.

### To v20 (Claude Tool Use + Agent Memory)
In v20, AOIS gets tools. Each agent step calls the LLM multiple times — the budget enforcement in v2.5 becomes the mechanism that prevents agent cost spirals. Per-incident cost attribution (tracked via `team_id`/`user_id` fields + a future `incident_id` field) is the foundation for the CLAUDE.md-noted requirement: "investigating this OOMKilled cost $0.04 across 12 LLM calls."

### To v21.5 (MCP Security)
The API key enforcement in the gateway (`X-API-Key` header, rate limit per key) is the same pattern as MCP OAuth authorization. The audit log is the per-tool-call trace that v21.5 requires. Building it now means Phase 7 has a working control plane to build on.

### To v23.5 (Agent Evaluation)
The audit log enables post-hoc analysis: for every agent run, retrieve all LLM calls by `request_id` chain, reconstruct the decision trace, compare to ground truth. Without the audit log, agent evaluation requires expensive re-running of scenarios.

---

## Mastery Checkpoint

1. Start the gateway and confirm `/health` returns `{"status":"healthy"}`. Confirm both Redis and Postgres connections succeed (health check tests both).

2. Send the same log analysis request three times through the gateway. On requests 2 and 3, verify `cache_hit: true` and `latency_ms` is under 10ms. Explain why the first call is never cached.

3. Send a log containing an email address and an IP address. Verify `pii_detected: true` in the response. Query the audit log and confirm `pii_detected = true` is stored. Confirm the email does not appear in the `prompt_hash` field (it is a hash, not plaintext).

4. Set a team's daily budget to $0.001 in Redis, send two requests. Confirm the first succeeds and the second returns HTTP 402 with the budget exhausted message. Reset the budget counter and confirm the third request succeeds.

5. Send 61 requests in under 60 seconds (use a loop). Confirm request 61 returns HTTP 429. Explain the token bucket mechanism and why the rate limit resets at the start of the next minute.

6. Query the audit log and compute the cache hit rate, total cost, and average latency for your test session. Are these numbers consistent with what the gateway response fields showed?

7. Explain to a non-technical person why the gateway stores a hash of the prompt rather than the prompt text itself.

8. Explain to a junior engineer the difference between rate limiting (request frequency) and budget enforcement (total spend). Give one scenario where an attacker could bypass rate limiting but not budget enforcement, and vice versa.

9. Explain to a senior engineer why Redis is the right choice for budget counters but wrong for the audit log. What would break if you swapped them — budgets to Postgres, audit log to Redis?

**The mastery bar:** you can add a new caller (a new team, a new API key, a new rate limit) to the gateway without touching the LLM routing code, and confirm enforcement is working from the audit log and budget status endpoints alone.

---

## 4-Layer Tool Understanding

### AI Gateway

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Without a gateway, every team that calls an LLM does so without limits, without audit, and with no protection against accidentally sending personal data. The gateway enforces: "you can spend this much, at this rate, and nothing sensitive leaves the building." |
| **System Role** | Where does it sit in AOIS? | Between every caller (Kafka consumer, main.py, future agents) and LiteLLM. No caller reaches the LLM directly — all traffic goes through the gateway, which enforces policy and records every call. |
| **Technical** | What is it, precisely? | A FastAPI service that wraps LLM calls with Redis-backed rate limits and budget counters, SHA256-based exact response caching, regex PII redaction, and an immutable Postgres audit log. It uses `litellm.acompletion` internally for model routing. |
| **Remove it** | What breaks, and how fast? | Remove the gateway → callers hit the LLM directly. PII reaches external APIs immediately. Cost spirals have no circuit breaker. Cache layer disappears — repeated prompts cost full price every time. Audit trail gone — no way to answer "who spent what, when, on what model". Discovery: you notice the spend increase in your Anthropic dashboard billing, days later. |

### Semantic Cache

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | If you ask the same question 50 times, you should only pay for it once. The cache stores the answer and returns it instantly for every repeat, saving both money and latency. |
| **System Role** | Where does it sit in AOIS? | Inside the AI Gateway, before the LiteLLM call. Every request is checked against the cache first. Cache hits cost $0 and respond in <5ms. Cache misses proceed to the LLM and the response is stored for future hits. |
| **Technical** | What is it, precisely? | A Redis key-value store where the key is `SHA256(model + system_prompt + user_message)` and the value is the serialized JSON response. TTL is 1 hour by default (configurable). Exact matching only — semantically similar but textually different prompts are cache misses in v2.5. |
| **Remove it** | What breaks, and how fast? | Remove the cache → every repeated incident analysis (same OOMKilled log pattern appearing hourly) hits the LLM. In a production SRE system with repetitive log patterns, this can multiply costs by 5–10x. Latency also increases — every request waits for a full LLM round trip. |
