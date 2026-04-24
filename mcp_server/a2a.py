"""
AOIS A2A (Agent-to-Agent) endpoint.
Implements Google's A2A protocol so other agents can delegate investigations.

Endpoints:
  GET  /.well-known/agent.json  — Agent Card discovery
  POST /tasks/send              — Submit a task
  GET  /tasks/{task_id}         — Poll for result

Run: uvicorn mcp_server.a2a:app --port 8002
"""
import asyncio
import logging
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.investigator import investigate

log = logging.getLogger("a2a")

app = FastAPI(title="AOIS A2A Endpoint", version="21.0")

AGENT_CARD = {
    "name": "AOIS",
    "description": (
        "AI Operations Intelligence System. Autonomous SRE agent that investigates "
        "Kubernetes incidents by pulling pod logs, node state, events, and metrics. "
        "Returns root cause analysis with cited evidence."
    ),
    "version": "21.0",
    "url": "http://localhost:8002",
    "capabilities": {"streaming": False, "pushNotifications": False},
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
            ],
        }
    ],
}

# In-memory task store — use Redis in production
_tasks: dict[str, dict] = {}


class TaskMessage(BaseModel):
    role: str
    parts: list[dict]


class Task(BaseModel):
    id: str | None = None
    message: TaskMessage
    sessionId: str | None = None


class TaskResult(BaseModel):
    id: str
    status: dict
    artifacts: list[dict] = []


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return AGENT_CARD


@app.post("/tasks/send")
async def send_task(task: Task) -> TaskResult:
    text = " ".join(
        p.get("text", "") for p in task.message.parts if p.get("type") == "text"
    )
    if not text:
        raise HTTPException(status_code=400, detail="No text content in task message")

    task_id = task.id or str(uuid.uuid4())
    _tasks[task_id] = {"state": "working", "text": text}
    asyncio.create_task(_run_investigation(task_id, text, task.sessionId))
    return TaskResult(id=task_id, status={"state": "working"})


@app.get("/tasks/{task_id}")
async def get_task(task_id: str) -> TaskResult:
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    data = _tasks[task_id]
    if data["state"] == "completed":
        return TaskResult(
            id=task_id,
            status={"state": "completed"},
            artifacts=[{
                "name": "investigation",
                "parts": [{"type": "text", "text": data.get("result", "")}],
            }],
        )
    return TaskResult(id=task_id, status={"state": data["state"]})


async def _run_investigation(task_id: str, incident: str, session_id: str | None) -> None:
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
