# v23 — LangGraph: Autonomous SRE Loop

⏱ **Estimated time: 6–8 hours**

---

## Prerequisites

v22 Temporal workflows complete. LangGraph installable.

```bash
# Temporal worker runs successfully
python3 -c "from temporal_workflows.investigation_workflow import InvestigationWorkflow; print('ok')"
# ok

# LangGraph + LangChain available
pip install langgraph langchain-anthropic
python3 -c "import langgraph; print(langgraph.__version__)"
# 0.x.x

# Postgres up (for audit trail)
psql $DATABASE_URL -c "SELECT 1" -q
# (1 row)
```

---

## Learning Goals

By the end you will be able to:

- Explain what LangGraph is and how it differs from the flat tool-use loop in v20
- Build a stateful agent graph with distinct nodes: Detect, Investigate, Hypothesize, Verify, Remediate, Report
- Implement a human-in-the-loop approval gate that pauses the graph before any write action
- Persist the full investigation graph state to Postgres as an immutable audit trail
- Integrate Dapr pub/sub so graph nodes communicate via portable messaging
- Run the full SRE loop end-to-end: alert → investigation → human approval → (simulated) remediation → report
- Explain when LangGraph adds value over a plain loop, and when it does not

---

## The Problem This Solves

The `investigate()` function in v20 is a flat loop: Claude calls tools until it has enough evidence, then returns a final response. This works for investigation. It does not scale to the full SRE lifecycle.

A real SRE incident response is not a loop — it is a state machine:

```
Alert received
    ↓
Investigate (gather evidence)
    ↓
Hypothesize (propose root cause)
    ↓
Verify (confirm hypothesis with additional evidence)
    ↓
[HUMAN APPROVAL GATE]
    ↓ approved
Remediate (apply fix)
    ↓
Report (write postmortem entry, close ticket)
```

Each stage has different tools, different reasoning goals, and different approval requirements. The Hypothesize stage needs the output of Investigate. The Verify stage needs the hypothesis. The Remediate stage needs human approval.

LangGraph represents this as an explicit, stateful graph where nodes are processing steps and edges are conditional transitions. The graph makes the SRE loop visible, debuggable, and modifiable — not implicit in the flow of a loop.

---

## What LangGraph Is

LangGraph is a library from LangChain for building stateful, multi-actor agent applications. It extends LangChain's graph abstractions with:

- **State**: a typed dictionary shared across all nodes
- **Nodes**: functions that take state and return updated state
- **Edges**: transitions between nodes (can be conditional)
- **Checkpointing**: persist graph state between steps (with LangChain checkpointers)
- **Human-in-the-loop**: interrupt the graph at any node for human approval

LangGraph is not magic — it is a structured way to write the same agent logic you would otherwise write as a series of if/else and function calls. The value is: explicit state machine, built-in checkpointing, and standardized human-in-the-loop patterns.

---

## The AOIS SRE Graph

```
              ┌─────────────┐
    alert ──→ │   DETECT    │ ← Classify the alert, decide if investigation needed
              └──────┬──────┘
                     ↓
              ┌─────────────┐
              │ INVESTIGATE │ ← Pull logs, events, metrics (v20 tool calls)
              └──────┬──────┘
                     ↓
              ┌─────────────┐
              │ HYPOTHESIZE │ ← Propose root cause based on evidence
              └──────┬──────┘
                     ↓
              ┌─────────────┐
              │   VERIFY    │ ← Confirm or refute the hypothesis with more evidence
              └──────┬──────┘
                     ↓
              ┌─────────────────┐
              │ [HUMAN APPROVAL] │ ← Graph pauses here; human approves/rejects
              └──────┬──────────┘
                     ↓ (approved)
              ┌─────────────┐
              │  REMEDIATE  │ ← Apply the approved fix (write action — gated)
              └──────┬──────┘
                     ↓
              ┌─────────────┐
              │   REPORT    │ ← Write postmortem entry to Postgres
              └─────────────┘
```

---

## Building the Graph

