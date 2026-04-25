# v21 — MCP + A2A: AOIS as an Interoperable Platform

⏱ **Estimated time: 5–7 hours**

---

## Prerequisites

v20 agent running. Tools decorated with `@gated_tool`. Claude API key active.

```bash
# Agent investigator works
python3 -c "import asyncio; from agent.investigator import investigate; print('ok')"
# ok

# Gate is enforcing tool calls
echo '{"tool_name":"get_pod_logs","agent_role":"read_only","human_approved":false}' | \
  opa eval --data agent_gate/policy.rego --input /dev/stdin --format json "data.aois.agent.allow" | \
  jq '.result[0].expressions[0].value'
# true

# Python MCP SDK available
python3 -c "import mcp; print(mcp.__version__)" 2>/dev/null || echo "install: pip install mcp"
```

---

## Learning Goals

By the end you will be able to:

- Explain what MCP is, why Anthropic created it, and what problem it solves for AI tooling
- Build AOIS as an MCP server that exposes its investigative tools to any MCP client
- Connect Claude.ai and Cursor to the AOIS MCP server and invoke tools from the UI
- Explain what A2A is, why Google created it, and how it differs from MCP
- Implement a minimal A2A endpoint on AOIS so it can receive tasks from other agents
- Explain the difference between: tool calling (v20), MCP (v21), and A2A (v21)
- Test cross-system agent communication: a LangChain agent sends a task to AOIS via A2A

---

## What MCP Is

Model Context Protocol (MCP) is an open standard created by Anthropic (November 2024) for connecting AI models to tools, data sources, and services. Before MCP, every AI integration was a custom integration: Claude needs its own plugin, Cursor has its own extension format, each tool is wired differently to each AI.

MCP defines a standard:
- **Server**: a program that exposes tools, resources, and prompts via the MCP protocol
- **Client**: an AI application (Claude.ai, Cursor, a custom agent) that discovers and calls those tools
- **Transport**: how they communicate — stdio (for local tools) or HTTP+SSE (for remote servers)

The analogy: MCP is to AI tools what USB is to hardware. Before USB, every peripheral needed a custom port. After USB, one standard, everything works with everything.

### MCP vs v20 Tool Use

In v20, you defined tools in `tools/definitions.py` and wired them to Python functions in `investigator.py`. Those tools only work with your AOIS investigator — they are private.

In v21, you expose those same tools as an MCP server. Now Claude.ai can call `get_pod_logs` directly from the Claude UI. Cursor can call `search_past_incidents` while you are writing a postmortem. Any MCP-compatible client gets access to AOIS's capabilities.

The tools do not change. The gate does not change. The difference is exposure: private tool → public MCP resource.

---

## What A2A Is

A2A (Agent-to-Agent) protocol is a Google-led open standard (2025) for communication between AI agents from different vendors and frameworks. Where MCP connects tools to models, A2A connects agents to agents.

The distinction:
- **MCP**: Claude (model) → AOIS MCP server (tool provider). Human is the orchestrator.
- **A2A**: CrewAI agent → AOIS A2A endpoint. Another AI is the orchestrator.

A2A defines how agents discover each other (via an Agent Card — a JSON description of capabilities), send tasks, stream results, and exchange structured messages. It is designed so a LangGraph agent built by one team can hand off a task to an AutoGen agent built by another team, with no shared codebase.

For AOIS, A2A means: a Google ADK agent doing incident triage can say "AOIS, investigate this pod failure and report back" — and AOIS handles the investigation autonomously.

---

## Building the AOIS MCP Server

The Python MCP SDK (`pip install mcp`) provides the server framework. You define tools using a decorator syntax similar to FastAPI endpoints.

```bash
pip install mcp httpx-sse
```

