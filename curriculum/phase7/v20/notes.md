# v20 — Claude Tool Use + Agent Memory: AOIS Sees and Remembers

⏱ **Estimated time: 6–8 hours**

---

## Prerequisites

Phase 7 gate built and tested. Claude API key available.

```bash
# Gate policy evaluates correctly
echo '{"tool_name":"get_pod_logs","agent_role":"read_only","human_approved":false}' | \
  opa eval --data agent_gate/policy.rego --input /dev/stdin --format json "data.aois.agent.allow" | \
  jq '.result[0].expressions[0].value'
# true

# Kill switch is clear
python3 -c "from agent_gate.kill_switch import is_halted; print('halted:', is_halted())"
# halted: False

# Claude API key works
python3 -c "import anthropic, os; c=anthropic.Anthropic(); r=c.messages.create(model='claude-haiku-4-5-20251001',max_tokens=10,messages=[{'role':'user','content':'hi'}]); print('ok')"
# ok

# Redis is up
redis-cli ping
# PONG
```

---

## Learning Goals

By the end you will be able to:

- Explain what Claude tool use is and how it differs from a prompt that asks Claude to use tools
- Define tools using Anthropic's JSON schema format and wire them to Python functions
- Build a multi-turn agent loop that calls tools until Claude decides the investigation is complete
- Integrate the Phase 7 gate into every tool call so the capability boundary is enforced automatically
- Implement persistent agent memory with Mem0 so AOIS remembers past investigations across sessions
- Detect and reject memory poisoning attempts from crafted log events
- Track per-incident LLM cost across all tool calls in one investigation session
- Explain the difference between short-term memory (current session context) and long-term memory (Mem0)

---

## The Problem This Solves

AOIS in v19 analyzes what it is given. You provide the log; it provides the assessment. The investigation is as good as the context you hand it.

A real SRE does not wait for someone to hand them the logs. When an OOMKilled alert fires, they: pull the pod logs, check the node state, look at recent events, pull the metrics for the last hour, search their notes for similar past incidents, then form a hypothesis. AOIS in v20 does the same.

The mechanism: **tool use** (Claude decides which tools to call, in what order, with what arguments) + **persistent memory** (Mem0 stores the outcome of each investigation so the next one benefits from it).

---

## How Claude Tool Use Works

Tool use in the Anthropic API is not prompt injection — you do not write "if you need data, use `get_pod_logs()`" in the system prompt. It is a structured API feature:

1. You define tools as JSON schemas and pass them to the API
2. Claude reads the current conversation and decides whether to call a tool
3. If Claude calls a tool, the API returns a `tool_use` content block (not text)
4. You execute the tool in Python and return the result as a `tool_result` message
5. Claude reads the tool result and either calls another tool or produces a final response

The key insight: **Claude never executes code**. Claude decides *what* to call and *with what arguments*. Your Python code executes it. This means every tool call passes through your gate before anything happens.

```
User: "Why is the auth service slow?"
        ↓
Claude: [tool_use: get_pod_logs(namespace="auth", pod="auth-*")]
        ↓
Your code: gate.check_tool() → circuit_breaker.record_call() → kubectl logs auth-...
        ↓
Claude: [tool_use: get_metrics(service="auth", window="1h")]
        ↓
Your code: gate.check_tool() → kubectl top pods -n auth
        ↓
Claude: "Based on the logs and metrics, the auth service is slow because..."
```

---

## Defining the AOIS Investigative Tools

