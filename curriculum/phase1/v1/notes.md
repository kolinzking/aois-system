# v1 — AOIS Core: Log → Intelligence
⏱ **Estimated time: 4–6 hours**

## What this version builds

One FastAPI endpoint that takes a raw infrastructure log and returns structured incident analysis. Claude is the primary model. OpenAI is the fallback. This is the first version where AOIS is actually intelligent — not pattern matching, not regex, but genuine reasoning about what a log means.

After Phase 0, you have:
- v0.6's FastAPI app showing how the API layer works
- v0.7's raw Claude call showing that the intelligence is real but output is unstructured

v1 connects them. The `analyze_with_regex()` function from v0.6 is replaced by `analyze_with_claude()`. The FastAPI app, the Pydantic models, the `/health` endpoint — all identical. One function changes. Everything changes.

---

## Prerequisites

- All Phase 0 complete — you can build and test APIs, you have made a raw Claude call
- API keys in `.env`:
  - `ANTHROPIC_API_KEY=sk-ant-...`
  - `OPENAI_API_KEY=sk-...`

Verify dependencies are installed:
```bash
cd /workspaces/aois-system
python3 -c "import fastapi, anthropic, openai, pydantic; print('All imports OK')"
```
Expected:
```
All imports OK
```

If any import fails:
```bash
pip install -r requirements.txt
```

Verify API keys:
```bash
python3 << 'EOF'
from dotenv import load_dotenv
import os
load_dotenv()
anthropic_key = os.getenv("ANTHROPIC_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")
print(f"Anthropic key: {'OK' if anthropic_key and anthropic_key.startswith('sk-ant') else 'MISSING'}")
print(f"OpenAI key:    {'OK' if openai_key and openai_key.startswith('sk-') else 'MISSING'}")
EOF
```
Expected:
```
Anthropic key: OK
OpenAI key:    OK
```

---

## Learning goals

By the end of this version you will understand:
- Why tool use forces structured output (vs asking for JSON in the prompt)
- What prompt caching is and how to activate it
- How to build a production fallback between two AI providers
- How FastAPI's `response_model` validates your AI output before it leaves the server
- The cost difference between Claude and OpenAI for this use case

---

## The full main.py: built section by section

Look at the current file:
```bash
cat /workspaces/aois-system/main.py
```

This is the v5 (security-hardened) version. The notes below explain the v1 foundations — the concepts apply to the current file too, but v5 adds rate limiting, sanitization, and output validation on top.

The archived v1 code:
```bash
cat /workspaces/aois-system/curriculum/phase1/v1/main.py
```

Walk through it section by section:

---

### Section 1 — Imports and setup

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

**`load_dotenv()`** reads `.env` and loads key=value pairs into the process environment. This must run before any `os.getenv()` calls. If `.env` does not exist (production environment where variables are injected by the runtime), `load_dotenv()` is a no-op — the code works in both environments.

**`anthropic.Anthropic(...)`** creates the Anthropic API client. The key comes from the environment, not the code. Creating the client at module level (not inside a function) means it is created once when Python loads the file, reused for every request. Creating a new client per request would be wasteful.

**Two clients:** v1 uses two separate SDKs (Anthropic and OpenAI) because they have different APIs and different response shapes. v2 replaces both with LiteLLM's unified interface.

---

### Section 2 — Pydantic models

```python
class LogInput(BaseModel):
    log: str

class IncidentAnalysis(BaseModel):
    summary: str
    severity: str
    suggested_action: str
    confidence: float
```

**`LogInput`**: the request body. When FastAPI receives a POST request, it reads the JSON body and validates it against `LogInput`. If `log` is missing or not a string: FastAPI returns 422 automatically. Your endpoint function never runs.

**`IncidentAnalysis`**: the response body. `severity` is `str` here (not `Literal`) — v3 tightens this.

**What Pydantic does for you:** you never write code like "if 'log' not in request.json: return error". Pydantic handles the entire validation layer from your type annotations.

---