```python
# mcp_server/server.py
"""
AOIS MCP server — exposes investigative tools to any MCP client.
Run: python -m mcp_server.server (stdio transport for local clients)
     uvicorn mcp_server.server:app (HTTP+SSE for remote clients)
"""
import asyncio
import json
import logging
import os
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest, CallToolResult, ListToolsRequest, ListToolsResult,
    TextContent, Tool,
)
from pydantic import AnyUrl

from agent.tools.k8s import describe_node, get_metrics, get_pod_logs, list_events
from agent.tools.rag_tool import search_past_incidents
from agent.investigator import investigate

log = logging.getLogger("mcp_server")

# Shared session_id for MCP calls — each client session gets its own circuit breaker scope
_MCP_SESSION = "mcp-default"

server = Server("aois-mcp-server")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Advertise available tools to MCP clients."""
    return [
        Tool(
            name="get_pod_logs",
            description="Retrieve recent logs from a Kubernetes pod in the AOIS cluster",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "pod_name": {"type": "string"},
                    "lines": {"type": "integer", "default": 100},
                },
                "required": ["namespace", "pod_name"],
            },
        ),
        Tool(
            name="describe_node",
            description="Get resource usage and conditions for a Kubernetes node",
            inputSchema={
                "type": "object",
                "properties": {"node_name": {"type": "string"}},
                "required": ["node_name"],
            },
        ),
        Tool(
            name="list_events",
            description="List recent Kubernetes events for a namespace",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "resource_name": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["namespace"],
            },
        ),
        Tool(
            name="get_metrics",
            description="Query current CPU and memory usage for pods or nodes",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "resource_type": {"type": "string", "enum": ["pods", "nodes"]},
                },
                "required": ["namespace", "resource_type"],
            },
        ),
        Tool(
            name="search_past_incidents",
            description="Search AOIS incident history for similar past incidents",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="investigate_incident",
            description=(
                "Run a full autonomous AOIS investigation on an incident description. "
                "AOIS will gather evidence, search past incidents, and return a full analysis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "incident_description": {"type": "string"},
                    "agent_role": {
                        "type": "string",
                        "enum": ["read_only", "analyst"],
                        "default": "read_only",
                    },
                },
                "required": ["incident_description"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to the appropriate AOIS function."""
    session_id = _MCP_SESSION

    try:
        if name == "get_pod_logs":
            result = await get_pod_logs(session_id=session_id, **arguments)
        elif name == "describe_node":
            result = await describe_node(session_id=session_id, **arguments)
        elif name == "list_events":
            result = await list_events(session_id=session_id, **arguments)
        elif name == "get_metrics":
            result = await get_metrics(session_id=session_id, **arguments)
        elif name == "search_past_incidents":
            result = await search_past_incidents(session_id=session_id, **arguments)
        elif name == "investigate_incident":
            inv_result = await investigate(
                arguments["incident_description"],
                agent_role=arguments.get("agent_role", "read_only"),
                session_id=session_id,
            )
            result = json.dumps(inv_result, indent=2)
        else:
            result = f"Unknown tool: {name}"
    except Exception as e:
        result = f"Error: {e}"
        log.error("MCP tool error %s: %s", name, e)

    return [TextContent(type="text", text=str(result))]


async def run_stdio():
    """Run the MCP server over stdio (for local Claude.ai / Cursor integration)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="aois",
                server_version="21.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={}
                ),
            ),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_stdio())
```

---

## ▶ STOP — do this now

Test the MCP server locally using the MCP inspector:

```bash
# Install the MCP inspector (Node.js tool)
npx @modelcontextprotocol/inspector python3 -m mcp_server.server
# Opens browser at http://localhost:5173
# Click "List Tools" — should show all 6 AOIS tools
# Click "get_pod_logs" → enter namespace="aois", pod_name="aois" → Run
# Should return real pod logs from the Hetzner cluster
```

If the inspector shows tools but `get_pod_logs` returns "kubectl error: ...":
- Check that `KUBECONFIG` path is correct for your environment (local dev vs cluster)
- The MCP server runs on your machine; kubectl must be configured to reach the cluster

---

## Connecting Claude.ai to AOIS

Claude.ai supports MCP servers via its settings. Configure it to point at your AOIS server:

```json
// ~/.claude/claude_desktop_config.json  (macOS/Linux)
{
  "mcpServers": {
    "aois": {
      "command": "python3",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/home/collins/aois-system",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "DATABASE_URL": "postgresql://...",
        "REDIS_URL": "redis://localhost:6379"
      }
    }
  }
}
```

