# v0.5 — Python for This Project

## What this version builds

The exact Python patterns used throughout AOIS — from scratch. Virtual environments, `.env` files, Pydantic models, type hints, async/await, error handling. Not Python from the beginning. Python as used in production AI engineering.

---

## Virtual environments — why they exist

Python packages are installed globally by default. If project A needs `pydantic==1.10` and project B needs `pydantic==2.0`, they conflict. Virtual environments solve this by giving each project its own isolated copy of Python and its packages.

```bash
# Create a virtual environment
python3 -m venv venv

# Activate it (Linux/Mac)
source venv/bin/activate

# Your prompt changes:
# (venv) codespace@machine:/workspaces/aois-system$

# Verify you're using the venv's Python
which python3        # should show: .../venv/bin/python3
python3 --version

# Install packages
pip install fastapi anthropic

# See what's installed
pip list
pip freeze                     # with exact versions — use for requirements.txt

# Save dependencies
pip freeze > requirements.txt

# Install from requirements.txt
pip install -r requirements.txt

# Deactivate
deactivate
```

The `venv/` directory should be in `.gitignore`. You commit `requirements.txt`, not `venv/`. Anyone who clones the repo runs `pip install -r requirements.txt` to recreate the environment.

---

## requirements.txt — the dependency contract

```
fastapi==0.115.0
uvicorn==0.30.0
anthropic==0.40.0
openai==1.50.0
litellm==1.50.0
instructor==1.4.0
langfuse==2.0.0
python-dotenv==1.0.1
pydantic==2.9.0
slowapi==0.1.9
```

Pin exact versions in production. This ensures the same behaviour on every machine, every deployment. A minor version bump in a dependency has broken production for many teams.

For development only, you can use `>=` ranges, but the requirements.txt used in Dockerfile should always be pinned.

---

## .env files — secrets never in code

```bash
# .env file (never committed to git)
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
DATABASE_URL=postgresql://user:pass@localhost:5432/aois
ENVIRONMENT=development
LOG_LEVEL=INFO
```

```python
from dotenv import load_dotenv
import os

load_dotenv()   # reads .env file, loads into environment

api_key = os.getenv("ANTHROPIC_API_KEY")
db_url = os.getenv("DATABASE_URL", "sqlite:///./default.db")  # with default
env = os.getenv("ENVIRONMENT", "development")

# Never do this:
api_key = "sk-ant-api03-hardcoded-key"   # key in git history forever
```

`load_dotenv()` must be called before `os.getenv()`. It reads the `.env` file and adds its key=value pairs to the process environment. In production (Docker, k8s), you do not use `.env` files — environment variables are injected directly by the runtime. `load_dotenv()` is a no-op if the file does not exist, so the same code works locally and in production.

---

## Type hints

Type hints tell you and your tools what type a variable holds. Python does not enforce them at runtime by default — but Pydantic does, and mypy/pyright use them for static checking.

```python
# Without type hints
def analyze(log, severity, confidence):
    pass

# With type hints — readable, tooling can catch bugs
def analyze(log: str, severity: str, confidence: float) -> dict:
    pass

# Common types
name: str = "collins"
count: int = 0
score: float = 0.95
active: bool = True
items: list[str] = ["P1", "P2", "P3"]
mapping: dict[str, int] = {"errors": 5, "warnings": 2}
maybe: str | None = None              # string or None

# From typing module
from typing import Optional, Union, Literal

severity: Literal["P1", "P2", "P3", "P4"] = "P1"   # only these values allowed
maybe_str: Optional[str] = None                      # same as str | None
either: Union[str, int] = "hello"                    # str or int
```

When you see `Literal["P1", "P2", "P3", "P4"]` in the AOIS codebase, it means that field will only accept exactly those four values. Pydantic enforces this at runtime — pass "Critical" and you get a validation error.

---

## Pydantic — the backbone of structured AI output

Pydantic is a data validation library. You define a model class with typed fields, and Pydantic validates, parses, and serializes data automatically.

```python
from pydantic import BaseModel, Field
from typing import Literal

# Define a model
class IncidentAnalysis(BaseModel):
    summary: str
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float = Field(ge=0.0, le=1.0)   # 0.0 to 1.0

# Create an instance — Pydantic validates on creation
analysis = IncidentAnalysis(
    summary="Payment service OOMKilled",
    severity="P1",
    suggested_action="Increase memory limits to 1Gi",
    confidence=0.95
)

print(analysis.severity)      # P1
print(analysis.model_dump())  # {'summary': '...', 'severity': 'P1', ...}
print(analysis.model_dump_json())  # JSON string

# Pydantic rejects invalid data
try:
    bad = IncidentAnalysis(
        summary="test",
        severity="Critical",    # not in Literal
        suggested_action="test",
        confidence=1.5          # > 1.0, violates ge/le constraint
    )
except Exception as e:
    print(e)    # validation error: 2 errors

# Parse from a dict (e.g., from an API response)
data = {
    "summary": "OOMKilled",
    "severity": "P2",
    "suggested_action": "Increase memory",
    "confidence": 0.8
}
analysis = IncidentAnalysis(**data)   # ** unpacks dict as keyword arguments
```

**Why this matters for AI:** Claude returns text. You can ask it to return JSON, but there is no guarantee it returns the right fields, the right types, or anything at all. Pydantic + Instructor (v3) solves this — the LLM response must conform to your Pydantic model or it gets rejected and retried.

---

## Field — adding constraints and documentation

