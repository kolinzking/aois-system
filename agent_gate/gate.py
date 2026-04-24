"""OPA-backed capability boundary. Called before every tool execution."""
import json
import logging
import os
import subprocess

log = logging.getLogger("agent_gate")

_POLICY_PATH = os.path.join(os.path.dirname(__file__), "policy.rego")


def check_tool(tool_name: str, agent_role: str,
               human_approved: bool = False) -> tuple[bool, str]:
    """
    Evaluate the capability boundary policy.
    Returns (allowed, reason). Defaults to deny on evaluation error.
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