> **▶ STOP — do this now**
>
> Open a Python REPL and test Pydantic validation directly:
> ```python
> from pydantic import BaseModel
> class IncidentAnalysis(BaseModel):
>     summary: str
>     severity: str
>     suggested_action: str
>     confidence: float
>
> # Try these — predict whether each succeeds or fails before running:
> print(IncidentAnalysis(summary="disk full", severity="P2", suggested_action="clear logs", confidence=0.9))
> print(IncidentAnalysis(summary="disk full", severity="P2", suggested_action="clear logs", confidence="high"))
> print(IncidentAnalysis(summary="disk full", severity="P2"))
> ```
> The third call fails with a `ValidationError` listing the missing field.
> FastAPI uses this same validation — an API request missing `suggested_action` gets a 422 back automatically. No code you wrote does that.

---

### Section 3 — The system prompt

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

**Why module-level:** created once at startup, never recreated. More importantly, Anthropic's prompt caching operates on this exact string — if it were recreated each call with varying content (a timestamp, for example), the cache would never hit.

**The severity definitions:** these are critical. Without them, "critical" to Claude might mean something different from what you mean. By defining P1-P4 explicitly with SRE-standard criteria, you get consistent classifications across all calls.

---

### Section 4 — The tool definition

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

**Why this exists — the core insight of v1:**

Without tool use, Claude returns text. From v0.7 you saw that text is well-written, but you cannot reliably extract fields from it. You cannot do `response["severity"]`.

Tool use is Anthropic's mechanism for forcing structured output. You define a function with a JSON schema. Claude is forced to "call" that function with parameters matching the schema exactly. The model cannot respond in plain text — it must fill in the schema.

**`"enum": ["P1", "P2", "P3", "P4"]`** in the schema: Claude cannot return "Critical" or "High". It must choose one of exactly those four values. The model is constrained by the schema at the API level.

**Anthropic format vs OpenAI format:**
- Anthropic uses `input_schema`
- OpenAI uses `parameters`
- LiteLLM (v2) normalizes to OpenAI format and translates to each provider

---

> **▶ STOP — do this now**
>
> Read the `ANALYZE_TOOL` definition and change the `severity` enum to `["CRITICAL", "HIGH", "MEDIUM", "LOW"]`. Do not restart the server yet. Predict: what will AOIS return when you send an OOMKill log?
>
> Now restart the server and send the OOMKill test:
> ```bash
> curl -s -X POST http://localhost:8000/analyze -H "Content-Type: application/json" \
>   -d '{"log": "OOMKilled pod/payment-service. Restarts: 14."}' | python3 -m json.tool
> ```
> The model is now constrained to return one of `["CRITICAL", "HIGH", "MEDIUM", "LOW"]` — it cannot say "P2" anymore. This proves the schema is not a suggestion to the model; it is a hard constraint enforced by the API protocol.
>
> Restore the enum to `["P1", "P2", "P3", "P4"]` before continuing.

---

### Section 5 — The Claude analysis function

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

**`system` as a list with `cache_control`:**

Normally `system` is a plain string. Here it is a list containing one object with `"cache_control": {"type": "ephemeral"}`. This activates Anthropic's prompt caching.

How caching works:
1. First call: Anthropic processes the system prompt (normal cost), stores it server-side for up to 5 minutes
2. Subsequent calls (same system prompt): Anthropic reads the stored version. Input cost for the system prompt drops by ~90%

At scale:
- 10,000 calls/day, 300-token system prompt
- Without caching: 3,000,000 tokens/day × $3/M = $9/day just for the system prompt
- With caching: first call $9 worth of tokens, subsequent $0.90 worth. Average across the day: ~$1/day

**`tool_choice: {"type": "tool", "name": "analyze_incident"}`:**

Forces Claude to always call exactly this tool. Without this, Claude might decide to answer in plain text on some calls. With this, it has no choice — it must call `analyze_incident` with the exact schema you defined.

**Parsing the response:**
```python
for block in response.content:
    if block.type == "tool_use":
        return IncidentAnalysis(**block.input)
```

Claude's response is a list of content blocks. There can be a `text` block (Claude's thinking/explanation) and a `tool_use` block (the structured output). You loop until you find `tool_use`.

`block.input` is already a Python dict: `{"summary": "...", "severity": "P2", "suggested_action": "...", "confidence": 0.93}`

