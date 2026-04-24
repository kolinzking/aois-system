# Phase 7 Gate — Agent Capability Boundary, Circuit Breaker, and Kill Switch

⏱ **Estimated time: 4–5 hours**

> **This is not optional.** AOIS does not receive any tools until this gate is built and tested.
> The gate is the difference between an agent you deploy and one that quietly destroys things.

---

## Prerequisites

v19 complete. Basic Python and FastAPI familiarity from Phases 1–6.

```bash
# AOIS analyze endpoint is healthy
curl -s http://localhost:8000/health | jq .status
# "healthy"

# OPA is available (will install below)
which opa 2>/dev/null || echo "install OPA first — see below"

# Redis is reachable (used for circuit breaker state)
redis-cli ping
# PONG
```

---

## Learning Goals

By the end you will be able to:

- Explain the difference between the output blocklist in v5 (reactive) and the capability boundary (preventive)
- Implement a policy engine using OPA that decides at invocation time what tools AOIS may call
- Build a circuit breaker that halts the agent mid-execution based on cost, call count, or anomalous sequences
- Build a kill switch that a human operator can assert at any time to stop all agent activity
- Test the gate by attempting tool calls that should be blocked and confirming they never execute
- Explain why this gate cannot be implemented in the LLM system prompt alone

---

## Why the Output Blocklist Is Not Enough

In v5, AOIS has an output blocklist: after the LLM returns its suggested action, the code scans for destructive patterns ("delete the cluster", "rm -rf", "drop table") and blocks responses that match. This is reactive — it fires at response time, after the LLM has already reasoned about and recommended a destructive action.

This is necessary but insufficient for an agent with tools. Here is why:

A blocklist on the output catches *what AOIS recommends*. It does not govern *what AOIS does*. When AOIS has a `kubectl delete` tool, the question is not "will it recommend deletion?" — the question is "can it call `kubectl delete` at all?"

The answer must be structurally **no** for certain operations, regardless of what the LLM decides. Not "the LLM will hopefully not call it" — "the invocation layer enforces it before execution."

The three layers:

```
LLM decides which tool to call
        ↓
Capability Boundary: is this tool in the allowed set for this agent?
        ↓ (allowed)
Circuit Breaker: has this agent exceeded cost/call/anomaly thresholds?
        ↓ (within limits)
Tool executes
        ↓
Kill Switch: is there an operator halt? (checked on every call)
```

Any layer can halt execution. No layer trusts the one above it.

---

## Installing OPA

