"""FastAPI router for kill switch and circuit breaker operator controls."""
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .circuit_breaker import get_session_state, reset_session
from .kill_switch import clear, halt, status as ks_status

router = APIRouter(prefix="/agent", tags=["agent-gate"])

_OPERATOR_KEY = os.getenv("OPERATOR_KEY", "aois-operator-key")


def _auth(key: str) -> None:
    if key != _OPERATOR_KEY:
        raise HTTPException(status_code=403, detail="Operator key required")


class HaltRequest(BaseModel):
    reason: str
    operator: str = "unknown"


@router.post("/killswitch/halt")
def assert_kill_switch(req: HaltRequest,
                        x_operator_key: str = Header(..., alias="X-Operator-Key")):
    _auth(x_operator_key)
    halt(req.reason, req.operator)
    return {"status": "halted", "reason": req.reason}


@router.post("/killswitch/clear")
def clear_kill_switch(operator: str = "unknown",
                       x_operator_key: str = Header(..., alias="X-Operator-Key")):
    _auth(x_operator_key)
    clear(operator)
    return {"status": "cleared"}


@router.get("/killswitch/status")
def kill_switch_status():
    return ks_status()


@router.get("/session/{session_id}")
def session_state(session_id: str,
                  x_operator_key: str = Header(..., alias="X-Operator-Key")):
    _auth(x_operator_key)
    return get_session_state(session_id)


@router.post("/session/{session_id}/reset")
def reset_cb(session_id: str,
             x_operator_key: str = Header(..., alias="X-Operator-Key")):
    _auth(x_operator_key)
    reset_session(session_id)
    return {"status": "reset", "session_id": session_id}