```python
# agent/tools/definitions.py
"""
Tool definitions in Anthropic JSON schema format.
These are passed directly to the Claude API — not executed here.
"""

TOOL_DEFINITIONS = [
    {
        "name": "get_pod_logs",
        "description": (
            "Retrieve recent logs from a Kubernetes pod. Use this when you need to understand "
            "what a pod is doing, why it crashed, or what errors it is producing. "
            "Returns the last N lines of logs from the specified pod."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace (e.g. 'aois', 'kafka', 'default')"
                },
                "pod_name": {
                    "type": "string",
                    "description": "Pod name or prefix (e.g. 'auth-service', 'aois-*'). "
                                   "Wildcards are supported."
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to retrieve (default: 100, max: 500)",
                    "default": 100
                },
                "container": {
                    "type": "string",
                    "description": "Container name within the pod (optional, defaults to first container)"
                }
            },
            "required": ["namespace", "pod_name"]
        }
    },
    {
        "name": "describe_node",
        "description": (
            "Get detailed information about a Kubernetes node, including resource usage, "
            "conditions, and pod count. Use this to investigate node-level issues like "
            "disk pressure, memory pressure, or CPU overcommit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": "Node name (e.g. 'aois'). Use 'all' to list all nodes."
                }
            },
            "required": ["node_name"]
        }
    },
    {
        "name": "list_events",
        "description": (
            "List recent Kubernetes events for a namespace or specific resource. "
            "Events show what the control plane has done: pod scheduling, image pulls, "
            "OOMKills, liveness probe failures, etc. Use this to understand what happened "
            "leading up to an incident."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace to query events for"
                },
                "resource_name": {
                    "type": "string",
                    "description": "Optional: filter events to a specific resource name"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of events to return (default: 20)",
                    "default": 20
                }
            },
            "required": ["namespace"]
        }
    },
    {
        "name": "get_metrics",
        "description": (
            "Query current resource usage (CPU, memory) for pods or nodes. "
            "Use this to confirm whether a pod is approaching its resource limits "
            "or whether a node is under pressure. Requires metrics-server."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to query metrics for"
                },
                "resource_type": {
                    "type": "string",
                    "enum": ["pods", "nodes"],
                    "description": "Whether to query pod or node metrics"
                }
            },
            "required": ["namespace", "resource_type"]
        }
    },
    {
        "name": "search_past_incidents",
        "description": (
            "Search AOIS incident history for similar past incidents. "
            "Use this early in any investigation to check if this problem has been seen before "
            "and what resolved it. Returns the top 3 most similar past incidents with their "
            "root causes and resolutions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Description of the current incident to search for"
                }
            },
            "required": ["query"]
        }
    },
]
```

---

## Implementing the Tools

```python
# agent/tools/k8s.py
"""
Kubernetes investigative tools for AOIS agents.
All functions are decorated with @gated_tool — they enforce the capability
boundary before any kubectl command runs.
"""
import subprocess
import json
import logging
from agent_gate.enforce import gated_tool, ToolBlocked

log = logging.getLogger("agent.tools.k8s")

KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"


def _kubectl(*args) -> str:
    """Run a kubectl command and return stdout. Raises on non-zero exit."""
    cmd = ["sudo", "kubectl", "--kubeconfig", KUBECONFIG] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return f"kubectl error: {result.stderr.strip()}"
    return result.stdout.strip()


@gated_tool(agent_role="read_only")
async def get_pod_logs(namespace: str, pod_name: str, lines: int = 100,
                       container: str = "", session_id: str = "default") -> str:
    lines = min(lines, 500)  # hard cap regardless of what Claude requests
    args = ["logs", "-n", namespace, f"--selector=app={pod_name}", f"--tail={lines}"]
    if container:
        args += ["-c", container]
    return _kubectl(*args) or f"No logs found for {pod_name} in {namespace}"


@gated_tool(agent_role="read_only")
async def describe_node(node_name: str, session_id: str = "default") -> str:
    if node_name == "all":
        return _kubectl("get", "nodes", "-o", "wide")
    return _kubectl("describe", "node", node_name)


@gated_tool(agent_role="read_only")
async def list_events(namespace: str, resource_name: str = "",
                      limit: int = 20, session_id: str = "default") -> str:
    args = ["get", "events", "-n", namespace,
            "--sort-by=.lastTimestamp", f"--field-selector=involvedObject.name={resource_name}"]
    if not resource_name:
        args = ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]
    output = _kubectl(*args)
    lines = output.split("\n")
    return "\n".join(lines[-limit:])  # most recent N events


@gated_tool(agent_role="read_only")
async def get_metrics(namespace: str, resource_type: str = "pods",
                      session_id: str = "default") -> str:
    if resource_type == "nodes":
        return _kubectl("top", "nodes")
    return _kubectl("top", "pods", "-n", namespace)
```

