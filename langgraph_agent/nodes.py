"""Node functions for the AOIS SRE graph."""
import anthropic
import json
import logging
import os
import re

from agent.tools.k8s import get_pod_logs, describe_node, list_events, get_metrics
from agent.tools.rag_tool import search_past_incidents
from agent.tools.definitions import TOOL_DEFINITIONS
from agent_gate.enforce import ToolBlocked
from langgraph_agent.state import InvestigationState
from langgraph_agent.dapr_events import publish_node_event

log = logging.getLogger("langgraph_agent")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * 0.80 + output_tokens * 4.00) / 1_000_000


async def _run_tool(tool_name: str, tool_input: dict, session_id: str) -> str:
    fn_map = {
        "get_pod_logs":          get_pod_logs,
        "describe_node":         describe_node,
        "list_events":           list_events,
        "get_metrics":           get_metrics,
        "search_past_incidents": search_past_incidents,
    }
    fn = fn_map.get(tool_name)
    if not fn:
        return f"Unknown tool: {tool_name}"
    try:
        return await fn(**tool_input, session_id=session_id)
    except ToolBlocked as e:
        return f"[BLOCKED: {e}]"
    except Exception as e:
        return f"[Error: {e}]"


async def detect_node(state: InvestigationState) -> dict:
    """Classify the alert and determine severity and next action."""
    log.info("[DETECT] %s", state["incident_description"][:80])
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Classify this alert and determine if investigation is needed.\n"
                f"Alert: {state['incident_description']}\n"
                f"Return JSON: {{\"severity\": \"P1-P4\", \"requires_investigation\": true/false, "
                f"\"reason\": \"...\"}}"
            ),
        }],
    )
    text = response.content[0].text
    try:
        data = json.loads(re.search(r'\{[^{}]+\}', text, re.DOTALL).group())
        severity = data.get("severity", "P3")
    except Exception:
        severity = "P3"

    cost = _estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
    publish_node_event("detect", state["session_id"], {"severity": severity})
    return {
        "severity": severity,
        "cost_usd": state.get("cost_usd", 0.0) + cost,
        "total_tokens": state.get("total_tokens", 0) + response.usage.input_tokens + response.usage.output_tokens,
    }


async def investigate_node(state: InvestigationState) -> dict:
    """Gather evidence using tool calls — v20 investigator as a graph node."""
    log.info("[INVESTIGATE] session=%s", state["session_id"])
    sid = state["session_id"]

    messages = [
        {"role": "user", "content": (
            f"You are investigating: {state['incident_description']}\n"
            f"Severity: {state['severity']}\n"
            f"Gather evidence using your tools. Start with search_past_incidents."
        )},
    ]

    evidence_collected = []
    calls_made = []
    total_input = total_output = 0

    for _ in range(6):
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )
        total_input  += response.usage.input_tokens
        total_output += response.usage.output_tokens

        if response.stop_reason == "end_turn":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue
            calls_made.append({"tool": block.name, "input": block.input})
            result = await _run_tool(block.name, block.input, sid)
            evidence_collected.append(f"[{block.name}]: {result[:800]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result[:3000],
            })

        messages.append({"role": "user", "content": tool_results})

    cost = _estimate_cost(total_input, total_output)
    publish_node_event("investigate", state["session_id"], {"tool_calls": len(calls_made)})
    return {
        "evidence": evidence_collected,
        "tool_calls": calls_made,
        "cost_usd": state.get("cost_usd", 0.0) + cost,
        "total_tokens": state.get("total_tokens", 0) + total_input + total_output,
    }


