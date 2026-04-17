# v0.5 — Python for This Project

## What this version is about

Not Python from the beginning. Python exactly as it is used in production AI engineering. You will set up a proper Python project environment, understand every pattern that repeats throughout AOIS, and build the Pydantic models that form the backbone of structured AI output.

After this version, no Python pattern in any later version will be unfamiliar.

---

## Prerequisites

- v0.1–v0.4 complete
- Python 3.11+ is installed (it is in Codespaces)

Verify:
```bash
python3 --version
```
Expected:
```
Python 3.11.x
```

```bash
pip3 --version
```
Expected:
```
pip 23.x from /usr/lib/python3/dist-packages/pip (python 3.11)
```

---

## Learning goals

By the end of this version you will understand:
- Why virtual environments exist and how to use them correctly
- How `.env` files work and why secrets never go in code
- How Pydantic validates data and why it matters for AI output
- What type hints are and how to read them
- How async/await works conceptually
- Python error handling patterns used throughout AOIS
- The five code patterns that appear in every version of this project

---

## Part 1 — Virtual environments

**The problem virtual environments solve:**

Python packages install globally by default. If project A needs `pydantic==1.10` and project B needs `pydantic==2.0`, they conflict — you cannot have both installed globally.

Virtual environments give each project its own isolated Python installation with its own packages.

```bash
# Create a virtual environment in your project
cd /workspaces/aois-system
python3 -m venv venv
```

What was created:
```bash
ls venv/
```
Expected:
```
bin/  include/  lib/  pyvenv.cfg
```
- `bin/` — has its own `python3` and `pip3` executables
- `lib/` — installed packages go here
- `pyvenv.cfg` — configuration file pointing to the system Python

Activate it:
```bash
source venv/bin/activate
```

Your prompt changes:
```
(venv) codespace@machine:/workspaces/aois-system$
```
The `(venv)` prefix confirms you are in the virtual environment.

Verify which Python you are using:
```bash
which python3
```
Expected:
```
/workspaces/aois-system/venv/bin/python3
```
This is the venv's Python, not the system Python. Any packages you install now go into `venv/lib/`, not the system.

```bash
# Install a package into the venv
pip install requests

# See installed packages
pip list

# Deactivate when done (returns to system Python)
deactivate
which python3   # back to system python
```

**In Codespaces for AOIS:** the dependencies are already installed in the project environment. You do not need to activate a venv to run things. But you should understand venvs because every project you work on or join uses them.

**The `venv/` directory is in `.gitignore`.** You commit `requirements.txt`, not `venv/`. Anyone who clones the repo runs `pip install -r requirements.txt` to recreate the environment.

---

## Part 2 — requirements.txt: the dependency contract

```bash
cat /workspaces/aois-system/requirements.txt
```
Expected:
```
fastapi
uvicorn
anthropic
openai
litellm
instructor
langfuse
python-dotenv
pydantic
httpx
slowapi
jaraco.context>=6.1.0
```

To install everything:
```bash
pip install -r requirements.txt
```

**Pinning versions:**

The current `requirements.txt` uses unpinned versions. In production, you pin exact versions:
```
fastapi==0.115.0
uvicorn==0.30.0
anthropic==0.40.0
```

Why: an unpinned install always grabs the latest version. A minor version bump in a dependency has broken production deployments. Pin versions for anything that runs in production. Use the unpinned list during development when you want latest features.

To generate a pinned requirements.txt:
```bash
pip freeze > requirements.txt
```
`pip freeze` outputs all installed packages with exact versions.

---

## Part 3 — .env files: secrets never in code

```bash
cat /workspaces/aois-system/.env
```
Expected:
```
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-...
```

How `python-dotenv` loads it:
```python
from dotenv import load_dotenv
import os

load_dotenv()   # reads .env, adds key=value pairs to process environment

api_key = os.getenv("ANTHROPIC_API_KEY")        # returns the value
db_url = os.getenv("DATABASE_URL", "sqlite:///./default.db")  # with default if not set
```