`**block.input` unpacks that dict as keyword arguments to `IncidentAnalysis(...)`. Pydantic validates it.

---

> **▶ STOP — do this now**
>
> Run the cache verification script from the notes right now — before reading further:
> ```bash
> python3 << 'EOF'
> from dotenv import load_dotenv; import os, anthropic
> load_dotenv()
> client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
> SYSTEM = "You are AOIS — AI Operations Intelligence System, an expert SRE.\nAnalyze infrastructure logs and classify incidents.\n\nSeverity levels:\nP1 - Critical: production down\nP2 - High: degraded\nP3 - Medium: warning\nP4 - Low: preventive"
> for i in range(3):
>     r = client.messages.create(model="claude-opus-4-6", max_tokens=50,
>         system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
>         messages=[{"role": "user", "content": "test"}])
>     u = r.usage
>     print(f"Call {i+1}: create={getattr(u,'cache_creation_input_tokens',0)} read={getattr(u,'cache_read_input_tokens',0)}")
> EOF
> ```
> Call 1 should show `create=NNN read=0`. Calls 2 and 3 should show `create=0 read=NNN`. You just watched prompt caching activate in real time. The system prompt on calls 2 and 3 cost 10% of call 1.

---

### Section 6 — The OpenAI fallback

```python
def analyze_with_openai(log: str) -> IncidentAnalysis:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this log. Respond with JSON only: "
             f'{{"summary": "...", "severity": "P1|P2|P3|P4", "suggested_action": "...", "confidence": 0.0}}\n\n{log}'}
        ],
        response_format={"type": "json_object"}
    )
    data = json.loads(response.choices[0].message.content)
    return IncidentAnalysis(**data)
```

**Why this is different from the Claude function:**

OpenAI and Anthropic have fundamentally different APIs:
- OpenAI: `system` is inside the `messages` list. Response is at `choices[0].message.content` as a plain string.
- Anthropic: `system` is a top-level parameter. Response is `response.content` as a list of blocks.

**`response_format: {"type": "json_object"}`**: tells GPT to return valid JSON. But it does not enforce the schema. The model could return `{"error": "cannot analyze"}` and this code would crash trying to build an `IncidentAnalysis` from it.

This fragility is one of the things v3 (Instructor) fixes.

**`gpt-4o-mini` as fallback:** approximately 150x cheaper per token than `claude-opus-4-6`. As a fallback for when Claude is unavailable, it is more than adequate.

---

### Section 7 — FastAPI app and endpoint

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

**`/health`**: liveness endpoint. Kubernetes, load balancers, and monitoring tools call this. Returns 200 when the process is running. This pattern exists in every version from v1 to v34.

**`response_model=IncidentAnalysis`**: FastAPI validates the return value against this model before serializing to JSON. If `analyze_with_claude()` returns something that does not match (missing field, wrong type), FastAPI raises a 500 error at the server before the caller sees bad data.

**Fallback logic:**
1. Try Claude. Any exception — network error, rate limit, invalid API key, model error — triggers the fallback.
2. Try OpenAI. If that also fails, raise HTTP 503 with both error messages.

This pattern: try primary, catch any exception, try fallback — appears in every version through v5.

---

## Running the server

### Step 1: Start the server

```bash
cd /workspaces/aois-system
uvicorn main:app --host 0.0.0.0 --port 8000
```

Expected startup output:
```
INFO:     Started server process [12345]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

If you see any errors here, stop and fix them before continuing.

### Step 2: Health check

In a second terminal:
```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
Expected:
```json
{
    "status": "ok"
}
```
If this returns anything other than 200 with `{"status": "ok"}`, something is wrong with the server startup.

---

## Testing with real incident logs

### Test 1 — OOMKilled (P2)

```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "FATAL: pod/payment-service-7d9f8b OOMKilled. Container exceeded memory limit of 512Mi. Restarts: 14. Exit code: 137."}' \
  | python3 -m json.tool
```

Expected output:
```json
{
    "summary": "Payment service pod is repeatedly being OOM killed, exceeding its 512Mi memory limit after 14 restarts",
    "severity": "P2",
    "suggested_action": "Increase memory limit to at least 1Gi in the pod spec, or investigate and fix memory leak. Run: kubectl top pod payment-service-7d9f8b --containers",
    "confidence": 0.95
}
```

