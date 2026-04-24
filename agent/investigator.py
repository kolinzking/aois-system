"""
AOIS investigative agent using Claude tool use.
Multi-turn loop: Claude calls tools → AOIS executes via gate → repeat until done.
"""
import logging
import os
import re
import time
import uuid

import anthropic

from agent.memory import recall_relevant, store_investigation
from agent.tools.definitions import TOOL_DEFINITIONS
from agent.tools.k8s import describe_node, get_metrics, get_pod_logs, list_events
from agent.tools.rag_tool import search_past_incidents
from agent_gate.enforce import ToolBlocked
from clickhouse.writer import write_incident

log = logging.getLogger("agent.investigator")

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_TOOL_MAP = {
    "get_pod_logs":          get_pod_logs,
    "describe_node":         describe_node,
    "list_events":           list_events,
    "get_metrics":           get_metrics,
    "search_past_incidents": search_past_incidents,
}

AGENT_SYSTEM_PROMPT = """You are AOIS, an autonomous SRE investigation agent.

When given an incident alert you MUST:
1. First call search_past_incidents to check if this has been seen before
2. Pull relevant logs and events to gather evidence
3. Check metrics if resource pressure is suspected
4. Form a hypothesis based on the evidence — not assumptions

Provide a structured response:
  Severity: P1/P2/P3/P4
  Root cause: (specific, evidence-based)
  Evidence summary: (what you found)
  Recommended action: (concrete, non-destructive)

Rules:
- Never recommend destructive actions (delete, rm -rf, drop)
- Always cite specific evidence from tool results
- If evidence is insufficient, state what additional data is needed
"""

_COST_PER_1M = {"in": 0.80, "out": 4.00}  # claude-haiku-4-5-20251001


async def investigate(incident_description: str,
                      agent_role: str = "read_only",
                      session_id: str | None = None) -> dict:
    """
    Run a full investigation. Returns result dict with tool trace and cost attribution.
    """
    session_id = session_id or str(uuid.uuid4())
    t0 = time.time()
    total_input = total_output = 0
    tool_calls_made: list[dict] = []

    # Recall relevant past memories
    past_memory = recall_relevant(incident_description)
    system = AGENT_SYSTEM_PROMPT + (f"\n\n{past_memory}" if past_memory else "")

    messages: list[dict] = [{"role": "user", "content": incident_description}]

    def bind_session(fn):
        async def caller(**kwargs):
            return await fn(**kwargs, session_id=session_id)
        return caller

    tools = {name: bind_session(fn) for name, fn in _TOOL_MAP.items()}

    for iteration in range(10):
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=system,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )
        total_input  += response.usage.input_tokens
        total_output += response.usage.output_tokens

        if response.stop_reason == "end_turn":
            final_text = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            latency_ms = int((time.time() - t0) * 1000)
            cost_usd = (total_input * _COST_PER_1M["in"] +
                        total_output * _COST_PER_1M["out"]) / 1_000_000

            write_incident(
                request_id=str(uuid.uuid4()),
                incident_id=session_id,
                model="claude-haiku-4-5-20251001",
                tier="premium",
                severity=_extract_severity(final_text),
                input_tokens=total_input,
                output_tokens=total_output,
                cost_usd=cost_usd,
                cache_hit=False,
                latency_ms=latency_ms,
                confidence=0.85,
                pii_detected=False,
            )

            store_investigation(
                session_id=session_id,
                incident=incident_description,
                resolution=final_text,
                severity=_extract_severity(final_text),
                root_cause="see investigation",
            )

            log.info("Done: session=%s iter=%d cost=$%.6f", session_id, iteration + 1, cost_usd)
            return {
                "session_id": session_id,
                "incident": incident_description,
                "investigation": final_text,
                "tool_calls": tool_calls_made,
                "iterations": iteration + 1,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost_usd, 6),
                "latency_ms": latency_ms,
            }

        # Process tool calls
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_name = block.name
            tool_calls_made.append({"tool": tool_name, "input": block.input})
            log.info("Tool call: %s(%s)", tool_name, block.input)

            fn = tools.get(tool_name)
            if not fn:
                result_text = f"Unknown tool: {tool_name}"
            else:
                try:
                    result_text = await fn(**block.input)
                except ToolBlocked as e:
                    result_text = f"[TOOL BLOCKED: {e}]"
                    log.warning("Blocked: %s — %s", tool_name, e)
                except Exception as e:
                    result_text = f"[Tool error: {e}]"
                    log.error("Tool error %s: %s", tool_name, e)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result_text)[:4000],
            })

        messages.append({"role": "user", "content": tool_results})

    return {
        "session_id": session_id,
        "incident": incident_description,
        "investigation": "Max iterations reached without final response",
        "tool_calls": tool_calls_made,
        "error": "max_iterations_exceeded",
    }


def _extract_severity(text: str) -> str:
    m = re.search(r'P[1-4]', text)
    return m.group(0) if m else "P3"
