# v2 — LiteLLM Gateway: One Interface, Any Model
⏱ **Estimated time: 3–4 hours**

## What this version builds

v1 had two separate code paths: one function for Anthropic, one for OpenAI. Different SDK calls, different response parsing, different error handling. To add a third provider (Groq, for example), you would write a third function.

v2 replaces both functions with a single routing layer. One function call works for any model. The model string (`"anthropic/claude-opus-4-6"` vs `"gpt-4o-mini"` vs `"groq/llama-3.1-8b-instant"`) is the only thing that changes between providers.

At the end of v2:
- **4 routing tiers** with real cost differences
- **Cost tracking** on every response (you see the dollar amount per call)
- **One codebase** — add a new model in one line, zero logic changes
- **Fallback logic** that degrades gracefully if a tier is unavailable

---

## Prerequisites

- v1 complete and tested
- The v1 `main.py` is working and all 6 test cases pass

Install LiteLLM if not already installed:
```bash
pip install litellm
python3 -c "import litellm; print(f'LiteLLM {litellm.__version__} installed')"
```

Add to `requirements.txt` if it is not there:
```bash
grep -q "litellm" requirements.txt || echo "litellm" >> requirements.txt
```

For the `fast` tier (Groq), you need a Groq API key. Get one free at console.groq.com:
```
GROQ_API_KEY=gsk_...
```
Add it to `.env`. If you do not have one, the fast tier will fail and fall back to standard — that is fine for now.

For the `local` tier (Ollama), you need Ollama running locally:
```bash
# Not required for v2 to work — local tier just fails gracefully without it
ollama --version    # check if installed
```

---

## Learning goals

By the end of this version you will understand:
- What LiteLLM is and why it exists (universal LLM gateway)
- How to define routing tiers with cost-performance tradeoffs
- Why cost tracking matters from the first version in production
- How a single API interface can route to completely different providers
- What graceful degradation looks like in practice

---

## What LiteLLM is

LiteLLM is a Python library that provides a single interface (`litellm.completion()`) for calling any LLM provider. The model string prefix determines the provider:

```
"anthropic/claude-opus-4-6"     → Anthropic API
"gpt-4o-mini"                    → OpenAI API (no prefix needed — it is the default)
"groq/llama-3.1-8b-instant"     → Groq API
"ollama/mistral"                 → Local Ollama instance
"bedrock/anthropic.claude-v3"   → Amazon Bedrock (Phase 4)
```

You write the tool definition once in OpenAI format. LiteLLM translates it to each provider's format under the hood.

LiteLLM also provides `litellm.completion_cost()` which calculates the exact dollar cost from any response's token counts.

---

## The code changes: v1 → v2

### What was removed

```python
# REMOVED: two separate SDKs
import anthropic
from openai import OpenAI

anthropic_client = anthropic.Anthropic(...)
openai_client = OpenAI(...)

# REMOVED: two separate functions
def analyze_with_claude(log: str) -> IncidentAnalysis: ...
def analyze_with_openai(log: str) -> IncidentAnalysis: ...
```

### What was added

```python
import litellm
import json

litellm.drop_params = True
```

`litellm.drop_params = True` tells LiteLLM to silently ignore parameters that a provider does not support. Different providers support different parameters. Without this, routing to Groq might crash if your request includes a parameter Groq does not accept.

---

## The routing tiers

```python
DEFAULT_TIER = "premium"

ROUTING_TIERS = {
    "premium":  "anthropic/claude-opus-4-6",    # $3 input / $15 output per million tokens
    "standard": "gpt-4o-mini",                   # $0.15 input / $0.60 output per million tokens
    "fast":     "groq/llama-3.1-8b-instant",    # near-zero cost, <1 second latency
    "local":    "ollama/mistral",               # free, runs on your machine
}
```

**Real cost difference for one AOIS call (~600 tokens):**

| Tier | Model | Approx cost/call | When to use |
|------|-------|-----------------|-------------|
| premium | claude-opus-4-6 | $0.004 | P1/P2 incidents needing deep reasoning |
| standard | gpt-4o-mini | $0.00005 | High-volume P3/P4 analysis |
| fast | groq/llama | ~$0.0001 | When latency matters more than quality |
| local | ollama/mistral | $0.00 | Development, testing, air-gapped |