```python
from pydantic import BaseModel, Field

class LogInput(BaseModel):
    log: str = Field(
        description="Raw infrastructure log line to analyze",
        min_length=1,
        max_length=5000
    )

class IncidentAnalysis(BaseModel):
    summary: str = Field(
        description="Plain English explanation of what happened and why it matters"
    )
    severity: Literal["P1", "P2", "P3", "P4"] = Field(
        description="P1=critical/production down, P2=high/degraded, P3=medium/warning, P4=low"
    )
    suggested_action: str = Field(
        description="Specific action the on-call engineer should take right now"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Model confidence 0.0-1.0"
    )
```

The `description` fields in Pydantic are not just for documentation — in v3, Instructor sends these descriptions to the LLM so it knows exactly what each field means. Better descriptions produce better outputs.

---

## Error handling

```python
# Basic try/except
try:
    result = analyze_with_claude(log)
except Exception as e:
    print(f"Error: {e}")

# Catch specific exceptions
import anthropic

try:
    result = anthropic_client.messages.create(...)
except anthropic.APIConnectionError as e:
    print("Network error — could not reach Anthropic")
except anthropic.AuthenticationError as e:
    print("Invalid API key")
except anthropic.RateLimitError as e:
    print("Rate limited — too many requests")
except anthropic.APIStatusError as e:
    print(f"API error {e.status_code}: {e.message}")
except Exception as e:
    print(f"Unexpected error: {type(e).__name__}: {e}")
finally:
    pass   # always runs, even if exception occurred

# Re-raise
try:
    result = analyze_with_claude(log)
except anthropic.RateLimitError:
    try:
        result = analyze_with_openai(log)   # try fallback
    except Exception:
        raise   # re-raise if fallback also fails
```

In FastAPI, unhandled exceptions become 500 responses. You want to catch provider-specific exceptions and return meaningful errors rather than letting FastAPI expose raw exception messages.

---

## Async/await

FastAPI is async. Understanding why matters, even if the pattern feels mechanical at first.

```python
import asyncio
import httpx

# Synchronous — blocks: nothing else can run while waiting
def get_data_sync():
    response = requests.get("https://api.example.com/data")  # blocks
    return response.json()

# Asynchronous — non-blocking: other requests can be handled while waiting
async def get_data_async():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")  # yields control
    return response.json()
```

**Why it matters for AOIS:** when your FastAPI server receives 10 simultaneous requests, synchronous code handles them one at a time — each blocks while waiting for Claude to respond. Async code handles all 10 concurrently — while waiting for Claude on request 1, it handles requests 2-10. One uvicorn worker can serve hundreds of concurrent requests with async.

```python
# FastAPI async endpoint
@app.post("/analyze")
async def analyze(data: LogInput) -> IncidentAnalysis:
    result = await analyze_with_claude(data.log)   # non-blocking wait
    return result
```

In practice for Phase 1: the Anthropic SDK's async client is `AsyncAnthropic`. `await client.messages.create(...)` is the call. The pattern appears identically to synchronous code except for `async def` and `await` keywords.

---

## f-strings and common string patterns

```python
model = "claude-opus-4-6"
tokens = 1024
cost = 0.0042

# f-string interpolation
print(f"Model: {model}, tokens: {tokens}, cost: ${cost:.4f}")
# Output: Model: claude-opus-4-6, tokens: 1024, cost: $0.0042

# Multi-line string
system_prompt = """
You are AOIS — AI Operations Intelligence System.
Analyze infrastructure logs and classify incidents.
"""

# String methods
log = "  ERROR: OOMKilled pod/payment-service  "
log.strip()           # remove leading/trailing whitespace
log.lower()           # lowercase
log.upper()           # uppercase
log.replace("ERROR", "[ERROR]")
log.split(":")        # split into list by delimiter
"OOMKilled" in log    # True/False membership test
log.startswith("ERROR")
log.endswith("service")
```

---

## List and dict comprehensions

```python
logs = ["ERROR oom", "INFO healthy", "ERROR crashloop", "WARN disk"]

# Filter: keep only ERROR lines
errors = [log for log in logs if log.startswith("ERROR")]
# ['ERROR oom', 'ERROR crashloop']

# Transform: uppercase everything
upper_logs = [log.upper() for log in logs]

# Dict comprehension
severities = {"payment": "P1", "auth": "P2", "cache": "P4"}
critical = {k: v for k, v in severities.items() if v == "P1"}
# {'payment': 'P1'}
```

---

## Importing and structuring code

```python
# Standard library
import os
import json
import re
from datetime import datetime
from typing import Literal, Optional

# Third party (installed via pip)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from anthropic import Anthropic
from dotenv import load_dotenv

# Load env before creating clients
load_dotenv()

# Module-level constants (created once at startup)
ANTHROPIC_CLIENT = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MAX_LOG_LENGTH = 5000

app = FastAPI()
```

Module-level code runs once when Python imports the file. Function-level code runs every time the function is called. API clients, constants, and app initialization belong at module level. Request processing belongs in functions.

---

## The patterns you will see repeatedly in AOIS

```python
# 1. Load env, create client, define models — at module level
load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# 2. Pydantic input/output models
class LogInput(BaseModel):
    log: str

class IncidentAnalysis(BaseModel):
    severity: Literal["P1", "P2", "P3", "P4"]
    ...

# 3. Try primary, fall back to secondary
try:
    result = analyze_with_claude(log)
except Exception:
    result = analyze_with_openai(log)

# 4. FastAPI route: validate input, process, return typed output
@app.post("/analyze", response_model=IncidentAnalysis)
async def analyze(data: LogInput) -> IncidentAnalysis:
    return await analyze_with_claude(data.log)

# 5. Raise HTTP exceptions for client errors
if not data.log.strip():
    raise HTTPException(status_code=400, detail="Log cannot be empty")
```

These five patterns appear in every version from v1 through the end of Phase 2. Everything else is built on top of them.
