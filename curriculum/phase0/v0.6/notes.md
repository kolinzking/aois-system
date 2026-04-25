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

## Common Mistakes

**Running FastAPI with `--reload` in production** *(recognition)*
`--reload` forks a child process that watches the filesystem and kills/restarts the server on any file change. In production, log rotation, temp file writes, or a config file touched by another process can trigger unexpected restarts mid-request.

*(recall — trigger it)*
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
sleep 2
ps aux | grep uvicorn
```
Expected: two uvicorn processes — the watcher parent and the server child.
```
codespace  1234  uvicorn main:app --reload         ← parent/watcher
codespace  1235  uvicorn main:app --reload (...)   ← actual server child
```
Now without `--reload`:
```bash
kill %1 2>/dev/null; sleep 1
uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 2
ps aux | grep uvicorn
kill %1 2>/dev/null
```
Expected: one process. In production there is no reason for two. `--reload` is a development flag only.

---

**Not handling exceptions → generic 500** *(recognition)*
When an unhandled exception escapes a FastAPI route, the framework catches it and returns HTTP 500 with no useful detail. The caller gets `Internal Server Error` and nothing actionable.

*(recall — trigger it)*
```bash
# Create a minimal FastAPI app that raises an unhandled exception
cat > /tmp/test_500.py << 'EOF'
from fastapi import FastAPI
app = FastAPI()

@app.get("/broken")
async def broken():
    raise ValueError("something went wrong internally")

@app.get("/handled")
async def handled():
    from fastapi import HTTPException
    raise HTTPException(status_code=503, detail="Dependency unavailable. Retry in 30s.")
EOF

uvicorn /tmp/test_500:app --port 8002 &
sleep 2

curl -s http://localhost:8002/broken | python3 -m json.tool
echo "---"
curl -s http://localhost:8002/handled | python3 -m json.tool
kill %1 2>/dev/null
```
Expected from `/broken`:
```json
{"detail": "Internal Server Error"}
```
Expected from `/handled`:
```json
{"detail": "Dependency unavailable. Retry in 30s."}
```
The unhandled exception gives the caller nothing useful. The `HTTPException` gives them a specific message and a status code they can act on. Every external call (API, database) gets a try/except that raises `HTTPException`.

---

**Returning a dict instead of a Pydantic response model** *(recognition)*
FastAPI will serialize a plain dict — but you lose validation, you lose the OpenAPI schema at `/docs`, and you lose type safety. The `/docs` endpoint shows `{}` for the response body instead of the actual schema.

*(recall — trigger it)*
```bash
cat > /tmp/test_schema.py << 'EOF'
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Analysis(BaseModel):
    severity: str
    summary: str

@app.get("/dict-response")
async def dict_response():
    return {"severity": "P2", "summary": "disk pressure"}   # plain dict

@app.get("/model-response", response_model=Analysis)
async def model_response():
    return Analysis(severity="P2", summary="disk pressure")  # Pydantic model
EOF

uvicorn /tmp/test_schema:app --port 8003 &
sleep 2

# Check the OpenAPI schema for both endpoints
curl -s http://localhost:8003/openapi.json | python3 -c "
import json, sys
spec = json.load(sys.stdin)
print('dict endpoint schema:')
print(json.dumps(spec['paths']['/dict-response']['get'].get('responses', {}), indent=2))
print('model endpoint schema:')
print(json.dumps(spec['paths']['/model-response']['get'].get('responses', {}), indent=2))
"
kill %1 2>/dev/null
```
The dict endpoint's response schema will be empty or `{}`. The model endpoint's response schema will show every field with its type. This is what gets generated in `/docs` — the model response is self-documenting.

---

**CORS not configured for browser access** *(recognition)*
Browsers enforce same-origin policy — a page on `localhost:3000` cannot call an API on `localhost:8000` without CORS headers. curl and server-to-server calls are not affected — only browsers. The error appears in the browser console, not the server logs.

*(recall — trigger it)*
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 2

# Simulate what a browser does — send an Origin header (curl cannot fully replicate browser CORS
# but you can see what headers the server returns)
curl -v -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS http://localhost:8000/analyze 2>&1 | grep -i "access-control"
kill %1 2>/dev/null
```
Expected: no `Access-Control-Allow-Origin` header in the response. A browser receiving this response will block the request entirely — the JavaScript fetch call never completes. The error in the browser DevTools console reads: `CORS policy: No 'Access-Control-Allow-Origin' header`. Adding `CORSMiddleware` makes the header appear. curl never needs it — only browsers.

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
- **v1 (AOIS Core)**: The mock regex endpoint you built here is replaced in v1 with a real Claude API call. Same FastAPI structure, same routes — the AI drops in where the regex was.

---


## Build-It-Blind Challenge

Close the notes. From memory: write the AOIS `/analyze` endpoint — POST, accepts `IncidentLog`, returns `AnalysisResult`, includes a mock implementation that always returns P3, a liveness probe at `/health`, and a startup message with uvicorn. 20 minutes.

```bash
uvicorn main:app --reload &
curl -s http://localhost:8000/health | jq .
# {"status": "ok"}
curl -s -X POST http://localhost:8000/analyze   -H "Content-Type: application/json"   -d '{"log": "OOMKilled"}' | jq .severity
# "P3"
```

---

## Failure Injection

Break the endpoint in two ways and read each error:

```python
# Break 1: missing async
@app.post("/analyze")
def analyze(payload: IncidentLog):   # synchronous — what happens under load?
    import time; time.sleep(2)
    return AnalysisResult(...)

# Break 2: wrong return type
@app.post("/analyze")
async def analyze(payload: IncidentLog):
    return {"severity": "P3"}   # dict not AnalysisResult — does FastAPI accept it?
```