```python
# langgraph_agent/state.py
"""Shared state for the AOIS SRE graph."""
from typing import TypedDict, Annotated
import operator


class InvestigationState(TypedDict):
    # Input
    incident_description: str
    session_id: str
    agent_role: str

    # Investigation outputs (accumulated)
    evidence: Annotated[list[str], operator.add]  # tool results appended across nodes
    tool_calls: Annotated[list[dict], operator.add]

    # Reasoning outputs
    hypothesis: str
    severity: str
    verified: bool

    # Remediation
    proposed_action: str
    human_approved: bool
    remediation_result: str

    # Final
    report: str
    cost_usd: float
    total_tokens: int
```

```python
# langgraph_agent/nodes.py
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

log = logging.getLogger("langgraph_agent")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * 0.80 + output_tokens * 4.00) / 1_000_000


async def _run_tool(tool_name: str, tool_input: dict, session_id: str) -> str:
    fn_map = {
        "get_pod_logs": get_pod_logs,
        "describe_node": describe_node,
        "list_events": list_events,
        "get_metrics": get_metrics,
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
    return {
        "severity": severity,
        "cost_usd": state.get("cost_usd", 0.0) + cost,
        "total_tokens": state.get("total_tokens", 0) + response.usage.input_tokens + response.usage.output_tokens,
    }


async def investigate_node(state: InvestigationState) -> dict:
    """Gather evidence using tool calls — equivalent to v20 investigator but as a graph node."""
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
    return {
        "hypothesis": hypothesis,
        "proposed_action": proposed_action,
        "cost_usd": state.get("cost_usd", 0.0) + cost,
        "total_tokens": state.get("total_tokens", 0) + response.usage.input_tokens + response.usage.output_tokens,
    }


async def verify_node(state: InvestigationState) -> dict:
    """Confirm or refute the hypothesis with one more targeted evidence pull."""
    log.info("[VERIFY] hypothesis=%s", state.get("hypothesis", "")[:60])
    # Pull one more targeted tool call to verify
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

    # In v23, remediation is simulated (E2B sandbox execution added in v25)
    action = state.get("proposed_action", "")
    result = f"[SIMULATED] Would execute: {action}"
    log.info("Remediation (simulated): %s", action)
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

    return {"report": report_text}
```

```python
# langgraph_agent/graph.py
"""Assemble the AOIS SRE graph and compile it with Postgres checkpointing."""
import asyncpg
import logging
import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph_agent.state import InvestigationState
from langgraph_agent.nodes import (
    detect_node, investigate_node, hypothesize_node,
    verify_node, remediate_node, report_node,
)

log = logging.getLogger("langgraph_agent")


def build_graph() -> StateGraph:
    graph = StateGraph(InvestigationState)

    # Add nodes
    graph.add_node("detect",      detect_node)
    graph.add_node("investigate", investigate_node)
    graph.add_node("hypothesize", hypothesize_node)
    graph.add_node("verify",      verify_node)
    graph.add_node("remediate",   remediate_node)
    graph.add_node("report",      report_node)

    # Linear flow — each node transitions to the next
    graph.set_entry_point("detect")
    graph.add_edge("detect",      "investigate")
    graph.add_edge("investigate", "hypothesize")
    graph.add_edge("hypothesize", "verify")

    # After verify: always go to remediate (human approval gate is inside remediate_node)
    graph.add_edge("verify",      "remediate")
    graph.add_edge("remediate",   "report")
    graph.add_edge("report",      END)

    return graph


async def run_investigation(incident: str, session_id: str,
                             agent_role: str = "read_only") -> dict:
    """
    Run the full AOIS SRE graph for an incident.
    Checkpoints state to Postgres after each node.
    """
    graph = build_graph()

    # Postgres checkpointer — state persisted after each node
    async with await asyncpg.create_pool(os.getenv("DATABASE_URL")) as db:
        checkpointer = AsyncPostgresSaver(db)
        await checkpointer.setup()  # creates the checkpoint tables if needed

        compiled = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["remediate"],  # pause here for human approval
        )

        initial_state = InvestigationState(
            incident_description=incident,
            session_id=session_id,
            agent_role=agent_role,
            evidence=[],
            tool_calls=[],
            hypothesis="",
            severity="P3",
            verified=False,
            proposed_action="",
            human_approved=False,
            remediation_result="",
            report="",
            cost_usd=0.0,
            total_tokens=0,
        )

        config = {"configurable": {"thread_id": session_id}}

        # Run until the interrupt (before remediate)
        log.info("Running graph to approval gate: %s", incident[:60])
        result = await compiled.ainvoke(initial_state, config=config)
        return result


async def approve_and_continue(session_id: str) -> dict:
    """
    Resume the graph after human approval.
    Updates human_approved=True and runs remediate → report.
    """
    graph = build_graph()
    async with await asyncpg.create_pool(os.getenv("DATABASE_URL")) as db:
        checkpointer = AsyncPostgresSaver(db)
        compiled = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["remediate"],
        )
        config = {"configurable": {"thread_id": session_id}}
        # Update state with approval
        await compiled.aupdate_state(
            config,
            {"human_approved": True},
            as_node="verify",
        )
        # Continue from the interrupt
        result = await compiled.ainvoke(None, config=config)
        return result
```

