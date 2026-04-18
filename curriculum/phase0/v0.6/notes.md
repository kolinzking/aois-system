# v0.6 — Your First API (No AI)
⏱ **Estimated time: 3–5 hours**

## What this version is about

Before adding AI, you need to understand the API container it lives in. This version builds a complete, working FastAPI server — with routing, validation, error handling, middleware, and auto-generated documentation — without a single LLM call.

At the end, you will test it with the same `curl` commands used in every version after this, and you will see exactly where regex breaks down. v1 swaps one function and everything changes.

---

## Prerequisites

- v0.1–v0.5 complete
- FastAPI and uvicorn installed

Verify:
```bash
python3 -c "import fastapi; print(fastapi.__version__)"
python3 -c "import uvicorn; print(uvicorn.__version__)"
```
Expected: version numbers, no errors. If you get `ModuleNotFoundError`:
```bash
pip install fastapi uvicorn
```

---

## Learning goals

By the end of this version you will:
- Understand what FastAPI is and why it exists
- Know what uvicorn does and why it is separate from FastAPI
- Build an endpoint that validates input, processes it, and returns typed output
- Use path parameters, query parameters, and request bodies
- Handle errors with `HTTPException`
- Write middleware that runs on every request
- Read the auto-generated OpenAPI documentation
- Understand the exact limitations of regex-based analysis

---

## Part 1 — What FastAPI is and why it matters

FastAPI is a Python web framework for building APIs. It sits on top of two libraries:
- **Starlette** — the async web framework (routing, middleware, requests, responses)
- **Pydantic** — data validation (already covered in v0.5)

FastAPI's job: receive an HTTP request, route it to the right function, validate the input, run your code, validate the output, send the response.

**Why FastAPI over Flask or Django?**
- Flask is synchronous by default — one request blocks while waiting for I/O
- Django is a full web framework designed for HTML apps — too heavy for an API
- FastAPI is async-native, fast, has automatic Pydantic validation, auto-generates OpenAPI docs

The AI engineering world standardized on FastAPI. Every production AI service you encounter will likely use it or a similar async framework.

---

## Part 2 — uvicorn: the ASGI server

FastAPI cannot receive HTTP connections directly. It implements the ASGI interface — a specification for how web apps receive requests. You need an ASGI server to handle the raw network part.

uvicorn is that server.

```
Internet/curl
      │
      ▼
   uvicorn          ← handles TCP connections, HTTP parsing, TLS
      │
      ▼
   FastAPI           ← routes requests, validates data, calls your functions
      │
      ▼
  Your function      ← your business logic
```

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

- `main` — the Python module name (filename without `.py`)
- `app` — the FastAPI instance variable name inside that module
- `--host 0.0.0.0` — listen on all network interfaces (required in Codespaces/containers)
- `--port 8000` — port number

For development with auto-reload (restarts on file changes):
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Do NOT use `--reload` in production — it has a significant performance overhead.

Kill it when you need to restart:
```bash
lsof -ti:8000 | xargs kill -9
```

---

## Part 3 — The minimal app

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "AOIS is running"}
```

That is a complete web server. Three lines of logic.

`@app.get("/")` is a decorator that registers `root()` as the handler for GET requests to `/`.

When a request arrives: uvicorn receives it, passes it to FastAPI, FastAPI sees the path `/` and method GET, calls `root()`, takes the returned dict, serializes it to JSON, sends the HTTP response.

---

## Part 4 — Request and response models

These are Pydantic models (v0.5) attached to FastAPI endpoints.

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Literal

app = FastAPI(
    title="AOIS — AI Operations Intelligence System",
    description="Log incident analysis API",
    version="0.6.0"
)

class LogInput(BaseModel):
    log: str = Field(
        description="Raw infrastructure log to analyze",
        min_length=1,
        max_length=5000
    )

class IncidentAnalysis(BaseModel):
    summary: str
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float
    method: str    # "regex" in v0.6, "claude" from v1 onwards
```

When FastAPI receives a POST request with a JSON body, it:
1. Parses the JSON
2. Validates it against `LogInput`
3. If valid: creates a `LogInput` instance, passes it to your function
4. If invalid: automatically returns HTTP 422 with a detailed error message — you write zero validation code

`response_model=IncidentAnalysis` on the route decorator:
1. FastAPI validates your return value against `IncidentAnalysis`
2. If it does not match: raises an error before sending (catches bugs)
3. Filters the output — if your function returns extra fields, they are removed

