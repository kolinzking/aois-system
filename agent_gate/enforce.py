"""
@gated_tool decorator — single enforcement point for all agent tools.
Applies capability boundary → circuit breaker → kill switch in order.
"""
import functools
import logging

from .circuit_breaker import CircuitBreakerTripped, record_call
from .gate import check_tool

log = logging.getLogger("enforce")


class ToolBlocked(Exception):
    """Raised when a tool call is blocked by any layer of the gate."""


def gated_tool(agent_role: str, cost_estimate_usd: float = 0.0):
    """
    Decorator factory. Wraps a tool function with the full gate stack.

    Usage:
        @gated_tool(agent_role="read_only")
        async def get_pod_logs(namespace: str, pod_name: str,
                               session_id: str = "default") -> str:
            ...
    """
    def decorator(fn):
        tool_name = fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args, session_id: str = "default",
                          human_approved: bool = False, **kwargs):
            allowed, reason = check_tool(tool_name, agent_role, human_approved)
            if not allowed:
                raise ToolBlocked(f"Capability boundary: {reason}")
            try:
                record_call(session_id, tool_name, cost_estimate_usd)
            except CircuitBreakerTripped as e:
                raise ToolBlocked(f"Circuit breaker: {e}") from e
            log.info("Tool ALLOWED: %s (role=%s session=%s)", tool_name, agent_role, session_id)
            return await fn(*args, session_id=session_id, **kwargs)

        wrapper._tool_name  = tool_name
        wrapper._agent_role = agent_role
        return wrapper
    return decorator