After configuring, restart Claude.ai desktop. In a new conversation, you will see "AOIS" in the tool selector. You can now type:

```
"Get the recent events from the kafka namespace and tell me if anything looks wrong"
```

Claude.ai will call `list_events(namespace="kafka")` through your MCP server, receive the real k8s events from your Hetzner cluster, and analyze them — without you writing any code for that specific interaction.

---

## Connecting Cursor to AOIS

In Cursor settings → Features → MCP, add:

```json
{
  "aois": {
    "command": "python3",
    "args": ["-m", "mcp_server.server"],
    "cwd": "/home/collins/aois-system"
  }
}
```

Now in Cursor's composer (Cmd+K or Ctrl+K), you can ask: "Search past incidents for OOMKilled patterns" and Cursor will call the AOIS MCP server to fetch the answer.

---

## Implementing A2A

A2A defines an Agent Card (what this agent can do) and a task endpoint (where to send tasks). AOIS becomes an A2A-compliant agent by implementing both.

```python
# mcp_server/a2a.py
"""
A2A (Agent-to-Agent) endpoint for AOIS.
Implements the A2A protocol so other agents can delegate investigations to AOIS.

Spec: https://google.github.io/A2A/
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
import uuid
import asyncio
import logging

from agent.investigator import investigate

log = logging.getLogger("a2a")

app = FastAPI(title="AOIS A2A Endpoint", version="21.0")


# ─────────────────────────────────────────────────────────
# Agent Card — describes this agent's capabilities
# Any A2A client can discover what AOIS can do
# ─────────────────────────────────────────────────────────
AGENT_CARD = {
    "name": "AOIS",
    "description": (
        "AI Operations Intelligence System. "
        "Autonomous SRE agent that investigates Kubernetes incidents by pulling "
        "pod logs, node state, events, and metrics. Returns root cause analysis "
        "with cited evidence."
    ),
    "version": "21.0",
    "url": "http://localhost:8002",  # where this A2A server is running
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
    },
    "skills": [
        {
            "id": "investigate_incident",
            "name": "Investigate Kubernetes Incident",
            "description": "Full autonomous investigation of a k8s incident",
            "inputModes": ["text"],
            "outputModes": ["text"],
            "examples": [
                "auth-service pod OOMKilled exit code 137",
                "Kafka consumer lag spike on aois-logs topic",
                "5xx spike on api-gateway — 503 upstream errors",
            ],
        }
    ],
}


# ─────────────────────────────────────────────────────────
# A2A Task models
# ─────────────────────────────────────────────────────────
class TaskMessage(BaseModel):
    role: str           # "user" or "agent"
    parts: list[dict]   # [{"type": "text", "text": "..."}]


class Task(BaseModel):
    id: str
    message: TaskMessage
    sessionId: str | None = None


class TaskResult(BaseModel):
    id: str
    status: dict        # {"state": "completed"|"failed"|"working"}
    artifacts: list[dict] = []


# In-memory task store (use Redis in production)
_tasks: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────
# A2A endpoints
# ─────────────────────────────────────────────────────────
@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    """A2A Agent Card discovery endpoint."""
    return AGENT_CARD


@app.post("/tasks/send")
async def send_task(task: Task) -> TaskResult:
    """Receive a task from another agent and begin investigation."""
    # Extract text from the message parts
    text = " ".join(
        p.get("text", "") for p in task.message.parts
        if p.get("type") == "text"
    )
    if not text:
        raise HTTPException(status_code=400, detail="No text content in task message")

    task_id = task.id or str(uuid.uuid4())
    _tasks[task_id] = {"state": "working", "text": text}

    # Run investigation asynchronously
    asyncio.create_task(_run_investigation(task_id, text, task.sessionId))

    return TaskResult(
        id=task_id,
        status={"state": "working"},
    )


@app.get("/tasks/{task_id}")
async def get_task(task_id: str) -> TaskResult:
    """Poll for task completion."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = _tasks[task_id]
    if task_data["state"] == "completed":
        return TaskResult(
            id=task_id,
            status={"state": "completed"},
            artifacts=[{
                "name": "investigation",
                "parts": [{"type": "text", "text": task_data.get("result", "")}],
            }],
        )
    return TaskResult(id=task_id, status={"state": task_data["state"]})


async def _run_investigation(task_id: str, incident: str, session_id: str | None) -> None:
    """Background task: run AOIS investigation and store result."""
    try:
        result = await investigate(
            incident,
            agent_role="read_only",
            session_id=session_id or task_id,
        )
        _tasks[task_id]["state"]  = "completed"
        _tasks[task_id]["result"] = result.get("investigation", "")
        log.info("A2A task %s completed", task_id)
    except Exception as e:
        _tasks[task_id]["state"] = "failed"
        _tasks[task_id]["error"] = str(e)
        log.error("A2A task %s failed: %s", task_id, e)
```

