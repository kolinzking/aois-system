# v1 — AOIS Core: Log → Intelligence

## What this version builds
One FastAPI endpoint that takes a raw infrastructure log and returns structured incident analysis.
Claude is the primary model. OpenAI is the fallback if Claude fails.
This is the foundation everything else builds on.

---

## Before you write any code

### What you need
- Python 3.11+
- An Anthropic API key (from console.anthropic.com)
- An OpenAI API key (from platform.openai.com)
- A `.env` file in your project root

### Create the .env file
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```
This file must never be committed to git. Verify it is in .gitignore:
```bash
cat .gitignore
```
You should see `.env` listed. If not, add it:
```bash
echo ".env" >> .gitignore
```

### Install dependencies
```bash
pip install fastapi uvicorn anthropic openai python-dotenv pydantic
```
Or save to requirements.txt first then install:
```bash
pip install -r requirements.txt
```

---

## The code — built section by section

### 1. Imports and setup

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import anthropic
import json
from openai import OpenAI

load_dotenv()

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
```

**`load_dotenv()`** reads your `.env` file and loads every key=value pair into the process environment. Without this line, `os.getenv("ANTHROPIC_API_KEY")` returns None and the API client has no key. This must be called before the clients are created.

**`anthropic.Anthropic(...)`** creates an Anthropic API client. The key comes from the environment, not hardcoded. Hardcoding a key in source code is a security vulnerability — the key ends up in git history and can be stolen.

**`OpenAI(...)`** same pattern, different provider. Two separate clients because v1 talks to each provider using their own SDK with their own response format.

---

### 2. The Pydantic models

```python
class LogInput(BaseModel):
    log: str

class IncidentAnalysis(BaseModel):
    summary: str
    severity: str
    suggested_action: str
    confidence: float
```

**What Pydantic does:** when FastAPI receives a request, it automatically validates the incoming JSON against `LogInput`. If the body is missing the `log` field, FastAPI returns a 422 error before your code runs. You do not write that validation yourself — Pydantic handles it from the type annotations.

**`LogInput`** is what the caller sends. One field: the raw log string.

**`IncidentAnalysis`** is what AOIS returns:
- `summary` — what happened and why it matters
- `severity` — P1, P2, P3, or P4
- `suggested_action` — what the on-call engineer should do right now
- `confidence` — how sure the model is, as a decimal (0.95 = 95% confident)

`severity` is typed as plain `str` here, which means Pydantic accepts any string. v3 tightens this to `Literal["P1", "P2", "P3", "P4"]` so anything outside those four values is rejected automatically.

---

### 3. The system prompt

```python
SYSTEM_PROMPT = """
You are AOIS — AI Operations Intelligence System, an expert SRE.
Analyze infrastructure logs and classify incidents.

Severity levels:
P1 - Critical: production down, immediate action required
P2 - High: degraded, action within 1 hour
P3 - Medium: warning, action within 24 hours
P4 - Low: preventive, action within 1 week
"""
```

**What a system prompt is:** the standing instruction given to the LLM before every conversation. It defines AOIS's identity and the rules it must follow. The severity definitions are here so the model uses exactly these criteria, not its own interpretation of "critical" or "high".

**Why it is a module-level constant and not inside the function:** if it were inside the function, Python would recreate the string on every call. At module level it is created once when the application starts. More importantly, Anthropic's prompt caching operates on this — see the next section.

---

### 4. The tool — forcing structured output

```python
ANALYZE_TOOL = {
    "name": "analyze_incident",
    "description": "Analyze a log and return structured incident data",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "suggested_action": {"type": "string"},
            "confidence": {"type": "number"}
        },
        "required": ["summary", "severity", "suggested_action", "confidence"]
    }
}
```

**Why this exists:** without it, Claude returns a paragraph of text. That paragraph is not reliably parseable. You cannot extract `severity` from "This appears to be a critical incident" in a way that works 100% of the time.

