# v0.6 — Your First API (No AI)

## What this version builds

A minimal FastAPI server with one endpoint that does log analysis using only regex and pattern matching — no AI. You will understand every line of how FastAPI receives a request, validates it, processes it, and returns a response. Then you will see exactly where regex breaks down.

This is the last thing built without intelligence. v0.7 introduces raw LLM calls. v1 brings it all together.

---

## What FastAPI is

FastAPI is a Python web framework for building APIs. It is built on two things:
- **Starlette** — the async web framework underneath (routing, middleware, request/response)
- **Pydantic** — data validation (already covered in v0.5)

FastAPI's job: receive an HTTP request, route it to the right function, validate the input, run your code, validate the output, send the HTTP response back.

```
HTTP Request
     |
     v
  uvicorn          # ASGI server — handles the raw TCP connection
     |
     v
  FastAPI          # routes the request to the right function
     |
     v
  Pydantic         # validates input body against your model
     |
     v
  Your function    # your logic runs here
     |
     v
  Pydantic         # validates your return value
     |
     v
HTTP Response
```

**Why FastAPI over Flask:** FastAPI is async-native (Flask is synchronous), has automatic input/output validation via Pydantic, auto-generates OpenAPI documentation, and is the standard in AI/ML backends today. Every production AI service you encounter will likely be FastAPI or a similar async framework.

---

## uvicorn — the ASGI server

FastAPI cannot receive HTTP connections directly. It needs an ASGI (Asynchronous Server Gateway Interface) server to handle the raw TCP work. uvicorn is that server.

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

- `main` — the Python file (`main.py`)
- `app` — the FastAPI instance in that file (`app = FastAPI()`)
- `--host 0.0.0.0` — listen on all interfaces (required in Codespaces/containers)
- `--port 8000` — which port

For development with auto-reload:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
`--reload` watches for file changes and restarts the server automatically. Do not use `--reload` in production — it has overhead and is not designed for it.

---

## The minimal FastAPI app

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "AOIS is running"}
```

That is a complete, working web server. `@app.get("/")` is a decorator that registers the function as the handler for GET requests to `/`. When a request arrives, FastAPI calls `root()` and serializes the returned dict to JSON.

---

## Auto-generated documentation

FastAPI generates interactive API documentation automatically. Start the server and visit:
- `http://localhost:8000/docs` — Swagger UI (interactive — you can send requests from the browser)
- `http://localhost:8000/redoc` — ReDoc (readable documentation)
- `http://localhost:8000/openapi.json` — raw OpenAPI spec

This is not something you configure. FastAPI generates it from your code — your Pydantic models, your route paths, your HTTP methods. In Codespaces, port-forward 8000 and open the URL in a browser.

---

## Request and response models

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Literal

app = FastAPI(
    title="AOIS — AI Operations Intelligence System",
    description="Log analysis API",
    version="0.6.0"
)

class LogInput(BaseModel):
    log: str = Field(description="Raw infrastructure log to analyze", min_length=1)

class IncidentAnalysis(BaseModel):
    summary: str
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float
    method: str     # v0.6 only: "regex" — to show what changed in v1
```

`LogInput` is what the caller sends. FastAPI reads the request body and validates it against this model. If the body is missing, not JSON, or missing required fields: FastAPI returns 422 automatically. You write zero validation code.

`IncidentAnalysis` is what you return. `response_model=IncidentAnalysis` on the route decorator tells FastAPI to validate your return value against this model before sending it.

---

## The full mock endpoint

Create `/workspaces/aois-system/practice/mock_api.py`:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
import re

app = FastAPI(
    title="AOIS v0.6 — No AI Yet",
    description="Regex-based log analysis. Shows the limitation this approach hits.",
    version="0.6.0"
)


class LogInput(BaseModel):
    log: str = Field(description="Raw infrastructure log", min_length=1, max_length=5000)


class IncidentAnalysis(BaseModel):
    summary: str
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float
    method: str


# Pattern-based rules — what you had to write before LLMs
PATTERNS = [
    {
        "pattern": re.compile(r"CrashLoopBackOff", re.IGNORECASE),
        "severity": "P1",
        "summary": "Pod is in CrashLoopBackOff — repeatedly crashing",
        "action": "Check pod logs: kubectl logs <pod> --previous. Fix crash cause.",
        "confidence": 0.90
    },
    {
        "pattern": re.compile(r"OOMKilled", re.IGNORECASE),
        "severity": "P2",
        "summary": "Container OOMKilled — exceeded memory limit",
        "action": "Increase memory limit in pod spec or optimize memory usage",
        "confidence": 0.85
    },
    {
        "pattern": re.compile(r"HTTP\s+5[0-9]{2}|503|500|502", re.IGNORECASE),
        "severity": "P2",
        "summary": "HTTP 5xx errors detected — service returning errors",
        "action": "Check application logs and upstream dependencies",
        "confidence": 0.75
    },
    {
        "pattern": re.compile(r"disk.{0,20}[89][0-9]%|disk.{0,20}100%", re.IGNORECASE),
        "severity": "P3",
        "summary": "High disk usage — approaching capacity",
        "action": "Run: df -h to identify filesystem. Clear logs or expand storage.",
        "confidence": 0.80
    },
    {
        "pattern": re.compile(r"cert.{0,30}expir|TLS.{0,30}expir", re.IGNORECASE),
        "severity": "P3",
        "summary": "TLS certificate expiring soon",
        "action": "Check cert-manager status. Renew certificate before expiry.",
        "confidence": 0.85
    },
    {
        "pattern": re.compile(r"connection refused|connection reset|ECONNREFUSED", re.IGNORECASE),
        "severity": "P2",
        "summary": "Connection refused — service unavailable or port closed",
        "action": "Verify target service is running and the correct port is open",
        "confidence": 0.70
    },
]


def analyze_with_regex(log: str) -> IncidentAnalysis:
    for rule in PATTERNS:
        if rule["pattern"].search(log):
            return IncidentAnalysis(
                summary=rule["summary"],
                severity=rule["severity"],
                suggested_action=rule["action"],
                confidence=rule["confidence"],
                method="regex"
            )

    # No pattern matched — default to low severity
    return IncidentAnalysis(
        summary="No known incident pattern detected",
        severity="P4",
        suggested_action="Review log manually — no automated rule matched this pattern",
        confidence=0.2,   # low confidence: we literally don't know
        method="regex"
    )


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.6.0"}


@app.post("/analyze", response_model=IncidentAnalysis)
def analyze(data: LogInput) -> IncidentAnalysis:
    return analyze_with_regex(data.log)
```

