# v22 — Temporal: Durable Agent Execution

⏱ **Estimated time: 5–7 hours**

---

## Prerequisites

v21 MCP + A2A complete. Docker available to run Temporal server.

```bash
# v21 agent investigator works
python3 -c "from agent.investigator import investigate; print('ok')"
# ok

# Docker is available
docker --version
# Docker version 26.x.x

# Temporal CLI available (will install below)
temporal --version 2>/dev/null || echo "install: see below"
```

---

## Learning Goals

By the end you will be able to:

- Explain what "durable execution" means and why it matters for agents that run for minutes
- Deploy Temporal server locally and run a Temporal worker
- Wrap the AOIS investigation into a Temporal workflow with activities
- Simulate a failure mid-investigation and observe Temporal replay to the correct state
- Implement timeouts, retries, and heartbeats on long-running tool calls
- Explain the difference between a Temporal workflow (coordinator) and an activity (unit of work)
- Query workflow history to reconstruct exactly what happened during an investigation

---

## The Problem This Solves

The AOIS investigator in v20 runs as a Python async coroutine. If the pod running AOIS crashes mid-investigation — between the `get_pod_logs` call and the `get_metrics` call — the investigation is lost. The next time AOIS starts, it has no record of what it was doing. The Kafka consumer picks up the alert again and starts a new investigation from scratch.

This is a demo-grade reliability model. In production:

- Investigations can run for 5–15 minutes (complex multi-tool reasoning)
- The AOIS pod can restart at any time (deployment update, OOM, node eviction)
- A restarted investigation may generate duplicate alerts or miss the resolution window
- The human on-call has no visibility into where an in-flight investigation was when it died

**Durable execution** solves this. The workflow's state is persisted after every step. If AOIS crashes after calling `get_pod_logs`, it resumes from that exact point when it restarts — not from the beginning. The human sees a continuous investigation history, not gaps.

Temporal implements durable execution as a managed workflow engine. It is not a message queue — it is a persistent state machine that runs your Python functions.

---

## How Temporal Works

```
Your code                     Temporal server                 Worker
───────────────────────────   ─────────────────────────────   ─────────────────────────
temporal_client.start_workflow()
                          →  creates Workflow Execution
                             stores input in history
                                                           ←  Worker polls for tasks
                                                              executes workflow function
                                                              executes activity (tool call)
                             appends ActivityCompleted event
                                                              reads next step from history
                                                              executes next activity
                             appends ActivityCompleted event
                          ←  returns final result to caller
```

The critical insight: **Temporal stores the complete execution history**. Every activity input and output is in the history. If the worker crashes after `get_pod_logs` completes, a new worker polls the history, sees "get_pod_logs completed with output X", and continues from there — it does not re-run `get_pod_logs`.

This is **event sourcing applied to function execution**. The history is the source of truth.

### Temporal concepts

| Concept | What it is | AOIS equivalent |
|---|---|---|
| Workflow | A durable, resumable function | `investigate()` |
| Activity | A unit of work that does real I/O | `get_pod_logs()`, `get_metrics()` |
| Worker | The process that executes workflows and activities | AOIS worker process |
| Task Queue | Where workflow/activity tasks wait for workers | `"aois-investigation"` |
| Workflow Execution | One running instance of a workflow | One incident investigation |
| Workflow History | Persistent log of every event in an execution | The investigation audit trail |

---

## Installing Temporal

```bash
# Temporal server (Docker — includes server, UI, and dependencies)
docker run -d \
  --name temporal \
  -p 7233:7233 \
  -p 8233:8233 \
  temporalio/auto-setup:1.24.2
# Pulls ~500MB on first run

# Wait for startup (~30 seconds)
sleep 30

# Verify
curl -s http://localhost:8233/api/v1/namespaces | jq '.namespaces[0].namespaceInfo.name'
# "default"

# Temporal CLI (for running workflow commands)
curl -sSf https://temporal.download/cli.sh | sh
# or: brew install temporal (macOS)

temporal --version
# temporal version 0.x.x

# Python SDK
pip install temporalio
```