**`load_dotenv()` must be called before any `os.getenv()` calls.**

In production (Docker, Kubernetes), you do not use `.env` files. Environment variables are injected by the runtime:
- Docker: `--env-file .env` or `-e KEY=value`
- Kubernetes: `ConfigMap`, `Secret`, or External Secrets Operator
- AWS: SSM Parameter Store, Secrets Manager

`load_dotenv()` is a no-op if `.env` does not exist, so the same code runs correctly both locally (with `.env`) and in production (variables injected by runtime).

**Why secrets never go in code:**

If you hardcode an API key:
```python
api_key = "sk-ant-api03-hardcoded-key"    # NEVER do this
```

It ends up in git history. Even if you remove it in the next commit, `git log -p` shows it forever. Rotate the key immediately if this happens.

---

## Part 4 — Type hints

Type hints tell you and your tools what type a variable holds. Python does not enforce them at runtime (unless you use Pydantic or mypy), but they make code readable and catch bugs.

```python
# Without type hints — ambiguous
def analyze(log, tier):
    pass

# With type hints — clear
def analyze(log: str, tier: str) -> dict:
    pass
```

Common type annotations:
```python
from typing import Literal, Optional
from pydantic import BaseModel

# Basic types
name: str = "collins"
count: int = 0
score: float = 0.95
active: bool = True

# Collections
tags: list[str] = ["P1", "P2"]
data: dict[str, int] = {"errors": 5}

# Optional: value can be the type OR None
maybe_string: Optional[str] = None          # same as str | None
maybe_string: str | None = None             # Python 3.10+ syntax

# Literal: only specific values allowed
severity: Literal["P1", "P2", "P3", "P4"] = "P1"
# severity = "Critical" would be a type error
```

When you see `Literal["P1", "P2", "P3", "P4"]` in AOIS code, it means that field will only accept exactly those four values. Pydantic enforces this at runtime — pass "Critical" and you get a `ValidationError`.

---

## Part 5 — Pydantic: the backbone of structured AI output

Pydantic is a data validation library. You define a model class with typed fields. When you create an instance, Pydantic validates every field against its type annotation. If anything is wrong, it raises a `ValidationError` with a clear error message.

This is the core of why v1's structured output is reliable.

### Basic model

```python
from pydantic import BaseModel, Field
from typing import Literal

class IncidentAnalysis(BaseModel):
    summary: str
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float
```

Create an instance:
```python
analysis = IncidentAnalysis(
    summary="Payment service OOMKilled — exceeded 512Mi memory limit",
    severity="P2",
    suggested_action="Increase memory limit to 1Gi in pod spec",
    confidence=0.92
)

print(analysis.severity)         # P2
print(analysis.confidence)       # 0.92
print(type(analysis.confidence)) # <class 'float'>
```

Try invalid data:
```python
try:
    bad = IncidentAnalysis(
        summary="test",
        severity="Critical",     # NOT in Literal["P1","P2","P3","P4"]
        suggested_action="check it",
        confidence=1.5            # > 1.0 if ge/le constraints were set
    )
except Exception as e:
    print(e)
```
Expected output:
```
1 validation error for IncidentAnalysis
severity
  Input should be 'P1', 'P2', 'P3' or 'P4' [type=literal_error, ...]
```

### Field with constraints and descriptions

```python
from pydantic import BaseModel, Field

class IncidentAnalysis(BaseModel):
    summary: str = Field(
        description="Plain English explanation of what happened and why it matters to SRE"
    )
    severity: Literal["P1", "P2", "P3", "P4"] = Field(
        description="P1=critical/production down, P2=high/degraded, P3=medium/warning, P4=low"
    )
    suggested_action: str = Field(
        description="Specific action the on-call engineer should take right now"
    )
    confidence: float = Field(
        ge=0.0,   # greater than or equal to 0.0
        le=1.0,   # less than or equal to 1.0
        description="Model confidence 0.0–1.0"
    )
```