---

> **▶ STOP — do this now**
>
> Open a Python REPL and test FastAPI validation before building the full app:
> ```python
> python3 << 'EOF'
> from pydantic import BaseModel
> from fastapi import FastAPI
> from fastapi.testclient import TestClient
>
> class LogInput(BaseModel):
>     log: str
>
> app = FastAPI()
>
> @app.post("/analyze")
> def analyze(data: LogInput):
>     return {"received": data.log, "length": len(data.log)}
>
> client = TestClient(app)
>
> # Valid request
> r = client.post("/analyze", json={"log": "OOMKilled pod/payment"})
> print("Valid:", r.status_code, r.json())
>
> # Missing field
> r = client.post("/analyze", json={})
> print("Missing:", r.status_code, r.json()["detail"][0]["msg"])
>
> # Wrong type
> r = client.post("/analyze", json={"log": 12345})
> print("Wrong type:", r.status_code)
> EOF
> ```
> FastAPI returns 422 on invalid input automatically. You wrote zero validation logic.

---

## Part 5 — Path parameters, query parameters, request body

Three ways data reaches your endpoint:

```python
# Path parameter — part of the URL path
# URL: GET /incidents/42
@app.get("/incidents/{incident_id}")
def get_incident(incident_id: int):    # FastAPI extracts "42" and converts to int
    return {"id": incident_id}

# Query parameter — after ? in the URL
# URL: GET /incidents?severity=P1&limit=10
@app.get("/incidents")
def list_incidents(
    severity: str | None = None,    # optional, defaults to None
    limit: int = 20                  # optional, defaults to 20
):
    return {"severity": severity, "limit": limit}

# Request body — for POST/PUT
# Body: {"log": "OOMKilled...", "tier": "premium"}
@app.post("/analyze")
def analyze(data: LogInput):         # entire body validated as LogInput
    return {"received": data.log}
```

Test them:
```bash
# Path parameter
curl http://localhost:8000/incidents/42

# Query parameters
curl "http://localhost:8000/incidents?severity=P1&limit=5"

# Request body
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment"}'
```

---

> **▶ STOP — do this now**
>
> Before building the full mock API, start the current AOIS server and test all three data input patterns:
> ```bash
> # Terminal 1
> cd /workspaces/aois-system && uvicorn main:app --port 8000
>
> # Terminal 2 — test all three patterns
> curl -s http://localhost:8000/health                     # path with no params
> curl -s "http://localhost:8000/docs" | head -5           # query the OpenAPI docs endpoint
> curl -s -X POST http://localhost:8000/analyze \
>   -H "Content-Type: application/json" \
>   -d '{"log": "test log"}' | python3 -m json.tool       # request body
> ```
> Stop the server when done. You just confirmed that v5 AOIS handles all three patterns. The mock API you are about to build follows the same pattern — just without the real AI.

---

## Part 6 — The complete mock_api.py

Create the file:

```bash
cat > /workspaces/aois-system/practice/mock_api.py << 'EOF'
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Literal
import re
import time

app = FastAPI(
    title="AOIS v0.6 — No AI Yet",
    description="Regex-based log analysis. Demonstrates what AI replaces.",
    version="0.6.0"
)


# ── Models ───────────────────────────────────────────────────────────────────

class LogInput(BaseModel):
    log: str = Field(
        description="Raw infrastructure log to analyze",
        min_length=1,
        max_length=5000
    )


class IncidentAnalysis(BaseModel):
    summary: str
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float
    method: str = "regex"


# ── Pattern rules ─────────────────────────────────────────────────────────────
# Each rule has a pattern, and a fixed response.
# Adding a new incident type = adding a new dict here + testing it.
# This is what scales badly in production.

PATTERNS = [
    {
        "pattern": re.compile(r"CrashLoopBackOff", re.IGNORECASE),
        "severity": "P1",
        "summary": "Pod is in CrashLoopBackOff — repeatedly crashing on startup",
        "action": "Run: kubectl logs <pod-name> --previous\nCheck exit code and crash reason",
        "confidence": 0.90
    },
    {
        "pattern": re.compile(r"OOMKilled", re.IGNORECASE),
        "severity": "P2",
        "summary": "Container OOMKilled — exceeded its memory limit",
        "action": "Increase memory limit in pod spec or investigate memory leak",
        "confidence": 0.85
    },
    {
        "pattern": re.compile(r"HTTP\s*5\d{2}|503|500|502", re.IGNORECASE),
        "severity": "P2",
        "summary": "HTTP 5xx errors detected — service returning server errors",
        "action": "Check application logs and upstream service health",
        "confidence": 0.75
    },
    {
        "pattern": re.compile(r"disk.{0,20}[89][0-9]%|disk.{0,20}100%", re.IGNORECASE),
        "severity": "P3",
        "summary": "High disk usage — filesystem approaching capacity",
        "action": "Run: df -h to identify filesystem\nClean logs or expand storage",
        "confidence": 0.80
    },
    {
        "pattern": re.compile(r"cert.{0,30}expir|TLS.{0,30}expir", re.IGNORECASE),
        "severity": "P3",
        "summary": "TLS certificate expiring soon — renewal required",
        "action": "Check cert-manager status\nManually renew if auto-renewal is failing",
        "confidence": 0.85
    },
    {
        "pattern": re.compile(r"connection refused|ECONNREFUSED", re.IGNORECASE),
        "severity": "P2",
        "summary": "Connection refused — target service is not accepting connections",
        "action": "Verify target service is running and listening on the expected port",
        "confidence": 0.70
    },
    {
        "pattern": re.compile(r"node.*not ready|node.*unreachable", re.IGNORECASE),
        "severity": "P1",
        "summary": "Kubernetes node is not ready or unreachable",
        "action": "Check node status: kubectl describe node <node-name>\nInvestigate kubelet logs",
        "confidence": 0.88
    },
]


# ── Analysis logic ────────────────────────────────────────────────────────────

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

    # No pattern matched — this is the critical failure mode
    return IncidentAnalysis(
        summary="No known incident pattern detected in this log",
        severity="P4",
        suggested_action="Review log manually — no automated pattern matched",
        confidence=0.1,    # 10%: we genuinely do not know
        method="regex"
    )


# ── Middleware ─────────────────────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    print(f"{request.method} {request.url.path} → {response.status_code} ({duration:.1f}ms)")
    return response


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.6.0", "method": "regex"}


@app.post("/analyze", response_model=IncidentAnalysis)
def analyze(data: LogInput) -> IncidentAnalysis:
    return analyze_with_regex(data.log)


@app.get("/patterns")
def list_patterns():
    """Shows all patterns this version knows about. v1 has no equivalent endpoint
    because Claude knows everything — not a fixed list."""
    return {
        "count": len(PATTERNS),
        "patterns": [p["pattern"].pattern for p in PATTERNS],
        "note": "v1 replaces this fixed list with Claude's trained knowledge"
    }
EOF
```

---

## Part 7 — Run and test it

### Start the server

```bash
cd /workspaces/aois-system
python3 -m uvicorn practice.mock_api:app --host 0.0.0.0 --port 8001 --reload
```

Expected startup output:
```
INFO:     Will watch for changes in these directories: ['/workspaces/aois-system']
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
INFO:     Started reloader process [1234] using StatReload
INFO:     Started server process [1235]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Test the health endpoint

In a second terminal:
```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```
Expected:
```json
{
    "status": "ok",
    "version": "0.6.0",
    "method": "regex"
}
```

### Test patterns that work

```bash
# CrashLoopBackOff — should be P1
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "Warning BackOff pod/auth-service CrashLoopBackOff restarts=8 in 10m"}' \
  | python3 -m json.tool
```
Expected:
```json
{
    "summary": "Pod is in CrashLoopBackOff — repeatedly crashing on startup",
    "severity": "P1",
    "suggested_action": "Run: kubectl logs <pod-name> --previous\nCheck exit code and crash reason",
    "confidence": 0.9,
    "method": "regex"
}
```

```bash
# OOMKilled — should be P2
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "FATAL pod/payment-service OOMKilled memory_limit=512Mi exit_code=137 restarts=14"}' \
  | python3 -m json.tool
```
Expected:
```json
{
    "summary": "Container OOMKilled — exceeded its memory limit",
    "severity": "P2",
    ...
    "confidence": 0.85
}
```

### Test what breaks it

```bash
# Vague but serious log — latency spike
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "payment service response time increased to 8 seconds, normal is 200ms, all replicas affected"}' \
  | python3 -m json.tool