The Temporal Web UI is at `http://localhost:8233` — a dashboard showing all workflow executions, their histories, and current state. Open this before running any workflow.

---

## Wrapping AOIS Tools as Temporal Activities

Activities are the Temporal unit of I/O. Each tool call becomes an activity.

```python
# temporal_workflows/activities.py
"""
AOIS tool calls wrapped as Temporal activities.
Activities are retried automatically by Temporal on failure.
Each activity is a discrete step in the investigation workflow.
"""
from datetime import timedelta

from temporalio import activity

from agent.tools.k8s import get_pod_logs, describe_node, list_events, get_metrics
from agent.tools.rag_tool import search_past_incidents


@activity.defn(name="get_pod_logs_activity")
async def get_pod_logs_activity(namespace: str, pod_name: str,
                                 lines: int = 100, session_id: str = "default") -> str:
    activity.heartbeat("fetching pod logs")  # proves the activity is alive during long kubectl calls
    return await get_pod_logs(namespace=namespace, pod_name=pod_name,
                              lines=lines, session_id=session_id)


@activity.defn(name="describe_node_activity")
async def describe_node_activity(node_name: str, session_id: str = "default") -> str:
    activity.heartbeat("describing node")
    return await describe_node(node_name=node_name, session_id=session_id)


@activity.defn(name="list_events_activity")
async def list_events_activity(namespace: str, resource_name: str = "",
                                limit: int = 20, session_id: str = "default") -> str:
    activity.heartbeat("listing events")
    return await list_events(namespace=namespace, resource_name=resource_name,
                             limit=limit, session_id=session_id)


@activity.defn(name="get_metrics_activity")
async def get_metrics_activity(namespace: str, resource_type: str = "pods",
                                session_id: str = "default") -> str:
    activity.heartbeat("fetching metrics")
    return await get_metrics(namespace=namespace, resource_type=resource_type,
                             session_id=session_id)


@activity.defn(name="search_past_incidents_activity")
async def search_past_incidents_activity(query: str, session_id: str = "default") -> str:
    return await search_past_incidents(query=query, session_id=session_id)


@activity.defn(name="run_llm_step_activity")
async def run_llm_step_activity(messages: list[dict], system: str) -> dict:
    """
    One LLM step in the investigation loop.
    Returns: {"stop_reason": str, "content": list, "usage": dict}
    """
    import anthropic, os
    from agent.tools.definitions import TOOL_DEFINITIONS

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    activity.heartbeat("calling Claude")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=system,
        tools=TOOL_DEFINITIONS,
        messages=messages,
    )
    return {
        "stop_reason": response.stop_reason,
        "content": [b.model_dump() for b in response.content],
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }
```

---

## The Investigation Workflow