Run it:
```bash
uvicorn practice.mock_api:app --host 0.0.0.0 --port 8001 --reload
```

Test the patterns that work:
```bash
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "pod/payment-service OOMKilled memory_limit=512Mi restarts=14"}' \
  | python3 -m json.tool

curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "BackOff pod/auth-service CrashLoopBackOff restarts=8"}' \
  | python3 -m json.tool
```

Now test what breaks it:
```bash
# Vague log — no specific pattern
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "payment service is responding slowly, latency p99 is 8 seconds"}' \
  | python3 -m json.tool
# severity: P4, confidence: 0.2 — it has no idea

# Unfamiliar format
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "[CRITICAL] GPU memory exhausted on node/gpu-worker-1 during model inference"}' \
  | python3 -m json.tool
# P4 — missed a clearly critical incident

# Context that changes severity
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "TEST: OOMKilled in staging environment non-production pod/test-runner"}' \
  | python3 -m json.tool
# Still P2 — the word "TEST" and "staging" mean nothing to regex
```

That last one is the key failure: regex has no concept of context. "OOMKilled in staging" gets the same severity as "OOMKilled in production". v1 handles this correctly.

---

## Path parameters and query parameters

```python
# Path parameter: /incidents/123
@app.get("/incidents/{incident_id}")
def get_incident(incident_id: int):
    return {"id": incident_id}

# Query parameter: /incidents?severity=P1&limit=10
@app.get("/incidents")
def list_incidents(severity: str | None = None, limit: int = 20):
    return {"severity": severity, "limit": limit}

# Both
@app.get("/services/{service_name}/logs")
def get_service_logs(service_name: str, lines: int = 100):
    return {"service": service_name, "lines": lines}
```

FastAPI extracts path parameters from the URL path automatically. Query parameters come from the URL query string (`?key=value`). Both are validated against their type annotations.

---

## HTTPException — returning error responses

```python
from fastapi import HTTPException

@app.post("/analyze")
def analyze(data: LogInput):
    if len(data.log.strip()) == 0:
        raise HTTPException(
            status_code=400,
            detail="Log cannot be empty"
        )

    if len(data.log) > 5000:
        raise HTTPException(
            status_code=413,
            detail=f"Log too large: {len(data.log)} bytes. Maximum: 5000"
        )

    return analyze_with_regex(data.log)
```

When you raise `HTTPException`, FastAPI catches it and returns an HTTP response with that status code and detail. The rest of your function does not execute.

---

## Middleware — code that runs on every request

```python
import time
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    print(f"{request.method} {request.url.path} → {response.status_code} ({duration:.3f}s)")
    return response
```

Middleware wraps every request. This one logs the method, path, response code, and duration for every call. In production AOIS, middleware handles rate limiting, authentication, payload size checks, and request tracing.

---

## What you see versus what v1 adds

| Capability | v0.6 (regex) | v1 (Claude) |
|-----------|-------------|-------------|
| Known patterns | ✓ | ✓ |
| Unknown log formats | ✗ | ✓ |
| Context awareness | ✗ | ✓ |
| Confidence score | Fixed/guessed | Calibrated |
| Suggested action | Canned responses | Specific to the incident |
| Summary | Template string | Actual description |
| Handles staging vs prod | ✗ | ✓ |
| New incident types | Requires code change | Zero change needed |

The FastAPI structure, the Pydantic models, the `/health` endpoint, the error handling — all of that stays identical in v1. The only thing that changes is `analyze_with_regex()` becomes `analyze_with_claude()`.

That is the lesson: the infrastructure of an API does not change when you add AI. You are swapping the analysis function, not the server.