```python
# agent/tools/rag_tool.py
"""RAG-backed past incident search tool."""
import asyncpg
import os
from agent_gate.enforce import gated_tool
from rag.aois_rag import retrieve_context

_db_pool = None


async def _get_pool():
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    return _db_pool


@gated_tool(agent_role="read_only")
async def search_past_incidents(query: str, session_id: str = "default") -> str:
    db = await _get_pool()
    context = await retrieve_context(db, query, k_candidates=10, top_k=3)
    return context if context else "No similar past incidents found."
```

---

## The Agent Loop

```python
# agent/investigator.py
"""
AOIS investigative agent using Claude tool use.
Runs a multi-turn loop until Claude produces a final text response (no more tool calls).
"""
import anthropic
import json
import logging
import os
import time
import uuid
from typing import Any

from agent.tools.k8s import get_pod_logs, describe_node, list_events, get_metrics
from agent.tools.rag_tool import search_past_incidents
from agent.tools.definitions import TOOL_DEFINITIONS
from agent_gate.enforce import ToolBlocked
from clickhouse.writer import write_incident

log = logging.getLogger("agent.investigator")

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Map tool name → Python function
_TOOL_MAP = {
    "get_pod_logs":         get_pod_logs,
    "describe_node":        describe_node,
    "list_events":          list_events,
    "get_metrics":          get_metrics,
    "search_past_incidents": search_past_incidents,
}

AGENT_SYSTEM_PROMPT = """You are AOIS, an autonomous SRE investigation agent.

When given an incident alert, you MUST:
1. First call search_past_incidents to check if this has been seen before
2. Pull relevant logs and events to gather evidence
3. Check metrics if resource pressure is suspected
4. Form a hypothesis based on the evidence you collected — not assumptions
5. Provide a structured response: severity, root_cause, evidence_summary, recommended_action

Rules:
- Never recommend destructive actions (delete, rm -rf, drop)
- Always cite specific evidence from the tools you called
- If evidence is insufficient, say so and recommend what additional data is needed
- Confidence must be based on evidence quality, not optimism
"""


async def investigate(incident_description: str,
                      agent_role: str = "read_only",
                      session_id: str | None = None) -> dict:
    """
    Run a full investigation for an incident description.
    Returns the investigation result with full tool call trace.
    """
    session_id = session_id or str(uuid.uuid4())
    t0 = time.time()
    total_input_tokens = total_output_tokens = 0
    tool_calls_made: list[dict] = []

    messages = [{"role": "user", "content": incident_description}]

    # Inject session_id into all tool calls via a closure
    def make_tool_caller(fn, sid):
        async def caller(**kwargs):
            return await fn(**kwargs, session_id=sid)
        return caller

    tool_functions = {
        name: make_tool_caller(fn, session_id)
        for name, fn in _TOOL_MAP.items()
    }

    max_iterations = 10  # safety limit — circuit breaker is the real limit
    for iteration in range(max_iterations):
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",  # fast + cheap for tool-heavy loops
            max_tokens=4096,
            system=AGENT_SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        total_input_tokens  += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # If Claude is done (no tool calls), extract the final response
        if response.stop_reason == "end_turn":
            final_text = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            total_latency_ms = int((time.time() - t0) * 1000)
            cost_usd = (total_input_tokens * 0.80 + total_output_tokens * 4.00) / 1_000_000

            # Write to ClickHouse
            write_incident(
                request_id=str(uuid.uuid4()),
                incident_id=session_id,
                model="claude-haiku-4-5-20251001",
                tier="premium",
                severity=_extract_severity(final_text),
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                cost_usd=cost_usd,
                cache_hit=False,
                latency_ms=total_latency_ms,
                confidence=0.85,
                pii_detected=False,
            )

            log.info("Investigation complete: session=%s iterations=%d cost=$%.6f",
                     session_id, iteration + 1, cost_usd)

            return {
                "session_id": session_id,
                "incident": incident_description,
                "investigation": final_text,
                "tool_calls": tool_calls_made,
                "iterations": iteration + 1,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "cost_usd": round(cost_usd, 6),
                "latency_ms": total_latency_ms,
            }

        # Process tool calls
        tool_results = []
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input

            log.info("Tool call: %s(%s) session=%s", tool_name, tool_input, session_id)
            tool_calls_made.append({"tool": tool_name, "input": tool_input})

            fn = tool_functions.get(tool_name)
            if not fn:
                result_text = f"Unknown tool: {tool_name}"
            else:
                try:
                    result_text = await fn(**tool_input)
                except ToolBlocked as e:
                    result_text = f"[TOOL BLOCKED by gate: {e}]"
                    log.warning("Tool blocked: %s — %s", tool_name, e)
                except Exception as e:
                    result_text = f"[Tool error: {e}]"
                    log.error("Tool error: %s — %s", tool_name, e)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result_text)[:4000],  # cap to avoid context bloat
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
    import re
    m = re.search(r'P[1-4]', text)
    return m.group(0) if m else "P3"
```

