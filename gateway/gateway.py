"""
AI Gateway v2.5 — control plane around LLM routing.
Enforces: per-key rate limits, per-team/user budget limits, PII redaction,
exact response caching, and immutable audit logging.

Run: uvicorn gateway.gateway:app --port 8001 --reload
"""
import json
import logging
import os
import re
import time
from typing import Literal

import asyncpg
import litellm
import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .audit import log_call
from .budget import budget_status, check_budget, debit_budget
from .cache import cache_stats, get_cached, set_cached
from .pii import redact

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gateway")

app = FastAPI(title="AOIS AI Gateway", version="2.5")

_redis: aioredis.Redis | None = None
_db: asyncpg.Pool | None = None

SYSTEM_PROMPT = (
    "You are AOIS, an expert SRE AI assistant. "
    "Analyze the provided log or alert and return a JSON object with: "
    "summary, severity (P1-P4), suggested_action, confidence (0-1)."
)

_COST_PER_1M = {
    "claude-haiku-4-5-20251001": {"in": 0.80, "out": 4.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "groq/llama-3.1-8b-instant": {"in": 0.05, "out": 0.08},
    "default": {"in": 1.00, "out": 3.00},
}
_RATE_LIMIT_RPM = int(os.getenv("GATEWAY_RATE_LIMIT_RPM", "60"))


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _COST_PER_1M.get(model, _COST_PER_1M["default"])
    return (input_tokens * rates["in"] + output_tokens * rates["out"]) / 1_000_000


@app.on_event("startup")
async def startup() -> None:
    global _redis, _db
    _redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    _db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    log.info("Gateway: Redis and Postgres connected")


@app.on_event("shutdown")
async def shutdown() -> None:
    if _redis:
        await _redis.aclose()
    if _db:
        await _db.close()


class GatewayRequest(BaseModel):
    log: str = Field(..., min_length=1, max_length=5000)
    model: str = Field(default="claude-haiku-4-5-20251001")
    team_id: str = Field(default="platform")
    user_id: str = Field(default="")


class GatewayResponse(BaseModel):
    summary: str
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float
    model_used: str
    cache_hit: bool
    pii_detected: bool
    cost_usd: float
    latency_ms: int
    request_id: str


async def _check_rate_limit(api_key: str) -> bool:
    key = f"aois:ratelimit:{api_key}:{int(time.time()) // 60}"
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, 60)
    return count <= _RATE_LIMIT_RPM


@app.post("/v1/analyze", response_model=GatewayResponse)
async def analyze(
    req: GatewayRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> GatewayResponse:
    t0 = time.time()

    if not await _check_rate_limit(x_api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    allowed, reason = await check_budget(_redis, _db, req.team_id, req.user_id)
    if not allowed:
        raise HTTPException(status_code=402, detail=f"Budget exhausted: {reason}")

    redacted = redact(req.log)
    clean_log = redacted.text
    if redacted.pii_detected:
        log.warning("PII detected and redacted: %s", redacted.detections)

    cached = await get_cached(_redis, req.model, SYSTEM_PROMPT, clean_log)
    if cached:
        data = json.loads(cached)
        latency_ms = int((time.time() - t0) * 1000)
        request_id = await log_call(
            _db,
            api_key_id=x_api_key[:8], user_id=req.user_id, team_id=req.team_id,
            model=req.model, prompt=clean_log, response=cached,
            input_tokens=0, output_tokens=0, cost_usd=0.0,
            latency_ms=latency_ms, cache_hit=True,
            pii_detected=redacted.pii_detected, error=None,
        )
        return GatewayResponse(
            **data,
            cache_hit=True,
            pii_detected=redacted.pii_detected,
            cost_usd=0.0,
            latency_ms=latency_ms,
            request_id=request_id,
            model_used=req.model,
        )

    error_msg = None
    response_text = None
    input_tokens = output_tokens = 0
    cost_usd = 0.0

    try:
        response = await litellm.acompletion(
            model=req.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this log:\n\n{clean_log}"},
            ],
            max_tokens=512,
            temperature=0.1,
        )
        response_text = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost_usd = _estimate_cost(req.model, input_tokens, output_tokens)
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
            latency_ms=latency_ms, cache_hit=False,
            pii_detected=redacted.pii_detected, error=error_msg,
        )

    await debit_budget(_redis, req.team_id, req.user_id, cost_usd)

    analysis: dict = {
        "summary": response_text or "",
        "severity": "P3",
        "suggested_action": "investigate",
        "confidence": 0.7,
    }
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


@app.get("/v1/budget/{entity_type}/{entity_id}")
async def get_budget(entity_type: str, entity_id: str,
                     x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    return await budget_status(_redis, _db, entity_type, entity_id)


@app.get("/v1/cache/stats")
async def get_cache_stats(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    return await cache_stats(_redis)


@app.get("/v1/audit/recent")
async def get_recent_audit(limit: int = 20,
                           x_api_key: str = Header(..., alias="X-API-Key")) -> list:
    rows = await _db.fetch(
        """
        SELECT request_id, api_key_id, team_id, model, cost_usd,
               latency_ms, cache_hit, pii_detected, error, created_at
        FROM llm_audit_log ORDER BY created_at DESC LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


@app.get("/health")
async def health() -> dict:
    await _redis.ping()
    await _db.fetchval("SELECT 1")
    return {"status": "healthy", "service": "ai-gateway"}