---

## ▶ STOP — do this now

Create the `investigation_reports` table and run the graph to the approval gate:

```bash
# Create the reports table
psql $DATABASE_URL <<'SQL'
CREATE TABLE IF NOT EXISTS investigation_reports (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT UNIQUE NOT NULL,
    incident        TEXT NOT NULL,
    severity        TEXT,
    hypothesis      TEXT,
    proposed_action TEXT,
    human_approved  BOOLEAN DEFAULT FALSE,
    remediation_result TEXT,
    cost_usd        NUMERIC(10, 6),
    report_text     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
SQL
# CREATE TABLE
```

```python
# Run to approval gate
import asyncio, uuid
from langgraph_agent.graph import run_investigation, approve_and_continue

async def main():
    session_id = str(uuid.uuid4())
    incident = "auth-service pod OOMKilled exit code 137 — third time this week"

    print("Running investigation to approval gate...")
    state = await run_investigation(incident, session_id)

    print(f"\nInvestigation paused at human approval gate.")
    print(f"Severity:        {state['severity']}")
    print(f"Hypothesis:      {state['hypothesis'][:200]}")
    print(f"Proposed action: {state['proposed_action']}")
    print(f"Cost so far:     ${state['cost_usd']:.6f}")

    # Human approval
    decision = input("\nApprove remediation? (y/n): ").strip().lower()
    if decision == "y":
        print("Approving and continuing...")
        final_state = await approve_and_continue(session_id)
        print(f"\nReport:\n{final_state['report']}")
    else:
        print("Remediation rejected. Investigation report saved without remediation.")

asyncio.run(main())
```

---

## Dapr Pub/Sub: Portable Messaging Between Graph Nodes

Dapr (Distributed Application Runtime) is a set of building blocks for distributed systems. For v23, the relevant building block is **pub/sub**: nodes publish events to topics, other nodes subscribe. This is more flexible than direct function calls — you can add a monitoring subscriber, a logging subscriber, or a notifications service without changing the graph.

```bash
# Install Dapr CLI
wget -q https://raw.githubusercontent.com/dapr/cli/master/install/install.sh -O - | /bin/bash

# Initialize Dapr locally (installs Redis-backed components)
dapr init

# Python SDK
pip install dapr dapr-ext-fastapi
```