Verify:
- `severity` is exactly `"P2"` (not "high" or "Priority 2")
- `confidence` is a float between 0.0 and 1.0
- `suggested_action` is specific to the incident, not a generic response
- Response is valid JSON, no extra text

### Test 2 — CrashLoopBackOff (P1)

```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "Warning BackOff pod/auth-service-5c8d9f CrashLoopBackOff. Restarts: 8 in 10 minutes. Last log: panic: nil pointer dereference at runtime."}' \
  | python3 -m json.tool
```

Expected: `severity: "P1"` — crash loop with panic is critical.

### Test 3 — Cert expiry (P3)

```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "WARNING: TLS certificate for api.production.company.com expires in 3 days. cert-manager auto-renewal failed 3 times. Error: ACME DNS challenge failed — check DNS configuration."}' \
  | python3 -m json.tool
```

Expected: `severity: "P3"` — urgent but not yet down. 3 days is time to act.

### Test 4 — Disk pressure (P3)

```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "node/worker-3 condition: DiskPressure=True. Filesystem /var/lib/docker at 94% capacity. Kubelet evicting pods to reclaim space."}' \
  | python3 -m json.tool
```

Expected: `severity: "P3"` — at 94% with active eviction, this warrants attention soon.

### Test 5 — Context awareness (staging OOMKill)

```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "TEST: OOMKilled pod/load-test-runner in staging-environment. This is expected behavior during load testing. Non-production."}' \
  | python3 -m json.tool
```

Expected: lower severity than P2 (P3 or P4), because Claude recognizes "TEST", "staging", "expected behavior", "non-production". Compare this to v0.6's regex — it classified all OOMKills as P2 regardless.

### Test 6 — Novel incident type (latency spike)

```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "checkout service response latency p99 increased from 180ms to 12000ms. All 4 replicas affected. No recent deployments. Database connection pool at 98%."}' \
  | python3 -m json.tool
```

Expected: `severity: "P1"` or `"P2"` — Claude understands that 12 second latency affecting all users is a serious incident, even though no word like "OOMKilled" or "CrashLoop" appears. v0.6 regex would say P4.

---

## Testing the OpenAI fallback

Temporarily break the Anthropic key:
```bash
# Edit .env — change the key to something invalid
# ANTHROPIC_API_KEY=invalid_key_for_testing
```

Restart the server:
```bash
lsof -ti:8000 | xargs kill -9
uvicorn main:app --host 0.0.0.0 --port 8000
```

Send a request:
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service"}' \
  | python3 -m json.tool
```

Expected: you should still get a valid `IncidentAnalysis` response, but this time from GPT-4o-mini (OpenAI fallback). The analysis may be slightly different — this is normal.

In the server logs you will see the Anthropic authentication error, then the fallback succeeding.

Restore the real key and restart the server.

---

## Checking cost and cache hits

To see whether prompt caching is working, look at the response headers from Anthropic. The cache metadata appears in the API response:

```python
python3 << 'EOF'
from dotenv import load_dotenv
import os
import anthropic

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """
You are AOIS — AI Operations Intelligence System, an expert SRE.
Analyze infrastructure logs and classify incidents.

Severity levels:
P1 - Critical: production down, immediate action required
P2 - High: degraded, action within 1 hour
P3 - Medium: warning, action within 24 hours
P4 - Low: preventive, action within 1 week
"""

for i in range(3):
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "Analyze: OOMKilled pod/payment-service"}]
    )
    usage = response.usage
    print(f"Call {i+1}:")
    print(f"  Input tokens:              {usage.input_tokens}")
    print(f"  Cache creation tokens:     {getattr(usage, 'cache_creation_input_tokens', 0)}")
    print(f"  Cache read tokens:         {getattr(usage, 'cache_read_input_tokens', 0)}")
    print()
EOF
```

Expected output:
```
Call 1:
  Input tokens:              87
  Cache creation tokens:     312    ← system prompt cached here
  Cache read tokens:         0

Call 2:
  Input tokens:              87
  Cache creation tokens:     0
  Cache read tokens:         312    ← system prompt read from cache (90% cheaper)