**Tool use** is Anthropic's mechanism for forcing structured output. You define a function with a name, description, and a JSON schema for its parameters. Claude must call this function with exactly those parameters — it cannot choose to answer in plain text instead.

**`"enum": ["P1", "P2", "P3", "P4"]`** on severity — Claude cannot return "Critical" or "Sev-1". It must choose from exactly those four values. The model knows this because it is in the schema it was given.

**`"required": [...]`** — all four fields must be present in every response.

**Note on format:** this is Anthropic's native tool format using `input_schema`. OpenAI uses `parameters` instead. They are different. v2 switches to OpenAI format because LiteLLM uses that as the common format and translates to each provider.

---

### 5. The Claude analyze function

```python
def analyze_with_claude(log: str) -> IncidentAnalysis:
    response = anthropic_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }
        ],
        tools=[ANALYZE_TOOL],
        tool_choice={"type": "tool", "name": "analyze_incident"},
        messages=[
            {"role": "user", "content": f"Analyze this log:\n\n{log}"}
        ]
    )
    for block in response.content:
        if block.type == "tool_use":
            return IncidentAnalysis(**block.input)
    raise ValueError("Claude did not return structured output")
```

**`system` as a list with `cache_control`:** normally `system` is just a string. Here it is a list containing one object with `cache_control: ephemeral`. This activates Anthropic's prompt caching.

**What prompt caching does:** on the first call, Anthropic processes and stores the system prompt on their side. Every subsequent call that uses the same system prompt pays approximately 10% of the normal input token cost for it. On a system processing thousands of logs per day, this alone cuts Claude costs significantly. The system prompt is your biggest fixed cost per call — caching it is one of the first optimisations in any production Claude application.

**`tool_choice: {"type": "tool", "name": "analyze_incident"}`** forces Claude to always call that specific tool. Without this, Claude might decide to answer in plain text sometimes. With this it has no choice.

**Parsing the response:**
```python
for block in response.content:
    if block.type == "tool_use":
        return IncidentAnalysis(**block.input)
```
Claude's response is a list of content blocks. There can be a `text` block (Claude's reasoning) and a `tool_use` block (the structured output). We loop until we find `tool_use`. `block.input` is already a Python dict matching our schema. `**block.input` unpacks it into keyword arguments for `IncidentAnalysis`.

---

### 6. The OpenAI fallback function

```python
def analyze_with_openai(log: str) -> IncidentAnalysis:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this log. Respond with JSON only: {{\"summary\": \"...\", \"severity\": \"P1|P2|P3|P4\", \"suggested_action\": \"...\", \"confidence\": 0.0}}\n\n{log}"}
        ],
        response_format={"type": "json_object"}
    )
    data = json.loads(response.choices[0].message.content)
    return IncidentAnalysis(**data)
```

**Why this is different from the Claude function:** OpenAI and Anthropic have different APIs with different response shapes. With OpenAI, `system` goes inside the `messages` list. The response is at `choices[0].message.content`, a plain string — not a list of blocks.

**`response_format: json_object`** tells GPT to always return valid JSON. But it does not enforce the schema. The model could return `{"error": "cannot analyze"}` and this code would crash trying to build an `IncidentAnalysis` from it. This fragility is exactly what Instructor in v3 fixes.

**`json.loads(...)`** parses the JSON string into a Python dict. `**data` unpacks it into `IncidentAnalysis`.

---

### 7. The FastAPI app and endpoint

```python
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze", response_model=IncidentAnalysis)
def analyze(data: LogInput):
    try:
        return analyze_with_claude(data.log)
    except Exception as claude_error:
        try:
            return analyze_with_openai(data.log)
        except Exception as openai_error:
            raise HTTPException(status_code=503, detail={
                "error": "Both providers failed",
                "claude": str(claude_error),
                "openai": str(openai_error)
            })
```