```python
# temporal_workflows/investigation_workflow.py
"""
AOIS investigation as a Temporal workflow.
The investigation is durable: it survives pod restarts, network partitions,
and deployment updates. Temporal replays the history to resume from the
last completed activity.
"""
import json
import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from temporal_workflows.activities import (
    describe_node_activity,
    get_metrics_activity,
    get_pod_logs_activity,
    list_events_activity,
    run_llm_step_activity,
    search_past_incidents_activity,
)

log = logging.getLogger("temporal_workflow")

# Activity options — applied to every tool call
_ACTIVITY_OPTIONS = {
    "start_to_close_timeout": timedelta(seconds=30),  # each tool call must complete in 30s
    "retry_policy": RetryPolicy(
        initial_interval=timedelta(seconds=1),
        maximum_interval=timedelta(seconds=10),
        maximum_attempts=3,
        non_retryable_error_types=["ToolBlocked"],  # gate blocks are not retried
    ),
    "heartbeat_timeout": timedelta(seconds=10),  # activity must heartbeat every 10s
}

AGENT_SYSTEM_PROMPT = """You are AOIS, an autonomous SRE investigation agent.
Investigate the incident using your tools. Always search past incidents first.
Return a structured response with Severity, Root cause, Evidence, and Recommended action."""

# Maps tool names returned by Claude to activity functions
_TOOL_ACTIVITY_MAP = {
    "get_pod_logs":          get_pod_logs_activity,
    "describe_node":         describe_node_activity,
    "list_events":           list_events_activity,
    "get_metrics":           get_metrics_activity,
    "search_past_incidents": search_past_incidents_activity,
}


@workflow.defn(name="InvestigationWorkflow")
class InvestigationWorkflow:
    """
    Durable investigation workflow. Every tool call is an activity — its result
    is persisted to Temporal history. On crash, Temporal replays up to the last
    completed activity and continues from there.
    """

    @workflow.run
    async def run(self, incident: str, session_id: str, agent_role: str = "read_only") -> dict:
        workflow.logger.info("Starting investigation: %s", incident[:80])

        messages = [{"role": "user", "content": incident}]
        tool_calls_made = []
        total_input = total_output = 0

        for iteration in range(10):
            # LLM step — durable: if worker crashes here and Claude already responded,
            # Temporal replays the activity result without calling Claude again
            llm_result = await workflow.execute_activity(
                run_llm_step_activity,
                args=[messages, AGENT_SYSTEM_PROMPT],
                **_ACTIVITY_OPTIONS,
            )

            total_input  += llm_result["usage"]["input_tokens"]
            total_output += llm_result["usage"]["output_tokens"]

            if llm_result["stop_reason"] == "end_turn":
                final_text = next(
                    (b["text"] for b in llm_result["content"] if b.get("type") == "text"), ""
                )
                cost_usd = (total_input * 0.80 + total_output * 4.00) / 1_000_000
                return {
                    "session_id": session_id,
                    "incident": incident,
                    "investigation": final_text,
                    "tool_calls": tool_calls_made,
                    "iterations": iteration + 1,
                    "cost_usd": round(cost_usd, 6),
                    "total_input_tokens": total_input,
                    "total_output_tokens": total_output,
                }

            # Process tool calls — each is a separate durable activity
            messages.append({"role": "assistant", "content": llm_result["content"]})
            tool_results = []

            for block in llm_result["content"]:
                if block.get("type") != "tool_use":
                    continue

                tool_name  = block["name"]
                tool_input = block["input"]
                tool_calls_made.append({"tool": tool_name, "input": tool_input})

                activity_fn = _TOOL_ACTIVITY_MAP.get(tool_name)
                if activity_fn is None:
                    result_text = f"Unknown tool: {tool_name}"
                else:
                    try:
                        result_text = await workflow.execute_activity(
                            activity_fn,
                            kwargs={**tool_input, "session_id": session_id},
                            **_ACTIVITY_OPTIONS,
                        )
                    except Exception as e:
                        result_text = f"[Tool error: {e}]"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": str(result_text)[:4000],
                })

            messages.append({"role": "user", "content": tool_results})

        return {
            "session_id": session_id,
            "incident": incident,
            "investigation": "Max iterations reached",
            "tool_calls": tool_calls_made,
            "error": "max_iterations_exceeded",
        }
```

---

## The Worker

```python
# temporal_workflows/worker.py
"""
Temporal worker — polls for workflow and activity tasks and executes them.
Run: python3 -m temporal_workflows.worker
"""
import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from temporal_workflows.activities import (
    describe_node_activity,
    get_metrics_activity,
    get_pod_logs_activity,
    list_events_activity,
    run_llm_step_activity,
    search_past_incidents_activity,
)
from temporal_workflows.investigation_workflow import InvestigationWorkflow

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("temporal_worker")

TASK_QUEUE = "aois-investigation"


async def main():
    client = await Client.connect(os.getenv("TEMPORAL_HOST", "localhost:7233"))
    log.info("Connected to Temporal server")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[InvestigationWorkflow],
        activities=[
            get_pod_logs_activity,
            describe_node_activity,
            list_events_activity,
            get_metrics_activity,
            search_past_incidents_activity,
            run_llm_step_activity,
        ],
    )
    log.info("Worker started on task queue: %s", TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## ▶ STOP — do this now

Start the worker and run your first durable investigation:

```bash
# Terminal 1: Start the worker
python3 -m temporal_workflows.worker
# INFO: Connected to Temporal server
# INFO: Worker started on task queue: aois-investigation