```
Expected: `severity: "P4"`, `confidence: 0.1`. This is a serious incident — payment service is 40x slower — but the regex has no idea.

```bash
# Context the regex ignores: staging environment
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "TEST: OOMKilled in staging env pod/test-runner non-production load test"}' \
  | python3 -m json.tool
```
Expected: `severity: "P2"`. The regex sees "OOMKilled" and fires P2. But this is a test in staging — it should be P4 or informational. Regex cannot distinguish context.

```bash
# GPU memory — cloud-native issue the regex does not know
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "[CRITICAL] CUDA out of memory on node/gpu-worker-1 during model inference, 24GB exhausted"}' \
  | python3 -m json.tool
```
Expected: `severity: "P4"`. The log says CRITICAL explicitly. Regex still says P4 because it has no CUDA pattern.

```bash
# See all the patterns this version knows
curl -s http://localhost:8001/patterns | python3 -m json.tool
```
Expected: 7 patterns. That is all it knows. Everything else is P4.

### Test validation

```bash
# Missing log field — should be 422
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"message": "wrong field name"}' \
  | python3 -m json.tool
```
Expected:
```json
{
    "detail": [
        {
            "type": "missing",
            "loc": ["body", "log"],
            "msg": "Field required"
        }
    ]
}
```
FastAPI returned this automatically — you wrote zero validation code.

```bash
# Empty log — min_length=1 should reject it
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": ""}' \
  | python3 -m json.tool
```
Expected: 422 with validation error about minimum length.

### View the auto-generated docs

Open in your browser (forward port 8001 in Codespaces):
```
http://localhost:8001/docs
```

You will see every endpoint, its input/output schemas, and an interactive form to test it. This is generated entirely from your Pydantic models and decorator annotations — you did not write any documentation.

---

> **▶ STOP — do this now**
>
> Test every endpoint in `mock_api.py` and record what `severity` each one returns:
> ```bash
> # OOMKilled
> curl -s -X POST http://localhost:8001/analyze \
>   -H "Content-Type: application/json" \
>   -d '{"log": "OOMKilled pod/payment-service"}' | python3 -m json.tool
>
> # CrashLoopBackOff
> curl -s -X POST http://localhost:8001/analyze \
>   -H "Content-Type: application/json" \
>   -d '{"log": "CrashLoopBackOff pod/auth-service restarts: 8"}' | python3 -m json.tool
>
> # Something the regex cannot recognize
> curl -s -X POST http://localhost:8001/analyze \
>   -H "Content-Type: application/json" \
>   -d '{"log": "checkout p99 latency increased from 180ms to 12000ms"}' | python3 -m json.tool
> ```
> Record what `severity` and `suggested_action` the last test returns. That latency spike is P1 in any SRE handbook — but the regex has no rule for it. Write down exactly what v0.6 gets wrong. When v1 comes back with the right answer, you will know exactly what changed.

---

## Part 8 — HTTPException: returning errors

```python
from fastapi import HTTPException

@app.post("/analyze")
def analyze(data: LogInput):
    # Business logic validation (beyond Pydantic's schema validation)
    if data.log.strip() == "test":
        raise HTTPException(
            status_code=400,
            detail="'test' is not a real log — send actual infrastructure logs"
        )

    return analyze_with_regex(data.log)
```

Test it:
```bash
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "test"}' \
  | python3 -m json.tool