---

## ▶ STOP — do this now

Run a live investigation against the Hetzner cluster:

```python
# From project root:
import asyncio
from agent.investigator import investigate

async def main():
    result = await investigate(
        "The AOIS Kafka consumer appears to be processing logs slower than expected. "
        "Check the consumer pods, recent events, and metrics.",
        agent_role="read_only",
    )
    print(f"\nInvestigation complete:")
    print(f"  Tool calls: {len(result['tool_calls'])}")
    print(f"  Iterations: {result['iterations']}")
    print(f"  Cost: ${result['cost_usd']:.6f}")
    print(f"\nFindings:\n{result['investigation']}")

asyncio.run(main())
```

Expected output pattern:
```
Tool call: search_past_incidents({'query': 'Kafka consumer slow processing'})
Tool call: get_pod_logs({'namespace': 'aois', 'pod_name': 'aois', 'lines': 100})
Tool call: list_events({'namespace': 'kafka', 'limit': 20})
Tool call: get_metrics({'namespace': 'aois', 'resource_type': 'pods'})

Investigation complete:
  Tool calls: 4
  Iterations: 5
  Cost: $0.000187

Findings:
Based on my investigation, severity is P3...
```

If `ToolBlocked` appears in the output, the gate is working — Claude tried to call something outside the read_only allowlist and was blocked before execution.

---

## Persistent Memory with Mem0

Without memory, every investigation starts cold. AOIS cannot say "I remember this OOMKilled pattern from last Tuesday." Mem0 adds a persistent memory layer that AOIS reads at the start of each investigation and writes to at the end.

```bash
pip install mem0ai
```