# Terminal 2: Start an investigation
python3 - <<'EOF'
import asyncio
from temporalio.client import Client
from temporal_workflows.investigation_workflow import InvestigationWorkflow
import uuid

async def main():
    client = await Client.connect("localhost:7233")
    session_id = str(uuid.uuid4())

    handle = await client.start_workflow(
        InvestigationWorkflow.run,
        args=["AOIS Kafka consumer lag spike — check consumer pods", session_id],
        id=f"investigation-{session_id}",
        task_queue="aois-investigation",
    )
    print(f"Workflow started: {handle.id}")
    result = await handle.result()
    print(f"\nCost: ${result['cost_usd']:.6f}")
    print(f"Tool calls: {len(result['tool_calls'])}")
    print(f"\n{result['investigation'][:500]}")

asyncio.run(main())
EOF
```

While the workflow is running, open `http://localhost:8233`. You should see the `InvestigationWorkflow` execution running. Click into it — you will see every activity event in the history: `ActivityTaskStarted`, `ActivityTaskCompleted`, with the full input and output of each tool call. This is the audit trail.

---

## Simulating a Crash

This is the moment that demonstrates why Temporal exists.

```bash
# Terminal 1: Start the worker
python3 -m temporal_workflows.worker &
WORKER_PID=$!

# Terminal 2: Start a long investigation
python3 - <<'EOF'
import asyncio
from temporalio.client import Client
from temporal_workflows.investigation_workflow import InvestigationWorkflow
import uuid

async def main():
    client = await Client.connect("localhost:7233")
    session_id = "crash-test-001"
    handle = await client.start_workflow(
        InvestigationWorkflow.run,
        args=["auth service OOMKilled — full investigation", session_id],
        id=f"crash-test-{session_id}",
        task_queue="aois-investigation",
    )
    print(f"Workflow started: {handle.id}")
    # Do NOT await — let it run in background
    print("Investigation started. Kill the worker in Terminal 1 now.")

asyncio.run(main())
EOF

# Wait 3 seconds for the first tool call to complete, then kill the worker
sleep 3
kill $WORKER_PID
echo "Worker killed mid-investigation"

# Restart the worker
python3 -m temporal_workflows.worker &
echo "Worker restarted"

# The investigation resumes automatically from the last completed activity
# Check the Temporal UI: the workflow continues, not restarts
```

In the Temporal UI, you will see the workflow history shows the first activity completed, then a gap (worker crashed), then the workflow continues from the next activity — not from the beginning. The investigation is resumed, not restarted.

This is durable execution. Without Temporal: the investigation is lost. With Temporal: it continues.

---

## ▶ STOP — do this now

Run the crash simulation. Confirm in the Temporal UI that:
1. The workflow history shows the completed activities before the crash
2. After worker restart, new activities appear in the same workflow execution (not a new one)
3. The final result is returned to the caller when the workflow completes

Record: how many activities completed before the crash? How long did the resume take after worker restart?

---

## ▶ STOP — do this now

Query the Temporal workflow history to understand what AOIS actually did during an investigation:

```python
import asyncio
from temporalio.client import Client

async def inspect_workflow(workflow_id: str):
    client = await Client.connect("localhost:7233")

    # Get the workflow handle
    handle = client.get_workflow_handle(workflow_id)

    # Fetch execution result (if complete)
    try:
        result = await handle.result(timeout=5)
        print("Workflow completed:", result)
    except Exception as e:
        print("Workflow not yet complete or failed:", e)

    # Describe the workflow for status
    desc = await handle.describe()
    print(f"\nStatus: {desc.status}")
    print(f"Start time: {desc.start_time}")
    print(f"Close time: {desc.close_time}")
    print(f"Execution time: {(desc.close_time - desc.start_time).total_seconds():.1f}s" if desc.close_time else "Still running")

# Run an investigation then inspect it
from temporal_workflows.worker import run_investigation_workflow

async def main():
    workflow_id = await run_investigation_workflow(
        incident="payments-api CrashLoopBackOff — 20 restarts in 10 minutes",
        session_id="test-inspect-001",
    )
    print(f"Workflow started: {workflow_id}")
    await asyncio.sleep(5)  # let it progress
    await inspect_workflow(workflow_id)

asyncio.run(main())
```