```python
# langgraph_agent/dapr_events.py
"""
Publish graph node events to Dapr pub/sub.
Subscribers (logging, monitoring, notifications) receive these without
any changes to the graph itself.
"""
from dapr.clients import DaprClient
import json
import logging

log = logging.getLogger("dapr_events")
_PUBSUB_NAME = "pubsub"  # Dapr component name (Redis by default in local init)
_TOPIC = "aois-investigation-events"


def publish_node_event(node_name: str, session_id: str, data: dict) -> None:
    """Publish a node completion event to Dapr pub/sub."""
    event = {
        "node": node_name,
        "session_id": session_id,
        "data": data,
    }
    try:
        with DaprClient() as d:
            d.publish_event(
                pubsub_name=_PUBSUB_NAME,
                topic_name=_TOPIC,
                data=json.dumps(event),
                data_content_type="application/json",
            )
        log.info("Published %s event for session %s", node_name, session_id)
    except Exception as e:
        log.warning("Dapr publish failed (non-fatal): %s", e)
```

Add `publish_node_event()` calls at the end of each node function:

```python
# In detect_node():
from langgraph_agent.dapr_events import publish_node_event
publish_node_event("detect", state["session_id"], {"severity": severity})
```

Now any subscriber listening to `aois-investigation-events` (a Prometheus exporter, a Slack notifier, a PagerDuty integration) receives every graph event without any changes to the graph.

---

## ▶ STOP — do this now

Run the full graph with real input, observe all nodes execute, and check the `investigation_reports` table afterward:

```bash
psql $DATABASE_URL -c "
SELECT session_id, severity, human_approved, cost_usd, LEFT(proposed_action, 60) AS action
FROM investigation_reports
ORDER BY created_at DESC LIMIT 5;"
```

If `human_approved=false`: the investigation ran but remediation was not approved or not reached. `cost_usd` should be in the $0.001–$0.005 range for a 4–6 node traversal.

---

## ▶ STOP — do this now

Trace the state evolution through each graph node for a single investigation:

```python
import asyncio
from langgraph_agent.graph import build_graph
from langgraph_agent.state import InvestigationState

async def trace_state_evolution(incident: str):
    """Run the graph and print state after each node."""
    graph = build_graph()
    config = {"configurable": {"thread_id": "trace-001"}}

    # Stream events from each node
    async for event in graph.astream(
        {"incident": incident, "session_id": "trace-001", "human_approved": False},
        config=config,
        stream_mode="values",
    ):
        # event is the full state after each node completes
        severity = event.get("severity", "—")
        evidence_count = len(event.get("evidence", []))
        tool_calls = len(event.get("tool_calls", []))
        hypothesis = event.get("hypothesis", "")[:60]
        cost = event.get("cost_usd", 0)
        print(f"  severity={severity} | evidence={evidence_count} | tools={tool_calls} | cost=${cost:.4f}")
        if hypothesis:
            print(f"    hypothesis: {hypothesis}")

incident = "auth-service OOMKilled exit code 137 — third occurrence this week"
print(f"Tracing: {incident}\n")
asyncio.run(trace_state_evolution(incident))
```

Expected output — watch the state build up as each node adds to it:
```
Tracing: auth-service OOMKilled exit code 137 — third occurrence this week

  severity=P1 | evidence=0 | tools=0 | cost=$0.0002
  severity=P1 | evidence=3 | tools=3 | cost=$0.0018
    hypothesis: auth-service memory limit 512Mi exceeded — likely leak in...
  severity=P1 | evidence=3 | tools=3 | cost=$0.0022
    hypothesis: auth-service allocating cache objects not released — GC pressure
  severity=P1 | evidence=4 | tools=4 | cost=$0.0028
```

Each line is one node completing. The `evidence` count increases as `investigate_node` adds kubectl output. The `cost_usd` accumulates across nodes. The `hypothesis` refines as more evidence comes in.

This trace is the mental model for LangGraph: not a single LLM call, but a state machine where each step adds to shared context and costs accumulate predictably.

---

## Common Mistakes

### 1. State accumulation not using `Annotated[list, operator.add]`

LangGraph merges node outputs into the shared state. Without the `operator.add` annotation, each node's `evidence` output replaces the previous — you lose evidence from earlier nodes.

```python
# Wrong — each node replaces the list
evidence: list[str]

# Correct — each node appends to the list
evidence: Annotated[list[str], operator.add]
```

---

### 2. `interrupt_before` node not triggering

