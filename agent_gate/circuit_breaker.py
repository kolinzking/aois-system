"""
Circuit breaker for agent tool calls.
Tracks call count, cost, and per-tool repetition per session.
Halts the agent when any threshold is breached.
"""
import json
import logging
import os

import redis

log = logging.getLogger("circuit_breaker")

_r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

MAX_CALLS_PER_SESSION  = 20
MAX_COST_PER_SESSION   = 0.50
MAX_SAME_TOOL_REPEAT   = 5
TRIP_TTL_SECONDS       = 300
SESSION_TTL_SECONDS    = 3600


class CircuitBreakerTripped(Exception):
    """Raised when the circuit breaker halts agent execution."""


def _key(session_id: str) -> str:
    return f"aois:cb:{session_id}"


def record_call(session_id: str, tool_name: str, cost_usd: float = 0.0) -> None:
    """
    Record a tool call attempt. Raises CircuitBreakerTripped if any threshold
    is exceeded or if the kill switch is active.
    Call this BEFORE executing the tool.
    """
    from .kill_switch import is_halted
    if is_halted():
        raise CircuitBreakerTripped("Kill switch is active — all agent activity halted")

    key = _key(session_id)
    raw = _r.get(key)
    data = json.loads(raw) if raw else {"calls": 0, "cost": 0.0, "tool_counts": {}, "tripped": False}

    if data.get("tripped"):
        raise CircuitBreakerTripped(f"Circuit breaker already tripped for session {session_id}")

    new_calls  = data["calls"] + 1
    new_cost   = data["cost"] + cost_usd
    tool_count = data["tool_counts"].get(tool_name, 0) + 1

    violations = []
    if new_calls > MAX_CALLS_PER_SESSION:
        violations.append(f"call count {new_calls} > {MAX_CALLS_PER_SESSION}")
    if new_cost > MAX_COST_PER_SESSION:
        violations.append(f"cost ${new_cost:.4f} > ${MAX_COST_PER_SESSION:.4f}")
    if tool_count > MAX_SAME_TOOL_REPEAT:
        violations.append(f"tool '{tool_name}' called {tool_count} times (anomaly)")

    if violations:
        data["tripped"] = True
        _r.setex(key, TRIP_TTL_SECONDS, json.dumps(data))
        msg = f"Circuit breaker TRIPPED for session {session_id}: {'; '.join(violations)}"
        log.error(msg)
        raise CircuitBreakerTripped(msg)

    data["calls"]  = new_calls
    data["cost"]   = new_cost
    data["tool_counts"][tool_name] = tool_count
    _r.setex(key, SESSION_TTL_SECONDS, json.dumps(data))


def get_session_state(session_id: str) -> dict:
    raw = _r.get(_key(session_id))
    return json.loads(raw) if raw else {"calls": 0, "cost": 0.0, "tool_counts": {}, "tripped": False}


def reset_session(session_id: str) -> None:
    _r.delete(_key(session_id))
    log.info("Circuit breaker reset for session %s", session_id)