Expected output:
```
Workflow started: aois-investigation-test-inspect-001
Status: WorkflowExecutionStatus.RUNNING
Start time: 2025-01-15 03:42:00+00:00
Close time: None
Still running
```

Also open the Temporal UI at `http://localhost:8080`. Click the workflow. You will see the event history: `WorkflowExecutionStarted` → `ActivityTaskScheduled` (classify) → `ActivityTaskCompleted` → `ActivityTaskScheduled` (investigate) → ... 

This timeline is the durable audit trail. Even if the worker crashes and restarts mid-investigation, this history survives — Temporal replays it from the event log.

---

## Common Mistakes

### 1. Using `await asyncio.sleep()` inside a workflow

Temporal workflows must be deterministic. `asyncio.sleep()` is non-deterministic (it interacts with the real clock). Use `workflow.sleep()` instead:

```python
# Wrong — breaks Temporal replay
await asyncio.sleep(5)

# Correct — Temporal's deterministic sleep
await workflow.sleep(timedelta(seconds=5))
```

The same applies to: random numbers (`random.random()` → `workflow.random().random()`), datetime (`datetime.now()` → `workflow.now()`), and any non-deterministic I/O.

---

### 2. Importing I/O libraries at the workflow module level

Workflows must be sandboxable. If you import `anthropic`, `asyncpg`, or `subprocess` at the top of `investigation_workflow.py`, Temporal's sandbox may reject it. Import them inside activity functions only.

```python
# Wrong — I/O in workflow module scope
import anthropic  # in investigation_workflow.py
client = anthropic.Anthropic()

# Correct — I/O in activities only (activities.py)
@activity.defn
async def run_llm_step_activity(...):
    import anthropic  # import inside the activity
    client = anthropic.Anthropic()
```

---

### 3. Not heartbeating long-running activities

Activities have a `heartbeat_timeout`. If the activity does not call `activity.heartbeat()` within that window, Temporal considers it failed and retries it. For `kubectl logs` calls that may take 5–10 seconds, heartbeat every 3 seconds:

```python
@activity.defn
async def get_pod_logs_activity(...) -> str:
    activity.heartbeat("starting kubectl logs")
    # Do the work
    result = _kubectl("logs", ...)
    activity.heartbeat("kubectl logs complete")
    return result
```

---

### 4. Storing mutable state in the workflow

Temporal replays the workflow from history on every decision. Any state you accumulate in a workflow-level variable (`self.tool_calls`, `self.messages`) must be deterministically reproducible from the activity history. If it is not, replay produces different results — Temporal raises a `NonDeterminismError`.

The pattern: derive state only from activity results, not from external state.

---

## Troubleshooting

### `WorkflowNotFoundError` when polling for result

```
temporalio.exceptions.WorkflowNotFoundError: workflow not found
```

The workflow ID does not exist. Either the workflow was never started, or it expired. Workflow executions expire after the `workflow_execution_timeout` (default: 10 years, configurable). If you see this immediately after `start_workflow`, the Temporal server is not running.

```bash
curl -s http://localhost:8233/api/v1/namespaces | jq length
# If 0 or error: Temporal server is not up — check docker ps
```

---

### Activities not being picked up (worker not polling)

The workflow starts but activities never execute — the Temporal UI shows tasks in the `aois-investigation` queue but the worker does not pick them up.

```bash
temporal task-queue describe --task-queue aois-investigation
# If "pollers: []" — no worker is polling
# Fix: start the worker process
```

---

## Connection to Later Phases