```python
# agent/memory.py
"""
Persistent agent memory via Mem0.
Wraps Mem0 with memory poisoning detection.
"""
import logging
import re
from mem0 import Memory

log = logging.getLogger("agent.memory")

# Mem0 config — uses local vector store by default (no separate service needed)
_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": "localhost",
            "port": 6333,
            "collection_name": "aois_agent_memory",
        }
    },
    "llm": {
        "provider": "anthropic",
        "config": {
            "model": "claude-haiku-4-5-20251001",
            "api_key": None,  # reads from ANTHROPIC_API_KEY env var
        }
    }
}

_mem0 = Memory.from_config(_config)

# ─────────────────────────────────────────────────────────
# Memory poisoning detection
# Crafted log events can embed instructions that cause AOIS
# to store false memories ("deleting the namespace fixed it").
# ─────────────────────────────────────────────────────────
_POISON_PATTERNS = [
    re.compile(r'remember\s+that', re.IGNORECASE),
    re.compile(r'store\s+in\s+memory', re.IGNORECASE),
    re.compile(r'next\s+time\s+you\s+see', re.IGNORECASE),
    re.compile(r'always\s+(run|execute|do|call)', re.IGNORECASE),
    re.compile(r'forget\s+(everything|all|previous)', re.IGNORECASE),
    re.compile(r'your\s+new\s+(instruction|rule|behavior)', re.IGNORECASE),
    re.compile(r'overwrite\s+(memory|previous)', re.IGNORECASE),
]

_DANGEROUS_CONTENT = [
    re.compile(r'delete\s+(namespace|cluster|volume|pv)', re.IGNORECASE),
    re.compile(r'kubectl\s+delete', re.IGNORECASE),
    re.compile(r'rm\s+-rf', re.IGNORECASE),
    re.compile(r'drop\s+table', re.IGNORECASE),
]


def _is_poisoned(text: str) -> tuple[bool, str]:
    """
    Detect potential memory poisoning in text before storing it.
    Returns (is_poisoned, reason).
    """
    for pattern in _POISON_PATTERNS:
        if pattern.search(text):
            return True, f"injection pattern detected: {pattern.pattern}"
    for pattern in _DANGEROUS_CONTENT:
        if pattern.search(text):
            return True, f"dangerous content detected: {pattern.pattern}"
    return False, ""


def store_investigation(session_id: str, incident: str, resolution: str,
                        severity: str, root_cause: str) -> None:
    """
    Store an investigation outcome to persistent memory.
    Checks for poisoning before writing.
    """
    memory_text = (
        f"Incident: {incident}\n"
        f"Severity: {severity}\n"
        f"Root cause: {root_cause}\n"
        f"Resolution: {resolution}"
    )
    poisoned, reason = _is_poisoned(memory_text)
    if poisoned:
        log.warning("Memory poisoning detected — write rejected: %s", reason)
        return

    _mem0.add(memory_text, user_id="aois-agent", metadata={
        "session_id": session_id,
        "severity": severity,
    })
    log.info("Stored investigation to memory: session=%s severity=%s", session_id, severity)


def recall_relevant(query: str, limit: int = 5) -> str:
    """
    Retrieve relevant past memories for a given query.
    Returns formatted string for injection into the agent context.
    """
    results = _mem0.search(query, user_id="aois-agent", limit=limit)
    if not results:
        return ""
    lines = ["## Agent Memory: Relevant Past Investigations\n"]
    for r in results:
        lines.append(f"- {r['memory']}")
        lines.append(f"  (score: {r['score']:.3f})\n")
    return "\n".join(lines)
```

### Using memory in the agent loop

At the start of `investigate()`, retrieve relevant memories and prepend to the system prompt:

```python
# In investigator.py, at the start of investigate():
from agent.memory import recall_relevant, store_investigation

# Retrieve relevant past memories
past_memory = recall_relevant(incident_description)
system = AGENT_SYSTEM_PROMPT
if past_memory:
    system += f"\n\n{past_memory}"

# ... run investigation ...

# At the end, after final_text is produced:
store_investigation(
    session_id=session_id,
    incident=incident_description,
    resolution=final_text,
    severity=_extract_severity(final_text),
    root_cause="see investigation above",
)
```

---

## ▶ STOP — do this now

Test memory persistence across two investigations:

```python
import asyncio
from agent.investigator import investigate
from agent.memory import recall_relevant

async def main():
    # First investigation
    r1 = await investigate(
        "auth-service pod OOMKilled exit code 137 — memory limit 512Mi",
        agent_role="read_only",
        session_id="test-001"
    )
    print("Investigation 1 complete. Memory stored.")

    # Check what was stored
    memory = recall_relevant("auth service OOMKilled memory")
    print(f"\nRecalled memory:\n{memory}")

    # Second investigation on same pattern — should recall first
    r2 = await investigate(
        "auth-service OOMKilled again — same pod, same namespace",
        agent_role="read_only",
        session_id="test-002"
    )
    print("\nInvestigation 2 complete.")
    print("Did AOIS mention the previous incident? Check the 'investigation' field.")

asyncio.run(main())
```

In the second investigation, AOIS should open with a reference to the previous occurrence — "I've seen this pattern before" — because `recall_relevant` found the memory from session test-001 and injected it into the system prompt.

---

## Per-Incident Cost Attribution

From CLAUDE.md, this is required at v20: every investigation must track total cost across all LLM calls, not just per-call.

The `investigate()` function already does this: `total_input_tokens` and `total_output_tokens` accumulate across all Claude calls in the loop. At the end, a single ClickHouse row records the full investigation cost.