```
Expected (if you added the test above):
```json
{
    "detail": "'test' is not a real log — send actual infrastructure logs"
}
```
HTTP status: 400.

---

## Part 9 — What v0.6 cannot do (what v1 fixes)

Run this comparison:

```bash
# Log 1: works perfectly in v0.6
echo "Testing known pattern (CrashLoopBackOff):"
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "CrashLoopBackOff pod/auth restarts=8"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  severity={d[\"severity\"]}, confidence={d[\"confidence\"]}')"

# Log 2: completely fails in v0.6
echo "Testing unknown pattern (latency spike):"
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "p99 latency for checkout service spiked to 12s, up from 180ms baseline, affecting 100% of users"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  severity={d[\"severity\"]}, confidence={d[\"confidence\"]}')"
```

Expected:
```
Testing known pattern (CrashLoopBackOff):
  severity=P1, confidence=0.9
Testing unknown pattern (latency spike):
  severity=P4, confidence=0.1
```

The second log describes a P1 incident. Every user is affected. Checkout is down. v0.6 says P4 with 10% confidence.

v1 swaps `analyze_with_regex()` for `analyze_with_claude()`. Everything else — the FastAPI app, the models, the endpoint, the tests, the curl commands — stays identical. The intelligence changes. The infrastructure does not.

---

## Troubleshooting

**"Address already in use" on port 8001:**
```bash
lsof -ti:8001 | xargs kill -9
```

**FastAPI returns 404 for /analyze:**
You are running the wrong file or the wrong port. Check:
```bash
ps aux | grep uvicorn    # see what is running
curl http://localhost:8001/health    # test if server is responding at all
```

**"ModuleNotFoundError: No module named 'practice.mock_api'":**
You are not in the project root, or the `practice/` directory is missing an `__init__.py`. Either:
```bash
# Option 1: run from project root
cd /workspaces/aois-system
python3 -m uvicorn practice.mock_api:app --port 8001

# Option 2: run the file directly
cd /workspaces/aois-system/practice
uvicorn mock_api:app --port 8001
```

**Reload is not picking up changes:**
`--reload` watches the current directory. Make sure you are in the project root and saving to the correct file.

---

## Connection to later phases

- **Phase 1 (v1)**: `analyze_with_regex()` becomes `analyze_with_claude()`. The FastAPI app, models, endpoint, and test commands are identical. This is the transformation point.
- **Phase 2 (v5)**: Middleware (the request logger above) becomes security middleware — rate limiting, payload size checks. Same pattern, different purpose.
- **Phase 8 (v26)**: The React dashboard calls these exact endpoints over WebSocket and HTTP. Understanding the API contract is essential for building the frontend.

---

## Mastery Checkpoint

v0.6 is the inflection point — the last version before AI. After these exercises you will feel the limitation viscerally, which makes v1 land hard.

**1. Add a new pattern to the regex analyzer and test its limits**
Add a pattern for "database connection pool exhausted" that returns P2. Test it with exactly the right wording. Then test with slightly different wording: "DB connection pool full", "connection pool at capacity", "too many database connections". Count how many variants work and how many return P4. This is what it means to maintain a regex-based system at scale.

**2. Understand every component of the FastAPI stack**
Answer these without running a command — then verify:
- What does `@app.post("/analyze", response_model=IncidentAnalysis)` actually do? (Two things: route binding AND response validation)
- What is the difference between a `400` and a `422` in FastAPI?
- What does `--reload` do in the uvicorn command and when would you NOT want it?
- What does `async def analyze(data: LogInput)` vs `def analyze(data: LogInput)` mean for performance?
- What happens if `analyze_with_regex()` returns `None`?

**3. Test the validation boundary**
FastAPI validates at two levels: Pydantic schema validation (422) and your code's HTTPException (400+). Send requests that trigger both:
- Schema validation failure: missing field, wrong type
- Business logic failure: any input your code deliberately rejects
Verify the response status code and body for each.

**4. Write a new endpoint from scratch**
Add a `GET /analyze/stats` endpoint to `mock_api.py` that returns:
```json
{
  "version": "0.6.0",
  "known_patterns": 7,
  "severity_distribution": {"P1": 1, "P2": 2, "P3": 2, "P4": 2}
}
```
No regex analysis needed — just aggregate the `PATTERNS` list. Write the response model first as a Pydantic class. Then implement the endpoint. Test it with curl.

**5. Feel the limitation**
Send these 5 logs to the mock API. Record the severity returned for each. Then write down what the correct severity should be, reasoning like a senior SRE:
1. `"auth service p50 latency 8s, baseline 50ms, 100% of users affected"`
2. `"certificate for api.internal.example.com expired 2 hours ago"`
3. `"TEST: simulating OOMKilled in staging for load test purposes, ignore"`
4. `"database disk at 93% capacity on prod-postgres-primary, write operations failing"`
5. `"GPU driver crash on inference-node-1, falling back to CPU inference, 10x slower"`

How many did the regex get right? This is the argument for v1.

**6. The architecture test**
Close all the notes and, from memory, explain to yourself:
- What FastAPI does (route, validate, respond)
- What Pydantic does (schema validation, type coercion)
- What uvicorn does (ASGI server, runs the event loop)
- How a request flows from `curl` to your function and back
- Why the test commands work identically in v0.6 and v1

If you can explain all of these clearly, you are ready for Phase 1.

**The mastery bar**: You should be able to rebuild this FastAPI app from scratch in 30 minutes — models, endpoint, middleware, and test commands. The framework is transparent; you understand what every line does.
