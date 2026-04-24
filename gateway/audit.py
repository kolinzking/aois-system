import hashlib
import uuid

import asyncpg


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def log_call(db: asyncpg.Pool, *, api_key_id: str, user_id: str, team_id: str,
                   model: str, prompt: str, response: str | None,
                   input_tokens: int, output_tokens: int, cost_usd: float,
                   latency_ms: int, cache_hit: bool, pii_detected: bool,
                   error: str | None) -> str:
    request_id = str(uuid.uuid4())
    await db.execute(
        """
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
        latency_ms, cache_hit, pii_detected, error,
    )
    return request_id