If `interrupt_before=["remediate"]` is set but the graph completes through remediate without pausing:

- The checkpointer is not configured — `graph.compile()` without a checkpointer ignores interrupts
- The `thread_id` in the config is new — interrupts apply to resumed invocations, not first invocations
- Check: `compiled.get_state(config)["next"]` — if `["remediate"]` is present, the interrupt is pending

---

### 3. Checkpointer table not created

```
asyncpg.exceptions.UndefinedTableError: relation "checkpoints" does not exist
```

Run `await checkpointer.setup()` before the first `compiled.ainvoke()`. This creates the LangGraph checkpoint tables in Postgres.

---

## Troubleshooting

### Graph hangs at investigate_node

The LLM call in `investigate_node` is waiting for a response that never comes. Likely causes: API key missing, network issue, or context window exceeded (too much evidence accumulated in a loop).

Add a timeout:

```python
# In investigate_node, wrap the LLM call:
import asyncio
response = await asyncio.wait_for(
    asyncio.to_thread(_client.messages.create, ...),
    timeout=60.0,
)
```

---

### `human_approved` not persisting after `aupdate_state`

The checkpoint must be read from the correct `thread_id`. If `approve_and_continue` uses a different session_id than `run_investigation`, it reads a different (or absent) checkpoint.

Confirm the session_id is consistent across both calls.

---

## Connection to Later Phases

### To v23.5 (Agent Evaluation)
The graph makes evaluation straightforward: for a given incident input, run the graph and compare the sequence of nodes traversed (Detect → Investigate → Hypothesize → ...) to the expected sequence. Compare `proposed_action` to ground truth. LangGraph's checkpointing gives you the full state at each step for offline analysis.

### To v25 (E2B Sandboxed Execution)
The `remediate_node` currently simulates the fix. In v25, it calls E2B to execute the proposed fix in a sandbox, validates the result, and only marks the remediation as successful if the sandbox confirms the fix works. The gate is already in place (human_approved=True required).

### To v34.5 (Capstone)
The full SRE loop — Detect → Investigate → Hypothesize → Verify → (human approval) → Remediate → Report — is the capstone's automated response pipeline. The game day in v34.5 runs this loop against real failures and measures MTTR. The loop is complete in v23. The capstone validates it at scale.

---


## Build-It-Blind Challenge

Close the notes. From memory: write the LangGraph `detect` node — it receives `AgentState`, calls the classify function, sets `severity` and `confidence` on the state, and returns the updated state dict. Write the conditional edge logic that routes to `investigate` for P1/P2 and `report` for P3/P4. 20 minutes.

```python
result = graph.invoke({"log_entry": "auth-service OOMKilled"})
print(result["severity"])      # P1 or P2
print(result["next_action"])   # "investigate"
```

---

## Failure Injection

Create a cycle in the graph by pointing an edge back to an earlier node and run it:

```python
builder.add_edge("investigate", "detect")   # loop back
```

LangGraph should detect this or run indefinitely. What happens? Then remove the cycle and introduce a wrong state key:

```python
def detect(state: AgentState) -> dict:
    return {"sevrity": "P1"}   # typo — 'sevrity' not 'severity'
```

The graph runs without error but the severity is never set. This is the silent state mutation bug that makes agent graphs hard to debug — the node ran, the graph advanced, but the state is wrong.

---

## Osmosis Check

1. The LangGraph agent calls `get_pod_logs` via the `@gated_tool` decorator (v20). The OPA policy checks `incident_id` for rate limiting. If the LangGraph `investigate` node calls `get_pod_logs` 15 times in one investigation (normal for complex incidents), does the circuit breaker (v20) fire? What is the correct threshold for a multi-call investigation?
2. Dapr pub/sub connects LangGraph nodes across services. Node A runs in the AOIS pod. Node B runs in a separate metrics-analyzer pod. The Dapr message between them has a TTL of 30 seconds. Node B is restarting due to a pod kill (v19 chaos). What happens to the message and the in-flight investigation?

---

