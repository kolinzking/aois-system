"""
Fire-and-forget ClickHouse writer for AOIS incident telemetry.
Never raises — ClickHouse write failure must not block the API response.
"""
import logging
import os
from datetime import datetime

import clickhouse_connect

log = logging.getLogger("clickhouse.writer")

_client: clickhouse_connect.driver.Client | None = None

_COLUMNS = [
    "request_id", "incident_id", "model", "tier", "severity",
    "input_tokens", "output_tokens", "cost_usd", "cache_hit",
    "latency_ms", "confidence", "pii_detected", "created_at",
]


def _get() -> clickhouse_connect.driver.Client:
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "aois"),
            password=os.getenv("CLICKHOUSE_PASSWORD", "aois_ch_pass"),
            database=os.getenv("CLICKHOUSE_DB", "aois"),
        )
    return _client


def write_incident(
    *,
    request_id: str,
    incident_id: str,
    model: str,
    tier: str,
    severity: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    cache_hit: bool,
    latency_ms: int,
    confidence: float,
    pii_detected: bool,
) -> None:
    try:
        _get().insert(
            "incident_telemetry",
            [[
                request_id, incident_id, model, tier, severity,
                input_tokens, output_tokens, cost_usd,
                int(cache_hit), latency_ms, confidence,
                int(pii_detected), datetime.utcnow(),
            ]],
            column_names=_COLUMNS,
        )
    except Exception as e:
        log.warning("ClickHouse write failed (non-fatal): %s", e)