---

## ▶ STOP — do this now

Start the A2A server and test it with curl:

```bash
# Start the A2A server (separate terminal)
uvicorn mcp_server.a2a:app --port 8002 --reload
# INFO: Uvicorn running on http://127.0.0.1:8002

# Discover the agent card
curl -s http://localhost:8002/.well-known/agent.json | jq .name
# "AOIS"

# Send a task (another agent delegating to AOIS)
TASK_RESPONSE=$(curl -s -X POST http://localhost:8002/tasks/send \
  -H "Content-Type: application/json" \
  -d '{
    "id": "task-001",
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "auth-service OOMKilled — investigate"}]
    }
  }')
echo $TASK_RESPONSE | jq .
# {"id":"task-001","status":{"state":"working"},"artifacts":[]}

# Poll for completion (wait ~10 seconds for investigation to complete)
sleep 12
curl -s http://localhost:8002/tasks/task-001 | jq '.status.state, .artifacts[0].parts[0].text[:200]'
# "completed"
# "Severity: P2\nRoot cause: auth-service pod reached its memory limit..."
```

This is a cross-agent handoff: the curl command represents another agent (AutoGen, CrewAI, LangGraph) delegating an investigation to AOIS via A2A. AOIS investigates autonomously and the delegating agent polls for the result.

---

## MCP vs A2A: The Difference in Practice

```
MCP scenario:
  You (human) → Claude.ai (model+UI) → AOIS MCP server (tools)
  Human is the orchestrator. Claude decides which AOIS tools to call.

A2A scenario:
  LangGraph agent (orchestrator) → AOIS A2A endpoint (specialist agent)
  An AI is the orchestrator. AOIS runs its full investigation autonomously.
```

| | MCP | A2A |
|---|---|---|
| Who calls it | A model (Claude, GPT-4) | Another agent |
| What it gets | Individual tool results | Full investigation result |
| Human involvement | Human drives the conversation | Human may not be in the loop |
| Granularity | Fine-grained (one tool at a time) | Coarse-grained (full task) |
| Protocol creator | Anthropic | Google |
| Use case | Augmenting a human-driven AI session | Multi-agent pipeline orchestration |

Both are needed. MCP is for AI-augmented human workflows. A2A is for autonomous agent pipelines.

---

## ▶ STOP — do this now

Send an A2A task from Python (simulating what a LangGraph or AutoGen agent would do):

```python
# test_a2a.py
import httpx
import asyncio
import time

A2A_URL = "http://localhost:8002"

async def delegate_to_aois(incident: str) -> str:
    """Simulate another agent delegating a task to AOIS via A2A."""
    async with httpx.AsyncClient() as client:
        # Discover the agent
        card = (await client.get(f"{A2A_URL}/.well-known/agent.json")).json()
        print(f"Connected to: {card['name']} — {card['description'][:60]}")

        # Send the task
        import uuid
        task_id = str(uuid.uuid4())
        response = await client.post(f"{A2A_URL}/tasks/send", json={
            "id": task_id,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": incident}]
            }
        })
        print(f"Task submitted: {task_id}, state={response.json()['status']['state']}")

        # Poll until complete
        for _ in range(30):  # max 60 seconds
            await asyncio.sleep(2)
            result = (await client.get(f"{A2A_URL}/tasks/{task_id}")).json()
            state = result["status"]["state"]
            if state == "completed":
                return result["artifacts"][0]["parts"][0]["text"]
            elif state == "failed":
                return f"Task failed"
            print(f"  Polling... state={state}")

        return "Timeout waiting for investigation"

async def main():
    investigation = await delegate_to_aois(
        "Kafka consumer pod is not processing messages — check kafka namespace"
    )
    print(f"\n=== AOIS Investigation Result ===\n{investigation}")

asyncio.run(main())
```

