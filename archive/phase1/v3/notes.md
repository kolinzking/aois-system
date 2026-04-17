# v3 — Instructor + Langfuse: Reliable Intelligence

## What this version does
Makes AOIS outputs guaranteed valid and every call observable.
Instructor replaces the manual tool definition and adds automatic retry.
Langfuse traces every call to a dashboard — model, tokens, cost, latency, input, output.

## What changed from v2
- Removed: ANALYZE_TOOL dict, manual json.loads(), manual tool_call parsing
- Added: instructor, langfuse, Literal type on severity, Field constraints on confidence
- The Pydantic model IS now the schema — no separate tool definition needed

---

## Code Explained — Block by Block

### Langfuse setup
```python
if os.getenv("LANGFUSE_SECRET_KEY"):
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
```
Two lines. That is the entire Langfuse integration.
LiteLLM has a callback system — when a call succeeds or fails, it notifies registered callbacks.
"langfuse" is a built-in LiteLLM callback that sends the full trace automatically.

What Langfuse receives on every call:
- model name and provider
- input messages (your prompt)
- output (the model's response)
- token counts (prompt tokens, completion tokens)
- cost in USD
- latency in milliseconds
- success or failure

To activate: create a free account at langfuse.com, add to .env:
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_HOST=https://cloud.langfuse.com

The dashboard populates itself from that point. No other code changes.

---

### IncidentAnalysis — the model IS the schema
```python
from typing import Literal

class IncidentAnalysis(BaseModel):
    summary: str = Field(description="Concise description of what happened and why it matters")
    severity: Literal["P1", "P2", "P3", "P4"] = Field(description="Incident severity level")
    suggested_action: str = Field(description="Specific remediation steps for the on-call engineer")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    provider: str = Field(default="")
    cost_usd: float = Field(default=0.0)
```

Three things changed from v2:

1. `Literal["P1", "P2", "P3", "P4"]` on severity
   In v2, severity was `str` — Pydantic would accept "Critical" or "Sev-1" without complaint.
   Literal means Pydantic will reject anything outside those four values.
   If the LLM returns "HIGH", that is a validation error and Instructor retries.

2. `ge=0.0, le=1.0` on confidence
   ge = greater than or equal. le = less than or equal.
   A confidence of 1.5 or -0.2 from a confused model is caught and retried.
   In v2 that would silently pass through.

3. `Field(description=...)` on each field
   Instructor reads these descriptions and includes them in the prompt it sends to the LLM.
   The model gets clearer instructions, which means fewer retries needed.

---

### Instructor wraps LiteLLM
```python
client = instructor.from_litellm(litellm.completion)
```
One line. Instructor wraps the LiteLLM completion function.
Everything that LiteLLM supports (all routing tiers, all providers) still works.
Instructor adds its validation and retry layer on top.

---

### The analyze function — what changed
```python
result, completion = client.chat.completions.create_with_completion(
    model=model,
    messages=[...],
    response_model=IncidentAnalysis,
    max_retries=2,
    max_tokens=1024,
)
```

v2 version:
```python
response = litellm.completion(...)
tool_call = response.choices[0].message.tool_calls[0]
data = json.loads(tool_call.function.arguments)
return IncidentAnalysis(**data, ...)
```

v3 version calls `create_with_completion` which returns two things:
- result — already a validated IncidentAnalysis instance, ready to return
- completion — the raw LiteLLM response, used only to calculate cost

`response_model=IncidentAnalysis` tells Instructor what shape to produce.
Instructor builds the tool definition from that model, sends the call,
parses the response, validates it against Pydantic.
If validation fails, it sends the error back to the LLM with the message
"you returned X but I expected Y, please try again" and retries up to max_retries times.

You never write a tool definition. You never parse JSON. You never handle validation manually.

---

### What did NOT change from v2
- ROUTING_TIERS — identical, same four tiers
- SYSTEM_PROMPT — identical
- LogInput model — identical
- The endpoint and fallback logic — identical
- requirements.txt — added instructor and langfuse

This is intentional. v3 is a targeted improvement to the reliability layer only.
The routing, the API shape, the fallback — none of that needed to change.

---

## What v3 does NOT have (solved in later versions)
- No eval suite — we have not measured AOIS accuracy against known incidents
- Prompt caching still not restored — will be revisited when we move off LiteLLM for Claude calls
- Langfuse is wired but requires manual account setup — not yet running locally