**`@app.get("/health")`** is a liveness endpoint. Kubernetes, load balancers, and monitoring tools call this to confirm the process is alive. Returns 200 with `{"status": "ok"}` when running.

**`response_model=IncidentAnalysis`** on the decorator tells FastAPI to validate and serialise the return value against `IncidentAnalysis`. If the function returns something that does not match, FastAPI raises an error before it leaves the server.

**Fallback logic:** try Claude. If it raises any exception — network error, API down, bad key, rate limit — try OpenAI. If that also fails, return HTTP 503 with both error messages so the caller knows what went wrong.

---

## Running the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

**`uvicorn`** is the ASGI server that runs FastAPI applications. `main:app` means the `app` object inside `main.py`. `--host 0.0.0.0` makes it reachable from outside localhost (required in Codespaces). `--port 8000` is the port.

Expected output:
```
INFO:     Started server process [...]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

To run in background so the terminal stays free:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 &
```

To kill it when you need to restart after a code change:
```bash
lsof -ti:8000 | xargs kill -9
```
`lsof -ti:8000` finds the process ID that owns port 8000. `xargs kill -9` force-kills it.

---

## Testing it

### Health check
```bash
curl -s http://localhost:8000/health
```
Expected:
```json
{"status": "ok"}
```

### Analyze a real incident log
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "FATAL: pod/payment-service-7d9f8b OOMKilled. Container exceeded memory limit of 512Mi. Restarts: 14. Exit code: 137."}' \
  | python3 -m json.tool
```

**`-s`** silent mode, hides curl progress bar.
**`-X POST`** HTTP POST request.
**`-H "Content-Type: application/json"`** tells the server the body is JSON.
**`-d '{...}'`** the request body.
**`| python3 -m json.tool`** pipes output through Python's JSON formatter so it is readable.

Expected output shape:
```json
{
    "summary": "...",
    "severity": "P1",
    "suggested_action": "...",
    "confidence": 0.95
}
```

### More test logs to try
```bash
# CrashLoopBackOff
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "Warning BackOff pod/auth-service CrashLoopBackOff. Restarts: 8 in 10 minutes. Last log: panic: nil pointer dereference"}' \
  | python3 -m json.tool

# Cert expiry
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "WARNING: TLS certificate for api.production.company.com expires in 3 days. cert-manager auto-renewal failed 3 times. Error: ACME DNS challenge failed."}' \
  | python3 -m json.tool
```

### Force the OpenAI fallback
Temporarily break the Anthropic key in `.env`:
```
ANTHROPIC_API_KEY=invalid_key
```
Restart the server, run the same request. You should get a valid response from GPT-4o-mini.
Restore the real key when done.

---

## Git — committing v1

Check what files exist and what changed:
```bash
git status
```

See the exact diff before committing:
```bash
git diff
```

Stage only the files that belong to v1:
```bash
git add main.py requirements.txt .gitignore
```

Do not use `git add .` blindly — it can accidentally stage `.env` or other files you do not want committed.

Commit with a clear message:
```bash
git commit -m "v1: FastAPI + Claude tool use + OpenAI fallback"
```

Verify the commit landed:
```bash
git log --oneline
```

**If you accidentally commit `.env`:**
The API keys are now in git history and must be rotated immediately. Generate new keys from console.anthropic.com and platform.openai.com, update `.env`, then remove the file from tracking:
```bash
git rm --cached .env
git commit -m "remove .env from tracking"
```

---

## What v1 does not have (fixed in later versions)

| Gap | Fixed in |
|-----|---------|
| Two separate code paths per provider | v2 — LiteLLM unifies them into one |
| No cost tracking | v2 — `cost_usd` on every response |
| Adding a third provider requires new code | v2 — one line in ROUTING_TIERS |
| OpenAI fallback can return wrong fields | v3 — Instructor validates and retries |
| No call history or tracing | v3 — Langfuse |