`ge` and `le` add numeric constraints. A confidence of 1.5 or -0.2 raises a `ValidationError`.

`description` does two things:
1. Documents the field for humans reading the code
2. In v3, Instructor reads these descriptions and includes them in the prompt sent to Claude, giving the model clear instructions for each field

### Serializing models

```python
analysis = IncidentAnalysis(
    summary="OOMKilled",
    severity="P2",
    suggested_action="Increase memory",
    confidence=0.9
)

# Convert to dict
data = analysis.model_dump()
print(data)
# {'summary': 'OOMKilled', 'severity': 'P2', 'suggested_action': 'Increase memory', 'confidence': 0.9}

# Convert to JSON string
json_str = analysis.model_dump_json()
print(json_str)
# {"summary":"OOMKilled","severity":"P2","suggested_action":"Increase memory","confidence":0.9}

# Create from dict (unpacking with **)
raw = {"summary": "OOMKilled", "severity": "P2", "suggested_action": "Increase memory", "confidence": 0.9}
analysis = IncidentAnalysis(**raw)
```

`**raw` unpacks the dict as keyword arguments. `IncidentAnalysis(**raw)` is equivalent to `IncidentAnalysis(summary="OOMKilled", severity="P2", ...)`. This pattern is used everywhere when building models from API responses.

### Try it right now

```python
# Run this in a Python terminal
python3 << 'EOF'
from pydantic import BaseModel, Field
from typing import Literal

class IncidentAnalysis(BaseModel):
    summary: str = Field(description="What happened")
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float = Field(ge=0.0, le=1.0)

# Valid
a = IncidentAnalysis(
    summary="OOMKilled payment service",
    severity="P2",
    suggested_action="Increase memory limit",
    confidence=0.92
)
print("Valid:", a.model_dump())

# Invalid severity
try:
    b = IncidentAnalysis(
        summary="test",
        severity="Critical",
        suggested_action="check it",
        confidence=0.5
    )
except Exception as e:
    print("Validation error:", str(e)[:100])

# Invalid confidence
try:
    c = IncidentAnalysis(
        summary="test",
        severity="P1",
        suggested_action="check it",
        confidence=1.5
    )
except Exception as e:
    print("Confidence error:", str(e)[:100])
EOF
```

Expected output:
```
Valid: {'summary': 'OOMKilled payment service', 'severity': 'P2', 'suggested_action': 'Increase memory limit', 'confidence': 0.92}
Validation error: 1 validation error for IncidentAnalysis
severity
  Input should be 'P1', 'P2', 'P3' or 'P4' ...
Confidence error: 1 validation error for IncidentAnalysis
confidence
  Input should be less than or equal to 1 ...
```

---

## Part 6 — Async/await

FastAPI is async. Understanding why matters even if the pattern feels mechanical at first.

**The problem:**

Your AOIS server receives 10 requests at the same time. Each request calls the Anthropic API, which takes 2 seconds to respond.

- **Synchronous**: the server handles one request at a time. Request 1 blocks for 2 seconds. Then request 2 blocks for 2 seconds. 10 requests take 20 seconds total.

- **Asynchronous**: the server starts request 1, sends the API call, then immediately starts request 2 while waiting for request 1's response. All 10 API calls are in flight simultaneously. 10 requests complete in ~2 seconds total.

**The pattern:**

```python
import asyncio
import httpx

# Synchronous: blocks — nothing else runs while waiting
def get_data_sync(url: str) -> dict:
    response = requests.get(url)    # blocks here for 200ms
    return response.json()

# Asynchronous: non-blocking — control returns to event loop while waiting
async def get_data_async(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)    # yields control while waiting
    return response.json()
```

`await` means "start this operation, and while waiting for it to complete, let other code run."

**In FastAPI:**

```python
@app.post("/analyze")
async def analyze(data: LogInput) -> IncidentAnalysis:
    result = await analyze_with_claude(data.log)    # non-blocking wait for Claude
    return result
```