async def hypothesize_node(state: InvestigationState) -> dict:
    """Propose root cause based on collected evidence."""
    log.info("[HYPOTHESIZE]")
    evidence_summary = "\n".join(state.get("evidence", []))[:3000]
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"Incident: {state['incident_description']}\n"
                f"Evidence collected:\n{evidence_summary}\n\n"
                f"Based on this evidence, propose the root cause and a specific remediation action.\n"
                f"Return JSON: {{\"root_cause\": \"...\", \"proposed_action\": \"...\", "
                f"\"confidence\": 0.0-1.0}}"
            ),
        }],
    )
    text = response.content[0].text
    proposed_action = "investigate further — insufficient evidence"
    hypothesis = text

    try:
        data = json.loads(re.search(r'\{[^{}]+\}', text, re.DOTALL).group())
        proposed_action = data.get("proposed_action", proposed_action)
        hypothesis = data.get("root_cause", text)
    except Exception:
        pass

    cost = _estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
    publish_node_event("hypothesize", state["session_id"], {"hypothesis": hypothesis[:200]})
    return {
        "hypothesis": hypothesis,
        "proposed_action": proposed_action,
        "cost_usd": state.get("cost_usd", 0.0) + cost,
        "total_tokens": state.get("total_tokens", 0) + response.usage.input_tokens + response.usage.output_tokens,
    }


async def verify_node(state: InvestigationState) -> dict:
    """Confirm or refute the hypothesis with one more targeted evidence pull."""
    log.info("[VERIFY] hypothesis=%s", state.get("hypothesis", "")[:60])
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Hypothesis: {state.get('hypothesis', '')}\n"
                f"Evidence so far: {str(state.get('evidence', []))[:1000]}\n"
                f"Is the hypothesis supported by the evidence? "
                f"Return JSON: {{\"verified\": true/false, \"confidence\": 0.0-1.0, \"reason\": \"...\"}}"
            ),
        }],
    )
    text = response.content[0].text
    verified = False
    try:
        data = json.loads(re.search(r'\{[^{}]+\}', text, re.DOTALL).group())
        verified = bool(data.get("verified", False))
    except Exception:
        pass

    cost = _estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
    publish_node_event("verify", state["session_id"], {"verified": verified})
    return {
        "verified": verified,
        "cost_usd": state.get("cost_usd", 0.0) + cost,
        "total_tokens": state.get("total_tokens", 0) + response.usage.input_tokens + response.usage.output_tokens,
    }


async def remediate_node(state: InvestigationState) -> dict:
    """Apply the approved remediation action. Requires human_approved=True."""
    log.info("[REMEDIATE] action=%s", state.get("proposed_action", "")[:60])
    if not state.get("human_approved", False):
        return {"remediation_result": "BLOCKED — human approval required"}

    # Remediation is simulated in v23 (E2B sandbox execution added in v25)
    action = state.get("proposed_action", "")
    result = f"[SIMULATED] Would execute: {action}"
    log.info("Remediation (simulated): %s", action)
    publish_node_event("remediate", state["session_id"], {"result": result})
    return {"remediation_result": result}


async def report_node(state: InvestigationState) -> dict:
    """Write the investigation report to Postgres."""
    import asyncpg
    log.info("[REPORT] session=%s", state["session_id"])

    report_text = (
        f"# AOIS Investigation Report\n\n"
        f"**Incident**: {state['incident_description']}\n"
        f"**Severity**: {state.get('severity', 'P3')}\n"
        f"**Hypothesis**: {state.get('hypothesis', 'N/A')}\n"
        f"**Verified**: {state.get('verified', False)}\n"
        f"**Proposed Action**: {state.get('proposed_action', 'N/A')}\n"
        f"**Human Approved**: {state.get('human_approved', False)}\n"
        f"**Remediation**: {state.get('remediation_result', 'Not executed')}\n"
        f"**Total Cost**: ${state.get('cost_usd', 0):.6f}\n"
        f"**Tool Calls**: {len(state.get('tool_calls', []))}\n"
    )

    try:
        db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
        await db.execute(
            """
            INSERT INTO investigation_reports
              (session_id, incident, severity, hypothesis, proposed_action,
               human_approved, remediation_result, cost_usd, report_text, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
            ON CONFLICT (session_id) DO UPDATE
              SET report_text=EXCLUDED.report_text
            """,
            state["session_id"],
            state["incident_description"][:500],
            state.get("severity", "P3"),
            state.get("hypothesis", "")[:1000],
            state.get("proposed_action", "")[:500],
            state.get("human_approved", False),
            state.get("remediation_result", ""),
            state.get("cost_usd", 0.0),
            report_text,
        )
        await db.close()
    except Exception as e:
        log.warning("Report DB write failed (non-fatal): %s", e)

    publish_node_event("report", state["session_id"], {"cost_usd": state.get("cost_usd", 0)})
    return {"report": report_text}