## Mastery Checkpoint

1. Create the `investigation_reports` table. Run the graph to the approval gate for a real incident. Confirm the graph pauses before `remediate_node` (does not execute remediation).

2. Approve the remediation and run `approve_and_continue()`. Confirm the `remediation_result` field in the report shows `[SIMULATED] Would execute: ...`.

3. Query `investigation_reports` after 3 runs. Confirm `session_id`, `severity`, `cost_usd`, and `report_text` are populated correctly for each.

4. Modify the graph to add a `notify` node after `report` that logs the report to stdout. Add the edge. Rerun — confirm the new node executes.

5. Introduce a deliberate error in `hypothesize_node` (raise an exception). Observe the graph error and the checkpoint state. Fix the error. Rerun the same session_id — does the graph resume from `hypothesize` or restart from `detect`? (It restarts from detect — the checkpoint stores completed node outputs, not mid-node state.)

6. Explain to a non-technical person the purpose of the human approval gate — why a fully autonomous system that also needs human approval is not a contradiction.

7. Explain to a junior engineer the difference between LangGraph's `interrupt_before` and the Phase 7 gate's kill switch. What does each protect against?

8. Explain to a senior engineer: when is a LangGraph graph the right architecture, and when is a flat loop (v20) sufficient? What is the cost of the added complexity?

**The mastery bar:** you can run the full SRE loop (Detect → Investigate → Hypothesize → Verify → human approval → Remediate → Report) against a real incident, pause it for human review, approve it, and produce a report in `investigation_reports` — all from one incident description.

---

## 4-Layer Tool Understanding

### LangGraph

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | A flat agent loop does not tell you where in the investigation you are. LangGraph makes the investigation a visible map — Detect, Investigate, Hypothesize, Verify, Remediate, Report — so you can see the current step, pause at specific points for human review, and debug exactly which step failed. |
| **System Role** | Where does it sit in AOIS? | LangGraph wraps the investigation logic that was a flat loop in v20. Each investigation stage is a named node. The graph coordinates their execution order, state sharing, and checkpointing. Temporal (v22) handles durability; LangGraph handles structure. |
| **Technical** | What is it, precisely? | A Python library for building stateful agent graphs using a typed state dictionary and a DAG (directed acyclic graph) of node functions. State is shared across all nodes via the `InvestigationState` TypedDict. Node outputs are merged into state using reducer functions (`operator.add` for lists). Checkpointers persist state after each node. `interrupt_before` pauses the graph at specified nodes for human-in-the-loop. |
| **Remove it** | What breaks, and how fast? | Remove LangGraph → investigation is a flat loop again (v20). The SRE lifecycle stages (Hypothesize, Verify, Remediate, Report) collapse into one undifferentiated function. Human approval is harder to implement correctly. Debugging which stage failed in a complex multi-step investigation becomes guesswork. |

### Dapr (Pub/Sub)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | If the investigation graph needs to notify Slack, update a dashboard, and log to an audit system — all at once — you do not want to hardcode all three in the graph. Dapr pub/sub lets the graph publish one event, and any number of subscribers receive it independently. |
| **System Role** | Where does it sit in AOIS? | Dapr runs as a sidecar alongside the AOIS agent. Graph nodes call `publish_node_event()` which sends to a Dapr pub/sub topic (`aois-investigation-events`). Subscribers (notification service, monitoring agent) listen on the topic without any code changes to the graph. |
| **Technical** | What is it, precisely? | A portable pub/sub abstraction. Dapr components define the backing message broker (Redis for local dev, Kafka in production). The Python SDK publishes to a topic; any subscribed service receives the message via HTTP callback or gRPC. Message broker can be swapped by changing the Dapr component YAML without changing application code. |
| **Remove it** | What breaks, and how fast? | Remove Dapr → each notification (Slack, PagerDuty, monitoring) is a direct call inside the graph. Adding a new notification requires changing the graph. Graph nodes become coupled to external services. Recovery from a failed notification (Slack down) either silently drops the notification or crashes the graph. |