```bash
python3 test_a2a.py
# Connected to: AOIS — AI Operations Intelligence System. Autonomous SRE agent...
# Task submitted: uuid-..., state=working
#   Polling... state=working
#   Polling... state=working
# === AOIS Investigation Result ===
# Severity: P3
# Root cause: ...
```

---

## Common Mistakes

### 1. MCP server blocks on sync kubectl calls

The MCP server is async. If `get_pod_logs` calls `subprocess.run()` (blocking), it blocks the event loop during the kubectl execution. Use `asyncio.create_subprocess_exec` for truly non-blocking subprocess calls, or wrap with `asyncio.to_thread`:

```python
import asyncio

async def _kubectl_async(*args) -> str:
    result = await asyncio.to_thread(
        subprocess.run,
        ["sudo", "kubectl", "--kubeconfig", KUBECONFIG] + list(args),
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout.strip() if result.returncode == 0 else f"error: {result.stderr}"
```

In v20 this did not matter (the `await` in the tool functions was not actually awaiting anything async). In v21 with concurrent MCP calls, it does.

---

### 2. A2A task state lost on server restart

The in-memory `_tasks` dict is ephemeral. If the A2A server restarts while a task is running, the polling client gets 404. For production, store task state in Redis:

```python
import redis, json
_r = redis.Redis.from_url(os.getenv("REDIS_URL"))

def _set_task_state(task_id, data):
    _r.setex(f"aois:a2a:{task_id}", 3600, json.dumps(data))

def _get_task_state(task_id):
    raw = _r.get(f"aois:a2a:{task_id}")
    return json.loads(raw) if raw else None
```

---

### 3. MCP session_id not isolating circuit breakers

All MCP calls use `_MCP_SESSION = "mcp-default"`. If two Claude.ai sessions call tools simultaneously, they share a circuit breaker — one session's calls count against the other's limit.

Fix for production: derive session_id from the MCP `clientId` in the connection headers. In v21, using a shared session is acceptable — it means the MCP circuit breaker trips at 20 total calls across all Claude.ai sessions combined, which prevents runaway UI-driven tool calls.

---

## Troubleshooting

### MCP inspector shows tools but calls return empty

The MCP server is receiving calls but the tools return empty strings. Check:

```bash
# Is kubectl reachable from the server's working directory?
sudo kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get pods -n aois
# If this fails, kubectl config is the issue — not MCP
```

---

### A2A task stuck in "working" state forever

The investigation is not completing. Check the A2A server logs:

```bash
# Look for asyncio errors or gate blocks:
uvicorn mcp_server.a2a:app --port 8002 --log-level debug 2>&1 | grep -E "error|blocked|tripped"
```

Common cause: circuit breaker tripped because the previous test run used too many calls. Reset:

```bash
redis-cli KEYS "aois:cb:*" | xargs redis-cli DEL
```

---

## Part 3 — AG-UI: The Agent ↔ Frontend Protocol

MCP connects tools to AI. A2A connects agents to agents. There is a third gap: how does an agent's real-time state reach a user's browser?

Without a standard: you write custom WebSocket code, poll an endpoint, or bolt on server-sent events manually. Every frontend team rolls their own. AG-UI (published by CopilotKit, May 2025) is the third protocol in the triad — the standard for pushing agent state to frontends in real time.

### The Problem Without AG-UI

AOIS investigates an incident. The investigation takes 45 seconds. During those 45 seconds:
- Which tools has AOIS called?
- What has it found so far?
- Is it stuck, or still working?

Without AG-UI, the v26 React dashboard has two bad options: poll `/status` every second (wastes network, feels janky) or wait for the final result (the UI appears frozen). Neither gives you the live streaming experience modern AI products require.

The backend knows everything in real-time. The frontend is blind until done. AG-UI closes that gap.

### How AG-UI Works