At 10,000 calls/day:
- All premium: ~$40/day
- All standard: ~$0.50/day
- Smart routing (P1→premium, P3/P4→standard): ~$5-10/day

This is why routing exists. In Phase 7 (multi-agent), AOIS will automatically route based on severity: P1 incidents get Claude, bulk P4 log summarization goes to the cheap tier.

**Adding a new tier:** one line in `ROUTING_TIERS`. Zero other changes.

```python
ROUTING_TIERS["bedrock"] = "bedrock/anthropic.claude-v3-sonnet"    # Phase 4
ROUTING_TIERS["nim"] = "openai/meta/llama-3.1-8b-instruct"        # Phase 5
```

---

> **▶ STOP — do this now**
>
> Calculate the real cost difference between tiers using the AOIS call profile (~280 tokens total per call):
> ```
> Premium (claude-opus-4-6):   $3/M input + $15/M output
>   Per call: 130 tokens input × $3/M = $0.00039
>             150 tokens output × $15/M = $0.00225
>   Total per call: ~$0.0026
>
> Standard (gpt-4o-mini):      $0.15/M input + $0.60/M output
>   Per call: 130 × $0.15/M = $0.0000195
>             150 × $0.60/M = $0.00009
>   Total per call: ~$0.0001
>
> Fast (groq/llama-3.1-8b-instant): ~$0.05/M input + $0.08/M output
>   Total per call: ~$0.00002
> ```
> At 10,000 calls/day — all premium: ~$26/day.
> At 10,000 calls/day — 20% premium, 80% fast: ~$5.36/day.
>
> The routing tier logic saves ~80% on a real production workload. These numbers explain why v2 exists.

---

## The tool definition: now in OpenAI format

v1 used Anthropic's native format:
```python
# v1 — Anthropic format
{
    "name": "analyze_incident",
    "description": "...",
    "input_schema": { ... }    ← Anthropic-specific key
}
```