Call 3:
  Input tokens:              87
  Cache creation tokens:     0
  Cache read tokens:         312    ← still reading from cache
```

---

## Common Mistakes

**Not using prompt caching — paying full price on every call.**
If your system prompt is the same on every call (it is for AOIS), you must add `cache_control: {"type": "ephemeral"}` to the system prompt content block. Without it, every call pays full input token price. With it, calls 2+ pay ~10% of that price. On 1000 calls/day with a 500-token system prompt, caching saves roughly $1.35/day — or $490/year at current Anthropic pricing. This is not optional in production.

**Using temperature for critical severity classification.**
```python
response = client.messages.create(..., temperature=0.7)
```
For AOIS severity classification (P1/P2/P3/P4), temperature=0.7 means different runs of the same log may produce different severity levels. Use temperature=0 for classification tasks. Use higher temperature only when you want creative variation (e.g., generating suggestions with multiple options).

**Treating the model's `suggested_action` as safe to execute automatically.**
The model can suggest "delete the namespace" or "run rm -rf /var/data" in a suggested_action field. Without output validation (added in v5), AOIS would return that suggestion directly. Never auto-execute LLM suggestions without a human approval step or output blocklist. The model is right most of the time — but "most of the time" is not production-safe.

**Not handling `anthropic.RateLimitError`.**
The Anthropic API has rate limits. Under load, calls will fail with 429. Without a retry strategy, AOIS returns a 500 error to the user. Add retry logic with exponential backoff, or use the fallback to OpenAI that v1 already includes. The fallback is the mitigation — make sure it is tested by temporarily using an invalid Anthropic key.

**Hardcoding model names as strings without a constant.**
```python
model="claude-sonnet-4-6"    # scattered across the codebase
```
Model names change when Anthropic releases new versions. Retired model names fail silently or return errors. Define model names as constants at the top of the file — one place to update when the model is upgraded.

---

## Troubleshooting

**Server starts but `curl /analyze` returns 500:**
Check the server terminal — the Python exception will be printed there.
```bash
# Check server logs while sending a request
# (run both in separate terminals)
uvicorn main:app --host 0.0.0.0 --port 8000 2>&1 | tee server.log
# In other terminal:
curl -s -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{"log": "test"}'
cat server.log | tail -20
```

**"AuthenticationError: Invalid API key":**
```bash
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print(repr(os.getenv('ANTHROPIC_API_KEY')[:20]))"
```
Check for whitespace, wrong variable name, or the key genuinely being wrong.

**Response missing fields (422 from FastAPI):**
The model returned JSON that does not match `IncidentAnalysis`. Check the raw response before FastAPI validation:
```python
# Add to analyze_with_claude() for debugging:
print(f"DEBUG raw response: {block.input}")
```

**"Both providers failed" 503:**
Both Claude and OpenAI are failing. Check both keys:
```bash
python3 -c "
from dotenv import load_dotenv; import os, anthropic, openai
load_dotenv()
try:
    anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY')).models.list()
    print('Anthropic: OK')
except Exception as e:
    print(f'Anthropic: {e}')