AG-UI is an event-based, bidirectional protocol built on Server-Sent Events (SSE). The agent emits structured events as it works; the frontend consumes and renders them as they arrive.

**Core event types:**

| Event | When it fires | What the UI shows |
|---|---|---|
| `RunStarted` | Investigation begins | Spinner appears, status = "Investigating..." |
| `TextMessageStart` / `Chunk` / `End` | Agent narrates its reasoning | Streaming text appears word by word |
| `ToolCallStart` | Tool invocation begins | "Fetching pod logs..." card appears |
| `ToolCallEnd` | Tool returns result | Result shown inline, tool card resolves |
| `StateSnapshot` | Agent state checkpoint | Full state serialized — useful for resuming |
| `StateDelta` | Incremental state change | Patch applied to frontend state |
| `RunFinished` | Investigation complete | Final severity + recommended action displayed |
| `RunError` | Agent failed | Error card shown, human escalation offered |

The frontend subscribes to the SSE stream once. Events arrive as they happen. No polling. No batching. The user sees the investigation unfold in real time.

### Wiring AG-UI to AOIS

AG-UI is framework-agnostic — it is a stream of JSON events over HTTP. AOIS emits them from a new SSE endpoint; the v26 dashboard subscribes.

```python
# mcp_server/agui.py
import asyncio
import json
from datetime import datetime, UTC
from typing import AsyncGenerator

async def agui_event_stream(
    log_entry: str,
    investigation_fn,
) -> AsyncGenerator[str, None]:
    """Emit AG-UI protocol events as AOIS investigates."""

    run_id = f"run-{int(datetime.now(UTC).timestamp())}"

    yield _event("RunStarted", {"run_id": run_id, "log": log_entry})

    yield _event("TextMessageStart", {"role": "assistant", "id": f"msg-{run_id}"})
    yield _event("TextMessageChunk", {"delta": "Investigating incident: "})
    yield _event("TextMessageChunk", {"delta": log_entry[:80]})
    yield _event("TextMessageEnd", {})

    yield _event("ToolCallStart", {
        "tool_call_id": "tc-1",
        "tool_name": "get_pod_logs",
        "tool_input": json.dumps({"namespace": "aois"}),
    })

    result = await investigation_fn(log_entry)

    yield _event("ToolCallEnd", {
        "tool_call_id": "tc-1",
        "tool_output": json.dumps(result.get("tool_evidence", ""))[:200],
    })

    yield _event("StateSnapshot", {"state": result})
    yield _event("RunFinished", {"run_id": run_id, "status": "completed"})


def _event(event_type: str, data: dict) -> str:
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"
```

Add an SSE endpoint to FastAPI:

```python
# In main.py
from fastapi.responses import StreamingResponse
from mcp_server.agui import agui_event_stream

@app.get("/investigate/stream")
async def investigate_stream(log: str):
    from agent.investigator import run_investigation
    return StreamingResponse(
        agui_event_stream(log, run_investigation),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### ▶ STOP — do this now

Curl the streaming endpoint and watch AG-UI events arrive in real time as AOIS works:

```bash
curl -N "http://localhost:8000/investigate/stream?log=auth+service+OOMKilled+exit+code+137"
```

Expected output (events stream over ~5–10 seconds):

```
data: {"type": "RunStarted", "run_id": "run-1745500000", "log": "auth service OOMKilled..."}

data: {"type": "TextMessageStart", "role": "assistant", "id": "msg-run-1745500000"}

data: {"type": "TextMessageChunk", "delta": "Investigating incident: "}

data: {"type": "TextMessageChunk", "delta": "auth service OOMKilled exit code 137"}

data: {"type": "TextMessageEnd"}

data: {"type": "ToolCallStart", "tool_call_id": "tc-1", "tool_name": "get_pod_logs", ...}

data: {"type": "ToolCallEnd", "tool_call_id": "tc-1", "tool_output": "...log evidence..."}

data: {"type": "StateSnapshot", "state": {"severity": "P2", "summary": "...", ...}}