OPA (Open Policy Agent) is the policy engine used for the capability boundary. It evaluates structured policies written in Rego (OPA's policy language) against structured input (the tool call request).

```bash
# Linux x86_64
curl -L -o /usr/local/bin/opa \
  https://openpolicyagent.org/downloads/v0.64.1/opa_linux_amd64_static
chmod +x /usr/local/bin/opa

# Verify
opa version
# Version: 0.64.1
# Build Commit: ...
```

OPA can run as a standalone binary (called inline from Python) or as a daemon with an HTTP API. For AOIS in Phase 7, you will call it as a Python library via `pip install opa-python-client` — or, simpler, by calling the OPA binary as a subprocess with JSON input and reading the JSON output. The subprocess approach requires no additional dependencies and makes the policy evaluation transparent.

---

## The Capability Boundary Policy

Define what tools are allowed in Rego. This is the source of truth — not a Python dict, not a config file, a versioned policy file checked into git.

```rego
# agent_gate/policy.rego
package aois.agent

# Default deny — if no rule allows, the call is blocked
default allow = false

# ─────────────────────────────────────────────────
# Tool allowlist per agent role
# ─────────────────────────────────────────────────
# "read_only" agent: can only observe, never write
read_only_tools := {
    "get_pod_logs",
    "describe_node",
    "list_events",
    "get_metrics",
    "search_past_incidents",
    "describe_deployment",
    "get_pod_status",
}

# "analyst" agent: read_only + can write analysis results, open tickets
analyst_tools := read_only_tools | {
    "write_incident_report",
    "create_jira_ticket",
    "post_slack_message",
}

# "operator" agent: analyst + can make non-destructive k8s changes
# Requires human approval gate before each call (enforced in circuit_breaker.py)
operator_tools := analyst_tools | {
    "scale_deployment",
    "restart_pod",
    "update_configmap",
    "patch_resource_limits",
}

# ─────────────────────────────────────────────────
# Permanently blocked tools — no role can call these
# ─────────────────────────────────────────────────
blocked_tools := {
    "delete_namespace",
    "delete_cluster",
    "delete_persistent_volume",
    "exec_arbitrary_command",  # shell exec is never allowed
    "modify_rbac",
    "access_secret_store",     # secrets accessed via dedicated secret tools only
}

# ─────────────────────────────────────────────────
# Allow rules
# ─────────────────────────────────────────────────
allow {
    # Tool is not in the permanently blocked set
    not input.tool_name in blocked_tools

    # Tool is in the allowed set for the agent's role
    input.agent_role == "read_only"
    input.tool_name in read_only_tools
}

allow {
    not input.tool_name in blocked_tools
    input.agent_role == "analyst"
    input.tool_name in analyst_tools
}

allow {
    not input.tool_name in blocked_tools
    input.agent_role == "operator"
    input.tool_name in operator_tools
    # Operator tools that modify state require human_approved=true in the request
    not requires_approval(input.tool_name)
}

allow {
    not input.tool_name in blocked_tools
    input.agent_role == "operator"
    input.tool_name in operator_tools
    requires_approval(input.tool_name)
    input.human_approved == true
}

# Tools that require explicit human approval before execution
requires_approval(tool) {
    tool in {"scale_deployment", "restart_pod", "update_configmap", "patch_resource_limits"}
}

# ─────────────────────────────────────────────────
# Reason: returned alongside the allow decision
# ─────────────────────────────────────────────────
reason = msg {
    allow
    msg := "allowed"
}

reason = msg {
    not allow
    input.tool_name in blocked_tools
    msg := sprintf("tool '%v' is permanently blocked — no role may invoke it", [input.tool_name])
}

reason = msg {
    not allow
    not input.tool_name in blocked_tools
    input.agent_role == "operator"
    requires_approval(input.tool_name)
    not input.human_approved
    msg := sprintf("tool '%v' requires human_approved=true for operator role", [input.tool_name])
}

reason = msg {
    not allow
    not input.tool_name in blocked_tools
    msg := sprintf("tool '%v' is not in the allowed set for role '%v'", [input.tool_name, input.agent_role])
}
```

---

## The Gate Enforcer

```python
# agent_gate/gate.py
"""
Capability boundary enforcer. Every tool call goes through check_tool() before execution.
If check_tool() returns False, the tool is never called — the invocation is blocked at this layer.
"""
import json
import subprocess
import logging
import os

log = logging.getLogger("agent_gate")

_POLICY_PATH = os.path.join(os.path.dirname(__file__), "policy.rego")


def check_tool(tool_name: str, agent_role: str,
               human_approved: bool = False) -> tuple[bool, str]:
    """
    Evaluate the capability boundary policy for a tool call.
    Returns (allowed: bool, reason: str).
    Never raises — a policy evaluation failure defaults to deny.
    """
    input_data = {
        "tool_name": tool_name,
        "agent_role": agent_role,
        "human_approved": human_approved,
    }
    try:
        result = subprocess.run(
            ["opa", "eval",
             "--data", _POLICY_PATH,
             "--input", "/dev/stdin",
             "--format", "json",
             "data.aois.agent"],
            input=json.dumps(input_data).encode(),
            capture_output=True,
            timeout=2,
        )
        output = json.loads(result.stdout)
        bindings = output["result"][0]["expressions"][0]["value"]
        allowed = bindings.get("allow", False)
        reason  = bindings.get("reason", "no reason provided")
        if not allowed:
            log.warning("Gate BLOCKED: tool=%s role=%s reason=%s",
                        tool_name, agent_role, reason)
        return allowed, reason
    except Exception as e:
        log.error("Policy evaluation failed — defaulting to DENY: %s", e)
        return False, f"policy evaluation error: {e}"
```

---

## The Circuit Breaker

```python
# agent_gate/circuit_breaker.py
"""
Circuit breaker for agent tool calls.
Tracks: call count, cost, and anomalous sequences per investigation session.
Halts the agent when any threshold is breached.
"""
import redis
import json
import time
import logging
import os

log = logging.getLogger("circuit_breaker")

_r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

# Thresholds — tune these based on observed agent behaviour in v23/v24
MAX_CALLS_PER_SESSION   = 20       # max tool calls in one investigation
MAX_COST_PER_SESSION    = 0.50     # max $0.50 in LLM + tool costs per session
MAX_SAME_TOOL_REPEAT    = 5        # if same tool called >5 times: anomaly
TRIP_TTL_SECONDS        = 300      # tripped circuit stays open for 5 minutes


class CircuitBreakerTripped(Exception):
    """Raised when the circuit breaker halts agent execution."""


def _session_key(session_id: str) -> str:
    return f"aois:cb:{session_id}"


def record_call(session_id: str, tool_name: str, cost_usd: float = 0.0) -> None:
    """
    Record a tool call. Raises CircuitBreakerTripped if any threshold is exceeded.
    Call this BEFORE executing the tool.
    """
    # Check kill switch first (see kill_switch.py)
    from .kill_switch import is_halted
    if is_halted():
        raise CircuitBreakerTripped("Kill switch is active — all agent activity halted")

    key = _session_key(session_id)
    data_raw = _r.get(key)
    if data_raw:
        data = json.loads(data_raw)
    else:
        data = {"calls": 0, "cost": 0.0, "tool_counts": {}, "tripped": False}

    # Already tripped?
    if data.get("tripped"):
        raise CircuitBreakerTripped(
            f"Circuit breaker already tripped for session {session_id}"
        )

    # Check thresholds BEFORE incrementing
    new_calls = data["calls"] + 1
    new_cost  = data["cost"] + cost_usd
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

    # Update state
    data["calls"]  = new_calls
    data["cost"]   = new_cost
    data["tool_counts"][tool_name] = tool_count
    _r.setex(key, 3600, json.dumps(data))  # session state expires after 1 hour


def get_session_state(session_id: str) -> dict:
    data_raw = _r.get(_session_key(session_id))
    if not data_raw:
        return {"calls": 0, "cost": 0.0, "tool_counts": {}, "tripped": False}
    return json.loads(data_raw)


def reset_session(session_id: str) -> None:
    """Manual reset — used after human review of a tripped session."""
    _r.delete(_session_key(session_id))
    log.info("Circuit breaker reset for session %s", session_id)
```

---

## The Kill Switch

```python
# agent_gate/kill_switch.py
"""
Global kill switch for all AOIS agent activity.
A human operator asserts the switch; it stays active until explicitly cleared.
Every tool call checks is_halted() before execution.
"""
import redis
import logging
import os
from datetime import datetime

log = logging.getLogger("kill_switch")

_r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
_KEY = "aois:killswitch"


def halt(reason: str, operator: str = "unknown") -> None:
    """Assert the kill switch. All agent tool calls will fail immediately."""
    payload = {
        "active": True,
        "reason": reason,
        "operator": operator,
        "asserted_at": datetime.utcnow().isoformat(),
    }
    import json
    _r.set(_KEY, json.dumps(payload))
    log.critical("KILL SWITCH ASSERTED by %s: %s", operator, reason)


def clear(operator: str = "unknown") -> None:
    """Clear the kill switch. Agent activity resumes."""
    _r.delete(_KEY)
    log.warning("Kill switch cleared by %s", operator)


def is_halted() -> bool:
    """Returns True if the kill switch is active. Checked on every tool call."""
    return _r.exists(_KEY) == 1


def status() -> dict:
    import json
    raw = _r.get(_KEY)
    if not raw:
        return {"active": False}
    return json.loads(raw)
```

---

## The Tool Decorator

Wrap every agent tool with the gate. This is the single enforcement point — tools don't need to check the gate themselves.

```python
# agent_gate/enforce.py
"""
Decorator that wraps any tool function with the full gate:
  1. Capability boundary (OPA policy)
  2. Circuit breaker (call count / cost / anomaly)
  3. Kill switch (operator halt)
"""
import functools
import logging
from .gate import check_tool
from .circuit_breaker import record_call, CircuitBreakerTripped

log = logging.getLogger("enforce")


class ToolBlocked(Exception):
    """Raised when a tool call is blocked by the gate."""


def gated_tool(agent_role: str, cost_estimate_usd: float = 0.0):
    """
    Decorator factory.

    Usage:
        @gated_tool(agent_role="read_only")
        async def get_pod_logs(namespace: str, pod_name: str, session_id: str) -> str:
            ...
    """
    def decorator(fn):
        tool_name = fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args, session_id: str = "default", human_approved: bool = False,
                          **kwargs):
            # 1. Capability boundary
            allowed, reason = check_tool(tool_name, agent_role, human_approved)
            if not allowed:
                raise ToolBlocked(f"Capability boundary: {reason}")

            # 2. Circuit breaker + kill switch (record_call checks kill switch internally)
            try:
                record_call(session_id, tool_name, cost_estimate_usd)
            except CircuitBreakerTripped as e:
                raise ToolBlocked(f"Circuit breaker: {e}") from e

            # 3. Execute
            log.info("Tool ALLOWED: %s (role=%s session=%s)", tool_name, agent_role, session_id)
            return await fn(*args, session_id=session_id, **kwargs)

        wrapper._tool_name = tool_name
        wrapper._agent_role = agent_role
        return wrapper
    return decorator
```

---

## Gate API Endpoints

Expose the kill switch and circuit breaker state via FastAPI so operators can act without SSH access:

```python
# agent_gate/api.py
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from .kill_switch import halt, clear, status as ks_status
from .circuit_breaker import get_session_state, reset_session

router = APIRouter(prefix="/agent", tags=["agent-gate"])

_OPERATOR_KEY = "aois-operator-key"  # in production: read from Vault


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
```

---

## Testing the Gate

This is the most important step. The gate means nothing if you have not confirmed it blocks what it should block.

```bash
# Save and test the OPA policy directly
echo '{"tool_name":"get_pod_logs","agent_role":"read_only","human_approved":false}' | \
  opa eval --data agent_gate/policy.rego --input /dev/stdin --format json "data.aois.agent.allow"
# {"result":[{"expressions":[{"value":true,"text":"data.aois.agent.allow","location":{"row":1,"col":1}}]}]}
# → true: read_only agent can call get_pod_logs ✓

echo '{"tool_name":"delete_namespace","agent_role":"operator","human_approved":true}' | \
  opa eval --data agent_gate/policy.rego --input /dev/stdin --format json "data.aois.agent.allow"
# → false: delete_namespace is permanently blocked, no role may call it ✓

echo '{"tool_name":"scale_deployment","agent_role":"operator","human_approved":false}' | \
  opa eval --data agent_gate/policy.rego --input /dev/stdin --format json "data.aois.agent.allow"
# → false: operator tool requires human_approved=true ✓

echo '{"tool_name":"scale_deployment","agent_role":"operator","human_approved":true}' | \
  opa eval --data agent_gate/policy.rego --input /dev/stdin --format json "data.aois.agent.allow"
# → true: operator + approved ✓

echo '{"tool_name":"get_pod_logs","agent_role":"read_only","human_approved":false}' | \
  opa eval --data agent_gate/policy.rego --input /dev/stdin --format json "data.aois.agent.reason"
# → "allowed" ✓

echo '{"tool_name":"delete_namespace","agent_role":"operator","human_approved":true}' | \
  opa eval --data agent_gate/policy.rego --input /dev/stdin --format json "data.aois.agent.reason"
# → "tool 'delete_namespace' is permanently blocked — no role may invoke it" ✓
```

```python
# Test circuit breaker: exceed the call limit
from agent_gate.circuit_breaker import record_call, reset_session, CircuitBreakerTripped

session = "test-session-001"
reset_session(session)

try:
    for i in range(25):  # MAX_CALLS_PER_SESSION = 20
        record_call(session, "get_pod_logs", cost_usd=0.001)
        print(f"Call {i+1}: OK")
except CircuitBreakerTripped as e:
    print(f"TRIPPED at call {i+1}: {e}")
# Call 1: OK
# ...
# Call 20: OK
# TRIPPED at call 21: Circuit breaker TRIPPED for session test-session-001: call count 21 > 20
```

```python
# Test kill switch
from agent_gate.kill_switch import halt, is_halted, clear
from agent_gate.circuit_breaker import record_call, CircuitBreakerTripped

halt("testing kill switch", operator="collins")
assert is_halted() == True

try:
    record_call("test-session-002", "get_pod_logs")
except CircuitBreakerTripped as e:
    print(f"Correctly blocked: {e}")
# Correctly blocked: Kill switch is active — all agent activity halted

clear("collins")
assert is_halted() == False
print("Kill switch cleared")
```

---

## Mastery Checkpoint

The gate is not done until every test passes. Run these in order.

1. Assert the kill switch via the API (`POST /agent/killswitch/halt`). Attempt a tool call via `record_call()`. Confirm `CircuitBreakerTripped` is raised. Clear the switch and confirm tool calls succeed again.

2. Write a test that fires 21 tool calls in one session. Confirm call 21 raises `CircuitBreakerTripped`. Reset the session. Confirm call 1 succeeds again.

3. Verify these five OPA evaluations produce the expected results:
   - `read_only` + `get_pod_logs` → `true`
   - `read_only` + `scale_deployment` → `false`
   - `operator` + `scale_deployment` + `human_approved=false` → `false`
   - `operator` + `scale_deployment` + `human_approved=true` → `true`
   - Any role + `delete_namespace` → `false`

4. Add a new tool `cordon_node` to the `operator_tools` set in the Rego policy. Verify with OPA eval that an `operator` role can call it (with approval). Verify a `read_only` role cannot. This tests that you can change policy without touching Python code.

5. Explain to a junior engineer: why is the gate in a decorator (`@gated_tool`) rather than inside each tool function? What would happen if each tool checked the gate itself?

6. Explain to a senior engineer: why is OPA (a Rego policy engine) used instead of a Python `if/else` allowlist? What does the Rego policy give you that Python dicts do not?

**The mastery bar:** you can add a new tool and a new role to the system by editing only `policy.rego` — no Python changes, no service restart required. The gate is the policy. The policy is the gate.

---

## 4-Layer Tool Understanding

### OPA (Open Policy Agent)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | You need rules about what the agent is allowed to do — and those rules need to be auditable, testable, and changeable without deploying new code. OPA is a policy engine that evaluates those rules from a separate file, so policy and code are never mixed. |
| **System Role** | Where does it sit in AOIS? | Between the LLM's tool choice and the tool's execution. Every tool call hits `check_tool()`, which calls OPA with the tool name and agent role as input. OPA evaluates `policy.rego` and returns `allow: true/false`. If false, the tool never runs. |
| **Technical** | What is it, precisely? | A general-purpose policy engine using the Rego language. Rego is a declarative query language for structured data — you define what is allowed, not how to check it. OPA evaluates Rego policies against JSON input and returns JSON output. Supports deny-by-default, hierarchical rule sets, and full unit test support (`opa test`). |
| **Remove it** | What breaks, and how fast? | Remove OPA → capability boundary is a Python dict. That dict is in application code, not in a policy repo, not independently testable, not auditable by security teams. The policy becomes implicit in the code rather than explicit in a file. Discovery: after the first security audit. |

### Circuit Breaker (Agent Context)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | An agent can get stuck in a loop, calling the same tool repeatedly, or spend $50 before you notice. The circuit breaker counts calls and costs during an investigation and stops the agent automatically when thresholds are exceeded — before the damage is done. |
| **System Role** | Where does it sit in AOIS? | Inside `record_call()`, which is called in the `@gated_tool` decorator before every tool execution. The state is stored in Redis (per session_id). If the circuit trips, `CircuitBreakerTripped` is raised and the agent stops immediately. |
| **Technical** | What is it, precisely? | A stateful counter in Redis keyed by session_id. Tracks: total call count, total cost, per-tool call count. Three thresholds: max calls per session (20), max cost per session ($0.50), max same-tool repeat (5). When any threshold is exceeded, the session key is marked `tripped` and all further calls for that session raise `CircuitBreakerTripped`. Resets via operator API or TTL expiry. |
| **Remove it** | What breaks, and how fast? | Remove circuit breaker → runaway agent loops run until API rate limits or credit exhaustion. An agent with a bug in its tool-calling loop can burn hundreds of dollars in minutes. Discovery: next day, in the billing dashboard. |