Run both. Read the responses. Understand what FastAPI validates and what it does not.

---

## Osmosis Check

1. Your `/analyze` endpoint receives a request body. Which HTTP header must the client set, and what status does FastAPI return if it is missing? (v0.4)
2. The `IncidentLog` model rejects payloads over 5KB. Where in the FastAPI stack do you enforce that — in the Pydantic model or as middleware — and why does the choice matter? (v0.5)

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

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### FastAPI

| Layer | |
|---|---|
| **Plain English** | A framework for building web APIs in Python — it handles receiving requests, routing them to the right function, validating the data, and sending back responses. |
| **System Role** | FastAPI is the AOIS web layer. Every `/analyze` call, every health check, every webhook goes through FastAPI. It is the front door. Everything else — LLM routing, Kafka publishing, metric recording — happens inside its route handlers. |
| **Technical** | An async Python web framework built on Starlette (ASGI) and Pydantic. Route handlers are Python async functions decorated with `@app.post()`, `@app.get()`, etc. Pydantic models define request/response schemas, which FastAPI uses to auto-validate and auto-document. Runs on uvicorn (ASGI server). |
| **Remove it** | Without FastAPI, there is no HTTP interface. The LLM analysis logic exists but has no way to receive requests. You would need to replace it with Flask, Django, or write raw ASGI/WSGI — all slower to develop and less integrated with Pydantic. The OpenAPI docs at `/docs` disappear entirely. |

**Say it at three levels:**
- *Non-technical:* "FastAPI is the receptionist for my application. When a request arrives, it checks it's valid, passes it to the right function, and sends back the answer."
- *Junior engineer:* "`@app.post('/analyze', response_model=IncidentAnalysis)` — FastAPI validates the request body, calls my function, validates the return value, and serves it as JSON. The `/docs` endpoint is generated automatically from Pydantic models — I never write API documentation by hand."
- *Senior engineer:* "FastAPI's async handlers via uvicorn mean a single process handles thousands of concurrent requests without threads. Route handlers should never block — any synchronous I/O (Postgres, sync HTTP client) blocks the event loop and kills throughput. Use `httpx.AsyncClient`, `asyncpg`, and `aioredis`. In production, run behind nginx with multiple uvicorn workers."

---

### uvicorn

| Layer | |
|---|---|
| **Plain English** | The engine that actually runs a FastAPI application and listens for incoming requests. FastAPI defines what to do with requests; uvicorn is what makes it actually listen. |
| **System Role** | uvicorn is the process running inside the AOIS Docker container. When Kubernetes sends a health check to port 8000, uvicorn receives it. When the KEDA ScaledObject spawns a new pod, uvicorn starts and begins accepting requests within seconds. |
| **Technical** | An ASGI (Asynchronous Server Gateway Interface) server built on `uvloop` (a high-performance event loop) and `httptools`. ASGI is the async successor to WSGI — it supports WebSockets, HTTP/2, and long-lived connections that WSGI cannot. Configured via CLI: `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4`. |
| **Remove it** | Without uvicorn (or another ASGI server like Hypercorn), a FastAPI application is just a Python object — it cannot receive network traffic. `uvicorn main:app` is the command that turns code into a running service. |

**Say it at three levels:**
- *Non-technical:* "uvicorn is what makes the application accessible over the network. FastAPI is the recipe; uvicorn is the restaurant that serves it."
- *Junior engineer:* "`uvicorn main:app --reload` for development (auto-reloads on file change), `uvicorn main:app --workers 4` for production (4 parallel workers). `--host 0.0.0.0` makes it accessible from outside the container — `127.0.0.1` (default) would only accept connections from inside the container."
- *Senior engineer:* "Single-worker uvicorn is fine for development; in production, `--workers $(nproc)` workers, each with their own event loop. For async code, one worker per CPU core is typically optimal — threads are not used, so there's no GIL contention. For Kubernetes, use `--workers 1` per pod and scale horizontally via KEDA instead of vertically via workers — it gives you better scaling granularity and resource isolation."

---

### OpenAPI / Swagger (`/docs`)

| Layer | |
|---|---|
| **Plain English** | Automatically generated interactive documentation for your API — it shows every endpoint, what it accepts, what it returns, and lets you try it directly in the browser. |
| **System Role** | FastAPI generates `/docs` (Swagger UI) and `/redoc` automatically from Pydantic models and route definitions. During development, it is the primary testing interface. In v27 (auth), it will be secured behind JWT. |
| **Technical** | OpenAPI Specification (formerly Swagger) is a JSON schema that describes every endpoint, request body, response schema, and authentication mechanism. FastAPI derives this from Python type annotations — no separate specification file needed. Available at `/openapi.json`; Swagger UI renders it interactively at `/docs`. |
| **Remove it** | Without OpenAPI, API consumers have no machine-readable contract. Integration testing requires reading source code. Clients cannot auto-generate SDK code. In a team, `/docs` is the shared contract — the difference between "what does this endpoint accept?" taking 30 seconds vs. reading Python source. |

**Say it at three levels:**
- *Non-technical:* "The `/docs` page lets anyone test the API through a web form. No code needed — just open the browser and click."
- *Junior engineer:* "FastAPI generates `/docs` from my Pydantic models. If I add a new field to `IncidentAnalysis`, the docs update automatically. The `/openapi.json` is machine-readable — client libraries can be generated from it automatically."
- *Senior engineer:* "OpenAPI is a contract. In a microservices environment, the OpenAPI spec is versioned alongside the code and validated in CI — breaking changes to request/response schemas are detected before merge. FastAPI's auto-generation is great for development speed; in a team, you add explicit examples and `description` fields to make the generated spec useful as a real contract."