data: {"type": "RunFinished", "run_id": "run-1745500000", "status": "completed"}
```

Each `data:` line is a standard SSE frame. The connection stays open between events. The v26 React dashboard subscribes to this stream with `EventSource` and renders each event as it arrives — no polling, no waiting for completion.

### How This Connects to v26

In v26, the React dashboard uses WebSockets to receive final results. With AG-UI:

- Replace the final-result handler with an `EventSource` subscription to `/investigate/stream`
- Each `ToolCallStart` renders a "Fetching pod logs..." card in real time
- Each `TextMessageChunk` renders streaming text — same word-by-word pattern as ChatGPT
- `RunFinished` closes the spinner and shows the severity card

The Vercel AI SDK (used in v26) has built-in React hooks for consuming AG-UI-compatible streams:

```typescript
// v26 dashboard — AG-UI subscription becomes three lines
const source = new EventSource(`/investigate/stream?log=${encodeURIComponent(log)}`);
source.onmessage = (e) => dispatch(JSON.parse(e.data));
source.onerror = () => source.close();
```

You are learning the event protocol now so the v26 integration is mechanical, not creative.

### The Agentic Triad — Complete

All three protocols are now in AOIS:

| Protocol | Connects | Transport | AOIS role |
|---|---|---|---|
| **MCP** | Agent ↔ Tool | JSON-RPC 2.0 over stdio/SSE | AOIS = MCP server |
| **A2A** | Agent ↔ Agent | REST/JSON + SSE polling | AOIS = A2A server |
| **AG-UI** | Agent ↔ Frontend | SSE event stream | AOIS = AG-UI emitter |

Remove any one: AOIS tools are invisible to AI clients (no MCP), AOIS is isolated from multi-vendor pipelines (no A2A), or the dashboard only shows completed results (no AG-UI). All three together is what makes AOIS a production-grade interoperable platform.

AWS Bedrock AgentCore supports AG-UI natively — when AOIS runs as a managed Bedrock agent, the same event stream protocol works unchanged, with AWS handling the SSE infrastructure. This connection is covered in v10.

---

## Connection to Later Phases

### To v21.5 (MCP Security)
The MCP server in v21 has no authentication — any local process can call it. v21.5 adds OAuth 2.0 on the MCP server, per-client rate limits, and MCP-level OTel tracing. The server code structure from v21 is the base that v21.5 hardens.

### To v24 (Multi-Agent Frameworks)
In v24, AutoGen agents, CrewAI agents, and Google ADK agents all delegate to AOIS via A2A. The A2A endpoint built in v21 is what makes AOIS a participant in multi-framework agent pipelines. Without A2A, AOIS is isolated within the Anthropic ecosystem.

### To v26 (React Dashboard)
The AG-UI `/investigate/stream` endpoint built here is what the v26 React dashboard subscribes to. v26 wires an `EventSource` to this stream — the dashboard renders `ToolCallStart` as tool-call cards, `TextMessageChunk` as streaming text, and `RunFinished` as the severity card. The protocol is the same; only the rendering layer is new.

### To v30 (Internal Developer Platform)
The AOIS Agent Card (`/.well-known/agent.json`) becomes the service catalog entry in the IDP. Other teams discover AOIS capabilities by reading the card — the same way they discover APIs via OpenAPI specs.

---


## Build-It-Blind Challenge

Close the notes. From memory: write the MCP server tool registration — the `@server.tool()` decorator pattern, a `get_incident_analysis` tool with input schema, and the server startup using `stdio` transport. 20 minutes.

```bash
python3 mcp_server/server.py &
# Server starts on stdio
# MCP client can now call get_incident_analysis
```

---

## Failure Injection

Call an MCP tool with a missing required parameter and read the error:

```python
# Required: namespace and pod_name
await client.call_tool("get_pod_logs", {"namespace": "aois"})
# pod_name is missing — what does the MCP server return?
# Is it a schema validation error or a runtime error?
```

Understand the difference: schema validation catches missing params before your tool code runs. Runtime errors happen inside your tool. Which is safer and why?

---

## Osmosis Check

1. Claude.ai connects to your MCP server as a client. It calls `get_pod_logs` with `namespace="kube-system"`. Your OPA policy (v20 agent gate) allows only the `aois` namespace. Does the gate fire for MCP-initiated calls the same as agent-initiated calls? What determines whether the policy applies?
2. A2A protocol allows AOIS to call a second agent's tools. That second agent also has an OPA gate. Describe the trust chain: when AOIS calls Agent B's tool, whose identity is presented to Agent B's gate — AOIS's identity or the original user's identity?

---

## Mastery Checkpoint

1. Start the MCP server and connect the MCP inspector. Call `get_pod_logs(namespace="aois", pod_name="aois")` from the inspector UI. Confirm you receive real pod logs from the cluster.

2. Configure Claude.ai desktop to connect to the AOIS MCP server. Ask Claude: "List the recent Kubernetes events in the kafka namespace." Confirm Claude calls `list_events` via MCP and returns the actual events.

3. Start the A2A server. Fetch the agent card via `curl http://localhost:8002/.well-known/agent.json`. Confirm all required A2A fields are present: `name`, `version`, `url`, `capabilities`, `skills`.