The `async def` tells Python this function can be suspended. The `await` is where it suspends — while waiting for Claude's API response, FastAPI can handle other incoming requests.

**For Phase 1:** the Anthropic SDK has an `AsyncAnthropic` client. The pattern is `await client.messages.create(...)`. The code looks almost identical to synchronous — just add `async def` and `await`.

---

## Part 7 — Error handling

```python
# Basic try/except
try:
    result = analyze_with_claude(log)
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

# Catch specific exception types (preferred)
import anthropic

try:
    result = anthropic_client.messages.create(...)
except anthropic.AuthenticationError:
    # Wrong API key — do not retry, this is a configuration problem
    raise HTTPException(status_code=500, detail="Invalid API key")
except anthropic.RateLimitError:
    # Too many requests — retry with backoff or use fallback
    return analyze_with_openai(log)
except anthropic.APIConnectionError:
    # Network problem — might be transient
    return analyze_with_openai(log)
except anthropic.APIStatusError as e:
    # Server error from Anthropic's side
    print(f"Anthropic API error {e.status_code}: {e.message}")
    return analyze_with_openai(log)
except Exception as e:
    # Unexpected: log it and use fallback
    print(f"Unexpected error: {type(e).__name__}: {e}")
    return analyze_with_openai(log)
```

**Why catch specific exceptions:**
Catching `Exception` for everything hides bugs. A `KeyError` inside your code is a bug — it should not be silently swallowed and retried. `anthropic.RateLimitError` is an expected operational condition — it should trigger fallback logic. Catch specifically.

---

## Part 8 — The five patterns in every version of AOIS

Recognize these five patterns and nothing in the codebase will be foreign.

### Pattern 1: Load environment, create clients, define constants — at module level

```python
from dotenv import load_dotenv
import os
import anthropic

load_dotenv()                                        # run once at startup

client = anthropic.Anthropic(                        # created once
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

MAX_LOG_LENGTH = 5000                               # constant, never changes
SYSTEM_PROMPT = "You are AOIS..."                   # cached in memory
```

Module-level code runs once when Python imports the file. Clients are expensive to create — you create one and reuse it for every request. If the client were created inside the endpoint function, it would be created fresh for every single request.

### Pattern 2: Pydantic input and output models

```python
class LogInput(BaseModel):
    log: str
    tier: str = "premium"     # with default

class IncidentAnalysis(BaseModel):
    summary: str
    severity: Literal["P1", "P2", "P3", "P4"]
    suggested_action: str
    confidence: float = Field(ge=0.0, le=1.0)
```

These two classes define the API's contract. `LogInput` is what callers send. `IncidentAnalysis` is what AOIS returns. FastAPI validates both automatically.

### Pattern 3: Try primary provider, fall back to secondary

```python
try:
    result = analyze_with_claude(log)       # preferred
except Exception as claude_error:
    try:
        result = analyze_with_openai(log)   # fallback
    except Exception as openai_error:
        raise HTTPException(503, detail={
            "claude_error": str(claude_error),
            "openai_error": str(openai_error)
        })
```

### Pattern 4: FastAPI endpoint — validate input, process, return typed output

```python
@app.post("/analyze", response_model=IncidentAnalysis)
async def analyze_endpoint(data: LogInput) -> IncidentAnalysis:
    return await analyze(data.log, data.tier)
```

`response_model=IncidentAnalysis` makes FastAPI validate your return value matches the model before sending it. A bug in your analysis function that returns the wrong shape is caught here, not silently sent to the caller.

### Pattern 5: Raise HTTP exceptions for errors

```python
from fastapi import HTTPException

if not data.log.strip():
    raise HTTPException(
        status_code=400,
        detail="Log cannot be empty"
    )
```

`HTTPException` is FastAPI's way of returning an error response. The `detail` field is included in the response body as `{"detail": "Log cannot be empty"}`. The function stops executing immediately when this is raised.