v2 uses OpenAI format (LiteLLM's common format):
```python
ANALYZE_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_incident",
        "description": "Analyze a log and return structured incident data",
        "parameters": {            ← OpenAI key (LiteLLM translates to Anthropic's input_schema)
            "type": "object",
            "properties": {
                "summary":          {"type": "string"},
                "severity":         {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                "suggested_action": {"type": "string"},
                "confidence":       {"type": "number"}
            },
            "required": ["summary", "severity", "suggested_action", "confidence"]
        }
    }
}
```

LiteLLM translates `parameters` to `input_schema` when routing to Anthropic, and passes `parameters` as-is to OpenAI. You define it once.

---

## The updated models

```python
class LogInput(BaseModel):
    log: str
    tier: str = DEFAULT_TIER    # callers can now choose which tier

class IncidentAnalysis(BaseModel):
    summary: str
    severity: str
    suggested_action: str
    confidence: float
    provider: str       # which model actually answered
    cost_usd: float     # what this call cost in dollars
```

`provider` and `cost_usd` are new. Every response now tells you which model answered and what it cost. Over time, this data lets you measure:
- Which tiers are being used most
- What the system is actually spending
- Whether the cheap tiers produce acceptable quality

---

## The single analyze function

```python
def analyze(log: str, tier: str = DEFAULT_TIER) -> IncidentAnalysis:
    model = ROUTING_TIERS.get(tier, ROUTING_TIERS[DEFAULT_TIER])

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this log:\n\n{log}"}
        ],
        tools=[ANALYZE_TOOL],
        tool_choice={"type": "function", "function": {"name": "analyze_incident"}},
        max_tokens=1024,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    data = json.loads(tool_call.function.arguments)
    cost = litellm.completion_cost(completion_response=response)

    return IncidentAnalysis(**data, provider=model, cost_usd=round(cost, 6))
```

Step by step:

**1. `model = ROUTING_TIERS.get(tier, ROUTING_TIERS[DEFAULT_TIER])`**
Look up the model string for the requested tier. If the tier name is unrecognized, use the default (premium). This prevents a crash on an invalid tier name.

**2. `litellm.completion(...)`**
One function call that works for any model. LiteLLM reads the model string prefix, finds the right provider, translates the request format, adds the correct API key from the environment, and makes the HTTP call.

**3. `response.choices[0].message.tool_calls[0]`**
LiteLLM normalizes all provider responses to the OpenAI response shape. Whether the model was Claude or GPT or Llama, the response structure is always `choices[0].message.tool_calls[0]`.

Compare to v1 where the response structure was different for Anthropic (`response.content` → loop for `tool_use` block) vs OpenAI (`choices[0].message.content` → json.loads).

**4. `json.loads(tool_call.function.arguments)`**
`tool_call.function.arguments` is a JSON string. `json.loads()` converts it to a Python dict.

**5. `litellm.completion_cost(completion_response=response)`**
Calculates the dollar cost from the token counts in the response. LiteLLM has a database of prices for every model it supports. Returns a float in USD.

**6. `IncidentAnalysis(**data, provider=model, cost_usd=round(cost, 6))`**
Unpacks the dict as keyword arguments, adds the two new fields, creates the Pydantic model.

---

> **▶ STOP — do this now**
>
> Look at the archived v2 code and compare the `analyze` function to v1's `analyze_with_claude`:
> ```bash
> grep -A 20 "def analyze_with_claude" /workspaces/aois-system/curriculum/phase1/v1/main.py
> grep -A 20 "def analyze" /workspaces/aois-system/curriculum/phase1/v2/main.py | head -25
> ```
> Count the lines in each. v1 has two functions totaling ~30 lines for two providers.
> v2 has one function of ~15 lines that handles any provider.
>
> Now see how adding Groq in v2 requires zero new code — just a new entry in `ROUTING_TIERS`:
> ```bash
> grep -A 6 "ROUTING_TIERS" /workspaces/aois-system/curriculum/phase1/v2/main.py | head -10
> ```
> This is the architectural argument for LiteLLM. Not magic — just one interface.

---

## The fallback logic

```python
@app.post("/analyze", response_model=IncidentAnalysis)
def analyze_endpoint(data: LogInput):
    tier = data.tier

    try:
        return analyze(data.log, tier)
    except Exception as e:
        if tier != "standard":
            try:
                return analyze(data.log, "standard")
            except Exception:
                pass
        raise HTTPException(
            status_code=503,
            detail={"error": str(e), "tier": tier}
        )
```

If the requested tier fails (missing API key, provider down, rate limit), try standard before giving up. This means:
- Groq is down → falls back to GPT-4o-mini automatically
- Local Ollama is not running → falls back to GPT-4o-mini automatically
- Claude is having issues → falls back to GPT-4o-mini

If standard also fails, return 503 with both error messages so you know what happened.

---

## Running and testing v2

Look at the archived v2 code:
```bash
cat /workspaces/aois-system/curriculum/phase1/v2/main.py
```

The current root `main.py` is v5 (security-hardened), which has all v2 concepts plus security layers. Test with the current version:

### Start the server
```bash
cd /workspaces/aois-system
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Test with explicit tier selection

Premium tier (Claude):
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service memory_limit=512Mi restarts=14", "tier": "premium"}' \
  | python3 -m json.tool
```
Expected: response includes `"provider"` and `"cost_usd"` fields.

Standard tier (GPT-4o-mini):
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service memory_limit=512Mi restarts=14", "tier": "standard"}' \
  | python3 -m json.tool
```
Expected: same analysis, different provider, much lower cost_usd.

Compare costs:
```bash
python3 << 'EOF'
import requests
import json

LOG = "OOMKilled pod/payment-service memory_limit=512Mi restarts=14 exit_code=137"
BASE = "http://localhost:8000"

for tier in ["premium", "standard"]:
    r = requests.post(f"{BASE}/analyze",
                      json={"log": LOG, "tier": tier},
                      headers={"Content-Type": "application/json"})
    if r.status_code == 200:
        data = r.json()
        print(f"Tier: {tier}")
        print(f"  Provider:  {data['provider']}")
        print(f"  Severity:  {data['severity']}")
        print(f"  Cost:      ${data['cost_usd']:.6f}")
        print()
    else:
        print(f"Tier {tier} failed: {r.status_code} {r.text}")
EOF
```

Expected output:
```
Tier: premium
  Provider:  anthropic/claude-opus-4-6
  Severity:  P2
  Cost:      $0.004200

Tier: standard
  Provider:  gpt-4o-mini
  Severity:  P2
  Cost:      $0.000083
```

The premium tier costs approximately 50x more than standard. Both return P2. For a P4 log summary, you would route to standard.

### Test fast tier (Groq)

If you have a Groq API key:
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service", "tier": "fast"}' \
  | python3 -m json.tool
```
Expected: response in under 1 second, very low cost.

### Test fallback behavior

If Groq is not configured, test fallback explicitly:
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service", "tier": "fast"}' \
  | python3 -m json.tool
```
When Groq API key is missing, LiteLLM raises an error, the fallback logic catches it, tries standard tier (GPT-4o-mini), and returns successfully. The response `provider` field tells you which model actually answered.

---

## Common Mistakes

**Model name format differences between providers.**
LiteLLM uses prefixed model names to identify the provider:
```python
"anthropic/claude-sonnet-4-6"    # Anthropic via LiteLLM
"gpt-4o-mini"                    # OpenAI — no prefix needed (default provider)
"groq/llama3-8b-8192"            # Groq
"ollama/llama3"                  # Ollama local
```
Passing `"claude-sonnet-4-6"` without the `anthropic/` prefix causes LiteLLM to default to OpenAI and fail with an authentication error against the wrong provider. Always check LiteLLM's documentation for the exact model name format for each provider.

**Fallback configured but never tested — silent single point of failure.**
You added OpenAI as a fallback. But have you confirmed it actually triggers? Set `ANTHROPIC_API_KEY="invalid"` temporarily and make a request. If the fallback works, the response will come from GPT-4o-mini. If it does not work, you discover it in production when Anthropic has an outage — not in testing.

**No budget limit on LiteLLM — a routing bug drains credits.**
If a routing condition has a bug that sends every request to Claude Opus instead of Haiku, your API bill will be 60x higher than expected. LiteLLM supports budget limits:
```python
litellm.max_budget = 10.0   # dollars — raises exception if exceeded
```
Set a daily budget limit during development. Learn to read the cost tracking output before removing the limit.

**`tier` parameter from user not validated.**
If `tier` is a free-form string from the request body, a user can send `tier: "premium_override"` and get routed to your most expensive model. Validate the tier value against a fixed set: `if tier not in ("premium", "standard", "fast", "local"): raise HTTPException(422)`. Never let user input directly control resource consumption without validation.

---

## Troubleshooting

**"LiteLLM API key not found for provider":**
```bash
# Check environment variable names LiteLLM expects
# Anthropic: ANTHROPIC_API_KEY
# OpenAI:    OPENAI_API_KEY
# Groq:      GROQ_API_KEY
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('GROQ_API_KEY', 'NOT SET'))"
```

**"json.decoder.JSONDecodeError" when parsing tool call:**
The model did not call the tool despite `tool_choice` forcing it. This is rare. Check:
```python
print(response.choices[0].message)    # see the raw message
print(response.choices[0].message.tool_calls)   # is it None?
```
If `tool_calls` is `None`, the model responded in text. Try again — usually transient.

**"litellm.exceptions.AuthenticationError":**
The API key for the requested tier is invalid. Check the key for that specific provider. Note that Groq and Anthropic use different key formats and different environment variable names.

**`cost_usd` is 0.0:**
`litellm.completion_cost()` returns 0 for models whose pricing it does not know. For standard models (Claude, GPT-4o-mini, Groq Llama), it should be non-zero. For custom or self-hosted models, you may need to set pricing manually.

**Provider order in fallback:**
The fallback only tries `standard`. If you want premium → standard → fast → local, you need to implement a retry loop across tiers.

---

## What v2 does not have (solved in v3)

| Gap | Impact | Fixed in |
|-----|--------|---------|
| No output validation guarantee | If LLM returns `"severity": "Critical"` instead of `"P1"`, `json.loads` succeeds but Pydantic accepts it because `severity` is still plain `str` | v3: Instructor validates the schema strictly |
| No automatic retry on bad output | One malformed response = one 503 (or silent bad data) | v3: Instructor retries with the error sent back to the model |
| No call history or dashboard | `cost_usd` per call, but no aggregation, no trend, no comparison | v3: Langfuse |
| Prompt caching lost | LiteLLM's default Anthropic routing does not pass `cache_control` through | Note: caching can be added back in v3 with LiteLLM's caching config |

---

## Connection to later phases

- **v3**: `litellm.completion()` is wrapped by Instructor. `json.loads(tool_call.function.arguments)` disappears — Instructor handles parsing and validation.
- **Phase 4 (v10)**: `ROUTING_TIERS["bedrock"] = "bedrock/anthropic.claude-v3-sonnet"` — one line and AOIS routes to Amazon Bedrock.
- **Phase 5 (v13-v14)**: `ROUTING_TIERS["nim"] = "..."` and `ROUTING_TIERS["vllm"] = "..."` — NIM and vLLM added as tiers. The routing logic never changes.
- **Phase 7 (v23)**: LangGraph agent nodes each call `analyze(log, tier)`. The tier is chosen based on severity: P1 incidents go to premium, batch P4 analysis goes to standard.
- **The principle**: LiteLLM is the abstraction layer that makes all of this possible. You write routing logic once. New providers are one line.

---

## Mastery Checkpoint

LiteLLM and multi-tier routing are production patterns used in every serious AI application. These exercises make them concrete.

**1. Cost comparison — the numbers that matter**
Run the tier comparison test with the same log across at least two tiers (premium and standard). Record the exact `cost_usd` returned. Now calculate: if this analysis runs 10,000 times per day, what is the monthly cost for each tier? What is the annual difference between routing everything to premium vs routing to standard? This arithmetic is what drives real architectural decisions.

**2. Understand LiteLLM normalization**
In v1, parsing Anthropic response was different from OpenAI response:
- Anthropic: `for block in response.content: if block.type == "tool_use":...`  
- OpenAI: `json.loads(response.choices[0].message.content)`

In v2 with LiteLLM: `response.choices[0].message.tool_calls[0].function.arguments` — same for both.

Write out the exact code path for one request through the premium tier (Claude) and trace every variable until you get to `IncidentAnalysis(**data, ...)`. Then trace the same path for standard tier (GPT-4o-mini). Where exactly are the paths identical? Where are they different? (Answer: the only difference is the `model` string passed to `litellm.completion()` — everything else is identical.)

**3. Add a new tier**
Add a fifth tier called `"batch"` that maps to `"groq/llama-3.1-70b-versatile"` (or any other available model). Add it to `ROUTING_TIERS`. Test it with a curl command. Verify `provider` and `cost_usd` in the response show the correct values. This exercise proves the routing layer is truly extensible.

**4. Understand the fallback logic exhaustively**
The fallback tries `standard` if the primary tier fails. But what if:
- The requested tier is already `standard` and it fails?
- The fallback itself fails?
- The tier name is unrecognized?
Trace through the code for each case. Write the expected behavior. Then verify by temporarily breaking the standard tier (change the model name to something invalid) and testing.

**5. Cost-aware routing decision**
Given this incident data:
- P1 alert: "payment service down, all users affected" → which tier?
- P4 summary: "disk at 45%, within normal range" → which tier?
- P3 warning: "cert expires in 14 days" → which tier?
- Batch analysis of 1000 P4 logs overnight → which tier?

Write the tier selection logic as a Python function: `def choose_tier(severity: str, is_batch: bool) -> str`. This function will appear in Phase 7 when the LangGraph agent routes different investigation steps to different tiers.

**6. The provider abstraction test**
Without changing any of the analysis logic (the `analyze()` function), make AOIS default to the `standard` tier instead of `premium` by changing one variable. Test that the behavior is identical. Then change it back. This is the power of the abstraction — provider changes at one point, behavior unchanged everywhere.

**The mastery bar**: You understand why routing layers exist, how LiteLLM normalizes provider responses, and can calculate cost implications of routing decisions. The LiteLLM pattern is what makes AOIS enterprise-flexible — the same application can route to Anthropic, OpenAI, Groq, Bedrock, or a local model with zero code changes outside the routing table.
