"""
Global kill switch. Asserted by a human operator; checked on every tool call.
State lives in Redis so it survives pod restarts.
"""
import json
import logging
import os
from datetime import datetime

import redis

log = logging.getLogger("kill_switch")

_r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
_KEY = "aois:killswitch"


def halt(reason: str, operator: str = "unknown") -> None:
    payload = {
        "active": True,
        "reason": reason,
        "operator": operator,
        "asserted_at": datetime.utcnow().isoformat(),
    }
    _r.set(_KEY, json.dumps(payload))
    log.critical("KILL SWITCH ASSERTED by %s: %s", operator, reason)


def clear(operator: str = "unknown") -> None:
    _r.delete(_KEY)
    log.warning("Kill switch cleared by %s", operator)


def is_halted() -> bool:
    return _r.exists(_KEY) == 1


def status() -> dict:
    raw = _r.get(_KEY)
    if not raw:
        return {"active": False}
    return json.loads(raw)