"
```

**`pydantic.ValidationError` in server logs:**
The model returned `"severity": "Critical"` instead of `"severity": "P2"`. In v1, this crashes. v3 (Instructor) handles this by retrying with the validation error sent back to the model.

---

## The gap list: what v1 does not have

These are not deficiencies — they are the next three versions.

| Gap | Impact | Fixed in |
|-----|--------|---------|
| Two separate code paths (Anthropic SDK + OpenAI SDK) | Adding a third provider requires a new function | v2: LiteLLM |
| No cost tracking per call | No visibility into what each request costs | v2: `cost_usd` field |
| `severity` is `str` — accepts any value | A bad model response silently passes through | v3: `Literal["P1","P2","P3","P4"]` |
| OpenAI fallback can return wrong fields | JSON parsing crashes if model returns unexpected structure | v3: Instructor validates + retries |
| No call tracing | Cannot see which model answered, token counts, latency | v3: Langfuse |
| Prompt caching works, but LiteLLM removes it in v2 | v2 loses caching until it is deliberately restored | v3 notes |

---

## Connection to later phases

- **v2**: `analyze_with_claude()` and `analyze_with_openai()` both disappear. Replaced by `analyze(log, tier)` — one function, LiteLLM routes to any model.
- **v3**: `ANALYZE_TOOL` disappears. Instructor generates the tool definition from the Pydantic model.
- **Phase 2 (v4)**: This entire `main.py` goes into a Docker container. No code changes — only the environment changes.
- **Phase 7 (v20)**: `analyze_with_claude()` gets expanded with tools — `get_pod_logs`, `describe_node`. AOIS stops reading logs and starts actively investigating.

---

## Mastery Checkpoint

v1 is the moment AOIS becomes real. These exercises prove you understand the core intelligence, not just how to run the server.

**1. The tool use schema controls the model**
Look at `ANALYZE_TOOL` in the archived v1 code. The `"enum": ["P1", "P2", "P3", "P4"]` on `severity` means the model cannot return anything outside those four values — it is constrained at the API protocol level, not just by the prompt.

Test this: temporarily add `"P5"` to the enum array and restart. Send the same OOMKill log. Does the model ever choose P5? (It should not — nothing in the model's training maps OOMKill to P5.) Now change the enum to just `["HIGH", "LOW"]`. Send the OOMKill log. What does it return? This proves the model adapts to the schema constraint.

**2. Prove the caching hit via token counts**
Run the cache verification script from the notes (three rapid calls with the same system prompt). For each call, record:
- `cache_creation_input_tokens`
- `cache_read_input_tokens`
- Total cost (calculate from token counts)

Call 1 should create the cache. Calls 2 and 3 should read from it. The system prompt tokens on calls 2-3 should cost ~10% of call 1. This is not theoretical — it is observable in the API response.

**3. The fallback test with real observation**
Break the Anthropic key as described in the notes. Send a request. Record:
- The error in the server logs (what exception was raised?)
- That the response still came back valid (from OpenAI)
- The different shape of the OpenAI response vs Anthropic (why v2 introduces LiteLLM to normalize this)

Restore the real key. Now you have observed the exact failure mode that motivated v2.

**4. Run all 6 test cases and record the intelligence**
Run every test case: OOMKilled, CrashLoopBackOff, cert expiry, disk pressure, staging OOMKill, latency spike. For each one, record:
- The severity returned
- The confidence score
- The `suggested_action` — is it specific to this incident or generic?
- Compare to what v0.6's regex would have returned

The staging OOMKill and the latency spike are the most revealing — they show contextual awareness that no regex can provide.

**5. Test the boundaries of tool_choice forcing**
What happens if you remove `tool_choice={"type": "tool", "name": "analyze_incident"}` from the API call? Send a request and observe the response.content list. Does it include a text block before the tool_use block? Does Claude ever choose to respond in plain text? How does this affect the `for block in response.content` loop?

This demonstrates why `tool_choice` forcing is essential for production reliability.

**6. Understand the architectural decision for v2**
v1 has two functions: `analyze_with_claude()` and `analyze_with_openai()`. They have different response parsing, different error types, and different system prompt formats.

Write out exactly what you would have to add to support a third provider (Groq) with its own SDK. Then compare to what v2 requires: one line in `ROUTING_TIERS = {"fast": "groq/llama-3.1-8b-instant"}`. 

The code you would have to write for v1-style Groq support is the argument for LiteLLM.

**7. Connect v1 to Phase 7**
In Phase 7 (v20), AOIS will have tools like `get_pod_logs(pod_name)` and `describe_node(node_name)`. These are defined exactly like `ANALYZE_TOOL` — a JSON schema with name, description, parameters.

Look at `ANALYZE_TOOL` and write a hypothetical `GET_POD_LOGS_TOOL` definition that would tell Claude how to call a function with a pod name and namespace. You do not need to implement it — just write the tool definition dict. The fact that you can write this from understanding (not memory) means you understand tool use at the conceptual level.

**The mastery bar**: v1 is the foundation of the entire intelligence layer. You should be able to explain to another engineer why tool use guarantees structured output, how prompt caching reduces costs, what the fallback mechanism does, and why this one function swap transforms the entire application. If you can explain all of this clearly, you are ready for v2.
