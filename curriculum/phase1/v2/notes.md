# v2 — LiteLLM Gateway

## What this version does
Replaces the two separate provider SDKs (Anthropic + OpenAI) with a single routing layer.
One function call reaches any model. Routing is controlled by a tier name in the request.
Every response now tells you which model answered and what it cost.

## What changed from v1
- Removed: `anthropic` SDK, `openai` SDK, two separate analyze functions
- Added: `litellm`, `ROUTING_TIERS` dict, `tier` field on requests, `provider` and `cost_usd` on responses

---

## Code Explained — Block by Block

### LiteLLM replaces both SDKs
```python
import litellm

litellm.drop_params = True
```
LiteLLM is a universal gateway. One function — `litellm.completion()` — routes to any provider.
The provider is determined by a prefix in the model string: `anthropic/`, `groq/`, `ollama/`.

`drop_params = True` tells LiteLLM to silently ignore any parameter a provider does not support.
Groq does not support every parameter that Claude does. Without this, routing to Groq would crash.

---

### The Tool — Now in OpenAI Format
```python
ANALYZE_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_incident",
        "parameters": { ... }
    }
}
```
v1 used Anthropic's native tool format (`input_schema`).
v2 uses OpenAI's tool format (`parameters`).
LiteLLM translates this to whatever each provider actually expects.
You write it once, it works everywhere.

---

### Routing Tiers
```python
ROUTING_TIERS = {
    "premium": "anthropic/claude-opus-4-6",   # $0.012 per call — deep reasoning
    "standard": "gpt-4o-mini",                # $0.000083 per call — 150x cheaper
    "fast": "groq/llama-3.1-8b-instant",      # sub-second latency, near-zero cost
    "local": "ollama/mistral",                # runs on your machine, zero cost
}
```
This is the core of v2. One dict controls all routing.
To add a new model: add one line here. Zero logic changes anywhere else.

The cost difference is real:
- Processing 10,000 logs/day on premium = ~$120/day
- Processing 10,000 logs/day on standard = ~$0.83/day
- The routing tier you choose per log type determines your infrastructure cost

To activate a tier you just need its API key in .env.
If the key is missing, the fallback logic catches it.

---

### The Single Analyze Function
```python
def analyze(log: str, tier: str) -> IncidentAnalysis:
    model = ROUTING_TIERS.get(tier, ROUTING_TIERS[DEFAULT_TIER])

    response = litellm.completion(
        model=model,
        messages=[...],
        tools=[ANALYZE_TOOL],
        tool_choice={"type": "function", "function": {"name": "analyze_incident"}},
        max_tokens=1024,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    data = json.loads(tool_call.function.arguments)
    cost = litellm.completion_cost(completion_response=response)

    return IncidentAnalysis(**data, provider=model, cost_usd=round(cost, 6))
```
v1 had two functions (analyze_with_claude, analyze_with_openai) with different logic in each.
v2 has one function. The model string is the only thing that changes per tier.

Step by step:
1. Look up the model string from the tier name
2. Call litellm.completion() — same interface regardless of provider
3. response.choices[0].message.tool_calls[0] — LiteLLM normalises all responses to this shape
4. tool_call.function.arguments is a JSON string — parse it into a dict
5. litellm.completion_cost() calculates the dollar cost from the token counts in the response
6. **data unpacks the dict into IncidentAnalysis keyword arguments

---

### Updated Models
```python
class LogInput(BaseModel):
    log: str
    tier: str = DEFAULT_TIER     # caller can now choose the routing tier

class IncidentAnalysis(BaseModel):
    summary: str
    severity: str
    suggested_action: str
    confidence: float
    provider: str    # which model actually answered
    cost_usd: float  # what this call cost in dollars
```
`provider` and `cost_usd` make cost visible per response.
Over time this data becomes your cost analytics — you can see which tiers are being used
and what the system is actually spending.

---

### Fallback Logic
```python
def analyze_endpoint(data: LogInput):
    try:
        return analyze(data.log, tier)
    except Exception as e:
        if tier != "standard":
            try:
                return analyze(data.log, "standard")
            except Exception:
                pass
        raise HTTPException(status_code=503, detail=str(e))
```
If the requested tier fails (missing API key, provider down), try standard before giving up.
This means Groq being unavailable does not take down the service.

---

## What v2 does NOT have (solved in later versions)
- No output validation guarantee — if the LLM returns malformed JSON, it crashes
- No retry logic — one failure = one 503, no automatic recovery
- No tracing — cost_usd is per-call but there is no history, no dashboard, no trend data
- Prompt caching is gone — LiteLLM does not pass cache_control through to Anthropic by default