```python
# After a completed investigation:
print(f"Investigation cost breakdown:")
print(f"  Input tokens:  {result['total_input_tokens']:,}")
print(f"  Output tokens: {result['total_output_tokens']:,}")
print(f"  Total calls:   {result['iterations']} LLM rounds")
print(f"  Tool calls:    {len(result['tool_calls'])}")
print(f"  Total cost:    ${result['cost_usd']:.6f}")
# Investigation cost breakdown:
#   Input tokens:  4,821
#   Output tokens: 687
#   Total calls:   5 LLM rounds
#   Tool calls:    4
#   Total cost:    $0.000659
```

This is the metric that gets an agent approved for production: "each P2 investigation costs $0.001 and takes 8 seconds. Human on-call costs $300/hour and takes 15 minutes." The number makes the case.

---

## ▶ STOP — do this now

Verify that Mem0 memory persists across sessions and changes AOIS behavior:

```python
import asyncio
from agent.memory import AoisMemory

memory = AoisMemory()

# Session 1: store a past incident resolution
asyncio.run(memory.store(
    session_id="session-001",
    incident="auth-service OOMKilled exit code 137",
    resolution="Increased memory limit from 512Mi to 1Gi — resolved immediately",
    severity="P1",
))

# Session 2 (simulate new session): retrieve memory during investigation
similar = asyncio.run(memory.retrieve("auth-service memory pressure"))
print(f"Retrieved {len(similar)} similar past incidents:")
for m in similar:
    print(f"  [{m.get('severity','?')}] {m.get('incident','')[:60]}")
    print(f"    Resolution: {m.get('resolution','')[:80]}")
```

Expected output:
```
Retrieved 1 similar past incidents:
  [P1] auth-service OOMKilled exit code 137
    Resolution: Increased memory limit from 512Mi to 1Gi — resolved immediately
```

Now verify the investigator uses this memory during analysis:

```python
from agent.investigator import investigate_incident

result = asyncio.run(investigate_incident(
    incident="auth-service OOMKilled again — same pod, same namespace",
    session_id="session-002",
))
# The hypothesis should reference the past incident and resolution
print("Hypothesis:", result.get("hypothesis", ""))
# Expected: mentions previous OOMKill and suggests checking memory limits first
```

This is the difference between an agent that starts cold every time and one that learns from incident history. Without Mem0, every OOMKill investigation starts from scratch. With Mem0, the second occurrence surfaces the previous resolution immediately.

---

## Common Mistakes

### 1. Calling `get_pod_logs` with the full pod name including hash

```python
# Claude often generates: pod_name="aois-7d6b4f8c9-xkj2p"
# The kubectl --selector flag expects the app label, not the full pod name
# Fix: use a label selector pattern in the tool implementation:
args = ["logs", "-n", namespace, f"--selector=app={pod_name}", f"--tail={lines}"]

# If the full pod name is passed, fall back to direct:
if "-" in pod_name and len(pod_name) > 20:  # looks like a full pod name
    args = ["logs", "-n", namespace, pod_name, f"--tail={lines}"]
```

---

### 2. Tool result too large for context

Claude's context window is large but not unlimited. If `get_pod_logs` returns 10,000 lines, the context fills quickly and costs multiply.

Hard-cap every tool result:
```python
"content": str(result_text)[:4000],  # 4000 chars ≈ 800–1000 tokens
```

If a tool returns more useful data than 4000 chars, the tool implementation should pre-filter (tail -50 for logs, sort by timestamp and take recent events only).

---

### 3. Mem0 writing to memory on every call

Memory should capture *outcomes* (what was the root cause, what fixed it), not *process* (every tool call result). If you call `store_investigation` inside the tool loop, you write noisy in-progress data.

Only call `store_investigation` once, at the end, after `final_text` is produced.

---

### 4. Missing `session_id` propagation to gated tools

The gate's circuit breaker tracks calls by `session_id`. If `session_id` is not passed, all calls bucket into the "default" session — the breaker trips immediately when two different investigations are running simultaneously.