### To v23 (LangGraph)
LangGraph adds a stateful graph (Detect → Investigate → Hypothesize → Verify → Remediate) on top of Temporal's durability. The LangGraph graph defines the reasoning structure; Temporal ensures the graph execution survives failures. They compose: LangGraph workflow runs inside a Temporal workflow.

### To v25 (E2B Sandboxed Execution)
The remediation step in the investigation workflow (Remediate node in v23) runs proposed fixes in an E2B sandbox before applying them to production. E2B sandbox execution is itself a Temporal activity — it can be retried if the sandbox times out, and its result is in the Temporal history for audit.

### To v34.5 (AI SRE Capstone)
The game day in v34.5 involves intentional crashes during agent investigations. Temporal's replay capability is what makes the capstone game day honest — you crash the worker mid-investigation and verify that AOIS resumes correctly. Without Temporal, the capstone cannot demonstrate real production-grade agent reliability.

---

## Mastery Checkpoint

1. Start the Temporal server and the AOIS worker. Open `http://localhost:8233`. Confirm the UI shows the `default` namespace and your task queue is registered.

2. Run an investigation via Temporal. In the Temporal UI, open the workflow execution and expand the history. Identify: `WorkflowExecutionStarted`, `ActivityTaskScheduled`, `ActivityTaskStarted`, `ActivityTaskCompleted` events for each tool call. Record how many activities the investigation ran.

3. Run the crash simulation. Kill the worker after the first activity completes. Restart the worker. Confirm in the UI that the workflow execution is the same ID (not a new execution) and that the first activity's result is not re-fetched from kubectl — Temporal replays it from history.

4. Add a 5-second `asyncio.sleep()` inside the workflow (not inside an activity). Observe the `NonDeterminismError` during replay. Fix it by using `workflow.sleep(timedelta(seconds=5))`. Confirm the error is gone.

5. Set `maximum_attempts=1` in the retry policy and force an activity to fail (e.g., wrong namespace in `get_pod_logs`). Observe the `ActivityTaskFailed` event in the history. Set `maximum_attempts=3` and confirm the retry events appear.

6. Explain to a non-technical person what "durable execution" means, using the analogy of a document that auto-saves after every sentence — you can close the browser and reopen it without losing your work.

7. Explain to a junior engineer the difference between a Temporal workflow and a Temporal activity. Why can activities do I/O but workflows must be deterministic?

8. Explain to a senior engineer: what is the performance cost of Temporal's durability? Each activity result is persisted to the Temporal history store — what are the latency and storage implications for a workflow with 20 activities?

**The mastery bar:** you can crash the AOIS worker mid-investigation, restart it, and demonstrate that the investigation resumes from the correct activity — not from the beginning — with the Temporal history as evidence. Durable execution is not a concept you understand; it is a behavior you can demonstrate.

---

## 4-Layer Tool Understanding

### Temporal

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Agent investigations can take minutes. If the server crashes halfway through, the investigation is lost and you have to start over — or worse, you never finish. Temporal makes each step of the investigation permanent: if the server crashes, the investigation picks up exactly where it left off. |
| **System Role** | Where does it sit in AOIS? | Temporal wraps the `investigate()` function. Each tool call (get_pod_logs, get_metrics) is a Temporal activity. The investigation loop is a Temporal workflow. The worker process runs both. Temporal stores the result of every activity in its history — crash and restart, and the history is replayed to restore state. |
| **Technical** | What is it, precisely? | A durable workflow engine using event sourcing. Workflow execution history is persisted in a database (default: Cassandra or Postgres). On worker restart, Temporal replays the history to restore the in-memory state of the workflow function. Determinism is required: the workflow function must produce the same decisions given the same history. Activities are exempt — they can have side effects and are not replayed. |
| **Remove it** | What breaks, and how fast? | Remove Temporal → investigations run as plain async coroutines. A pod restart loses all in-flight investigations. In a cluster under load (KEDA scaling AOIS down during a deployment), this means investigations are silently lost. Discovery: the next day when on-call notices some P1 alerts have no investigation record. |