4. Run `test_a2a.py`. Confirm the delegated investigation completes with a real result (not a timeout or error). Record the tool calls the investigation made — confirm they went through the gate.

5. Explain to a non-technical person the difference between MCP and A2A using a workplace analogy: MCP is asking a specialist colleague for specific information. A2A is delegating an entire project to a specialist team and waiting for their report.

6. Explain to a junior engineer: if you have both MCP and A2A on the same AOIS tools, why do you need both? When would a caller choose MCP vs A2A for the same underlying tool?

7. Explain to a senior engineer: the A2A task store is in-memory (dict). List three production failure modes this creates. What is the minimum viable fix for each?

**The mastery bar:** AOIS is callable from Claude.ai, Cursor, and any A2A-compatible agent — without any code changes to the calling system. The same gate, the same circuit breaker, the same tools — exposed through two different interoperability standards.

---

## 4-Layer Tool Understanding

### MCP (Model Context Protocol)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Every AI tool is currently a custom integration — Claude needs its own plugin, Cursor has its own format. MCP is one standard so a tool built once works with every AI client, without custom code per client. |
| **System Role** | Where does it sit in AOIS? | AOIS exposes its investigative tools as an MCP server. Claude.ai and Cursor are MCP clients. When a user asks Claude "what's in the kafka logs?", Claude calls the AOIS MCP server, which runs `list_events` through the gate and returns the result. |
| **Technical** | What is it, precisely? | A JSON-RPC 2.0 based protocol over stdio (local) or HTTP+SSE (remote). Defines three primitives: Tools (callable functions), Resources (readable data), Prompts (template prompts). MCP clients discover tools via `tools/list` and call them via `tools/call`. Servers return structured `TextContent`, `ImageContent`, or `EmbeddedResource`. |
| **Remove it** | What breaks, and how fast? | Remove MCP → AOIS tools are only accessible through the `investigator.py` code. Claude.ai and Cursor cannot use AOIS capabilities without custom integrations written for each. Every new AI client requires new glue code. |

### A2A (Agent-to-Agent Protocol)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | AI agents built by different companies (Google, Anthropic, Microsoft) cannot talk to each other — every cross-framework handoff requires custom code. A2A is the standard for agents to delegate tasks to each other, regardless of what framework or company built them. |
| **System Role** | Where does it sit in AOIS? | As an HTTP endpoint (`/tasks/send`, `/tasks/{id}`, `/.well-known/agent.json`). Other agents discover AOIS via the Agent Card and delegate investigation tasks. AOIS runs the investigation autonomously and the delegating agent polls for the result. |
| **Technical** | What is it, precisely? | A REST+JSON protocol with four concepts: Agent Card (capability advertisement at `/.well-known/agent.json`), Task (unit of work with id, message, artifacts), Parts (typed content — text, file, data), and States (submitted → working → completed/failed). Supports long-running async tasks via polling or SSE streaming. |
| **Remove it** | What breaks, and how fast? | Remove A2A → AOIS can only be orchestrated by Anthropic-native code (Claude tool use, MCP). LangGraph, AutoGen, and Google ADK agents cannot delegate to AOIS. Multi-vendor agent pipelines cannot include AOIS as a participant. |