Every tool call must pass `session_id`. The `make_tool_caller` closure in `investigator.py` handles this: it binds `session_id` into every tool function before it is called.

---

## Troubleshooting

### `ToolBlocked: Capability boundary: tool 'X' is not in the allowed set`

Claude tried to call a tool that is not in the `read_only_tools` set in `policy.rego`. Two causes:

1. **The tool definition is in TOOL_DEFINITIONS but not in policy.rego**: add it to the appropriate role set in the Rego policy
2. **Claude hallucinated a tool name**: check the tool call name against TOOL_DEFINITIONS — if it does not match exactly, Claude invented a tool that does not exist

---

### Mem0 `ConnectionRefused` on Qdrant

Mem0's Qdrant config points to `localhost:6333`. If Qdrant is not running:

```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:v1.9.0
# From v3.5 — same Qdrant instance, different collection
```

Mem0 creates its own collection (`aois_agent_memory`) in the same Qdrant instance as the RAG incident store. They coexist without conflict.

---

### Investigation stuck in loop (never reaches `end_turn`)

Claude keeps calling tools without producing a final text response. Causes:

1. Tool results are empty — Claude keeps trying different tools to gather evidence
2. Tool results contain errors — Claude tries to investigate the error instead of the original incident

Add the max_iterations safety limit (already in the implementation: 10). Check tool output quality — empty kubectl results indicate the pod name or namespace is wrong.

---

## Connection to Later Phases

### To v21 (MCP + A2A)
The tools built in v20 (`get_pod_logs`, `describe_node`, etc.) become MCP tools in v21. The AOIS agent is exposed as an MCP server — Claude.ai and Cursor can invoke the same tools that the autonomous agent uses. The `@gated_tool` decorator applies in both contexts.

### To v22 (Temporal)
The `investigate()` function is a workflow. In v22, it runs inside a Temporal workflow with durable state — a 10-minute investigation survives pod restarts. The tool calls become Temporal activities; the circuit breaker state moves from Redis to Temporal's workflow state.

### To v23 (LangGraph)
The multi-turn loop in `investigator.py` is a flat while-loop. LangGraph in v23 makes it a stateful graph: Detect → Investigate → Hypothesize → Verify → (await human approval) → Remediate → Report. The tools are identical; the state machine adds structure.

### To v23.5 (Agent Evaluation)
`tool_calls` in the investigation result is the trace. In v23.5, you run the same incident through the agent, compare `tool_calls` to a ground truth trace (expected: search_past_incidents first, then get_pod_logs, then get_metrics), and score correctness. Cost attribution from v20 is the primary metric.

---


## Build-It-Blind Challenge

Close the notes. From memory: write the `get_pod_logs` tool definition — correct tool schema with `namespace` and `pod_name` parameters, the implementation that calls `kubectl logs`, the `@gated_tool` decorator that checks OPA policy before execution. 20 minutes.

```python
result = await get_pod_logs(namespace="aois", pod_name="aois-abc123")
print(type(result))  # str — the logs
# OPA policy was checked before kubectl ran
```

---

## Failure Injection

Call a tool without the `@gated_tool` decorator and test whether the circuit breaker still fires:

```python
# Remove @gated_tool from get_pod_logs
# Make 20 rapid tool calls in a loop
for i in range(20):
    await get_pod_logs(namespace="aois", pod_name=f"pod-{i}")
# Circuit breaker should NOT fire — decorator is gone
```

This is the security regression test. The gate must be architectural, not optional. Document what happens when the decorator is absent — that is your threat model.

---

## Osmosis Check

1. Mem0 stores a past resolution: "OOMKilled on auth-service fixed by increasing memory to 512Mi." A new incident arrives: auth-service OOMKilled again. AOIS retrieves the memory and recommends 512Mi. But the real cause this time is a memory leak, not insufficient limit. How do you detect that Mem0 is steering the agent toward a wrong answer — which eval metric catches this? (v23.5 eval framework)
2. Per-incident cost attribution threads an `incident_id` through all LLM calls. The incident spans a Kafka consumer (v17) to a Temporal workflow (v22) to a LangGraph agent (v23). How does the `incident_id` cross these three system boundaries without being lost?