---

## Build: write and run the core models

Run this to verify everything works in this environment:

```python
python3 << 'EOF'
from pydantic import BaseModel, Field
from typing import Literal
import json

class LogInput(BaseModel):
    log: str = Field(min_length=1, max_length=5000)
    tier: str = "premium"

class IncidentAnalysis(BaseModel):
    summary: str = Field(description="What happened and why it matters")
    severity: Literal["P1", "P2", "P3", "P4"] = Field(
        description="P1=critical/down, P2=high/degraded, P3=medium/warning, P4=low"
    )
    suggested_action: str = Field(
        description="What the on-call engineer should do right now"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence 0-1")

# Simulate what FastAPI does with an incoming request
raw_request = {"log": "OOMKilled pod/payment-service memory=512Mi restarts=14", "tier": "premium"}
input_model = LogInput(**raw_request)
print(f"Input valid: log={input_model.log[:30]}..., tier={input_model.tier}")

# Simulate what Claude returns (as a dict after JSON parsing)
claude_response = {
    "summary": "Payment service exceeded memory limit 14 times — likely a memory leak",
    "severity": "P2",
    "suggested_action": "Increase memory limit to 1Gi. Check for memory leaks with: kubectl top pod payment-service",
    "confidence": 0.93
}
output_model = IncidentAnalysis(**claude_response)
print(f"Output valid: severity={output_model.severity}, confidence={output_model.confidence}")
print(f"JSON: {output_model.model_dump_json(indent=2)}")

# Test validation catches bad data
print("\n--- Testing validation ---")
for bad in ["Critical", "Sev-1", "p1", "HIGH"]:
    try:
        IncidentAnalysis(summary="x", severity=bad, suggested_action="x", confidence=0.5)
        print(f"  '{bad}' PASSED (should have failed)")
    except Exception:
        print(f"  '{bad}' correctly REJECTED")
EOF
```

Expected output:
```
Input valid: log=OOMKilled pod/payment-service..., tier=premium
Output valid: severity=P2, confidence=0.93
JSON: {
  "summary": "Payment service exceeded memory limit 14 times — likely a memory leak",
  "severity": "P2",
  "suggested_action": "Increase memory limit to 1Gi...",
  "confidence": 0.93
}

--- Testing validation ---
  'Critical' correctly REJECTED
  'Sev-1' correctly REJECTED
  'p1' correctly REJECTED
  'HIGH' correctly REJECTED
```

---

## Troubleshooting

**"ModuleNotFoundError: No module named 'pydantic'":**
```bash
pip install pydantic
# Or if using venv, make sure venv is activated: source venv/bin/activate
```

**"ImportError: cannot import name 'Field' from 'pydantic'":**
You have Pydantic v1 installed. AOIS uses Pydantic v2.
```bash
pip install "pydantic>=2.0"
```

**Pydantic model not validating:**
```bash
python3 -c "import pydantic; print(pydantic.VERSION)"
```
If this shows `1.x`, you need to upgrade.

**"AttributeError: 'IncidentAnalysis' object has no attribute 'model_dump'":**
`model_dump()` is Pydantic v2. In v1 it was `.dict()`. Upgrade to v2 or change the call.

---

## Connection to later phases

- **Phase 1 (v1–v3)**: These exact models (`LogInput`, `IncidentAnalysis`) are used. The `Field(description=...)` values are what Instructor reads to guide Claude's output.
- **Phase 2 (v5)**: The `sanitize_log()` function uses the string patterns from v0.2 and returns to Pydantic validation.
- **Phase 7 (v20)**: Agent tool definitions use Pydantic models to define tool input schemas. Same pattern.
- **Phase 7 (v24)**: Pydantic AI framework is built entirely around this — it is Pydantic models all the way down.
- **The core insight**: Every version of AOIS from v1 to v34 has a Pydantic model at its input and output boundaries. Once you understand Pydantic, you understand the data layer of the entire project.