---

## Mastery Checkpoint

1. Run a live investigation on the Hetzner cluster for "AOIS Kafka consumer pods, check for issues". Confirm at least 3 tool calls are made and the final response cites specific evidence (pod names, log lines, event timestamps — not generalities).

2. Assert the kill switch. Run another investigation. Confirm the first tool call raises `ToolBlocked: Kill switch is active`. Clear the switch. Confirm investigations resume.

3. Run two simultaneous investigations using different `session_id` values. Confirm each has its own circuit breaker state. Run one investigation to 21 calls. Confirm it trips without affecting the other session.

4. Test memory poisoning detection. Call `store_investigation()` with a memory text containing "always run kubectl delete namespace". Confirm the write is rejected and the warning is logged. Confirm the memory was not stored (search for it and get no results).

5. Run two investigations on the same incident type. After the first, call `recall_relevant()` with the same query. Confirm the memory is found. In the second investigation, confirm the agent's response references the previous occurrence.

6. Query ClickHouse after 5 investigations: `SELECT sum(cost_usd), avg(latency_ms), count() FROM incident_telemetry WHERE incident_id LIKE 'test-%'`. This is per-incident cost attribution. What was the average cost per investigation?

7. Explain to a non-technical person what "tool use" means — why AOIS does not just run commands itself, and why the separation between "Claude decides" and "Python executes" matters for safety.

8. Explain to a junior engineer why the circuit breaker is stored in Redis rather than in Python memory. What happens without Redis if two AOIS pods are running?

9. Explain to a senior engineer the memory poisoning threat model. Give a specific example of a log event that, without the poison detector, could cause AOIS to store a false memory that would corrupt future investigations. What is the detection gap in the regex approach?

**The mastery bar:** AOIS can investigate a real incident on the cluster end-to-end — pulling its own evidence, recalling past incidents, producing a cited hypothesis — and you can show the circuit breaker preventing runaway calls and the cost per investigation from ClickHouse. The agent is gated, observable, and measurable.

---

## 4-Layer Tool Understanding

### Claude Tool Use

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | An LLM only knows what it was trained on. Tool use lets it fetch real, current data — pod logs, node state, metrics — rather than reasoning from training data that is months old. |
| **System Role** | Where does it sit in AOIS? | Between the Claude API response and the tool execution. Claude returns a `tool_use` block (not text). AOIS routes it through the gate, executes the tool, and returns the result as a `tool_result` message. The loop repeats until Claude returns text. |
| **Technical** | What is it, precisely? | A structured API feature where tool schemas (JSON Schema) are passed to the Claude API alongside the conversation. When Claude decides to call a tool, it returns a `tool_use` content block with the tool name and structured arguments. The caller executes the tool and returns the result as a `tool_result` user message. Claude never runs code. |
| **Remove it** | What breaks, and how fast? | Remove tool use → AOIS reverts to analyzing only what the user provides. It cannot investigate — it can only assess. Every alert requires a human to gather and paste the relevant logs, metrics, and events before AOIS adds value. The autonomous investigation capability disappears entirely. |

### Mem0

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Without memory, every investigation starts from scratch. AOIS sees "auth service OOMKilled" for the twentieth time and has no idea it has seen it before. Mem0 stores the outcome of every investigation so the next one benefits from it. |
| **System Role** | Where does it sit in AOIS? | Mem0 is called at the start of `investigate()` (read: recall relevant memories → inject into system prompt) and at the end (write: store the outcome). It uses Qdrant for vector storage, the same Qdrant instance as the RAG incident store. |
| **Technical** | What is it, precisely? | A memory layer for AI agents. Stores text memories in a vector database with user/session metadata. At recall time, embeds the query and does cosine similarity search over stored memories. Uses an LLM to intelligently extract and consolidate what to remember from a given piece of text. |
| **Remove it** | What breaks, and how fast? | Remove Mem0 → every investigation starts cold. Recurring incidents are re-investigated from scratch each time. The institutional knowledge that accumulates over weeks of running AOIS is lost on every restart. AOIS never improves from experience. |
