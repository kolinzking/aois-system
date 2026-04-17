# v1 — AOIS Core: Log → Intelligence

## What this version does
One FastAPI endpoint that takes a raw log string and returns structured incident analysis.
Claude is the primary model. OpenAI is the fallback. No routing, no cost tracking.

## What you will see when it runs
Send any log to POST /analyze and get back:
- summary — what happened
- severity — P1, P2, P3, or P4
- suggested_action — specific steps for the on-call engineer
- confidence — how sure the model is (0.0 to 1.0)

---

## Code Explained — Block by Block

### Imports and clients
```python
import anthropic
from openai import OpenAI

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
```
v1 talks directly to each provider using their own SDK.
Each provider has its own client, its own API format, its own response structure.
You have to know the differences and handle them separately.
This is the problem v2 solves.

---

### The System Prompt
```python
SYSTEM_PROMPT = """
You are AOIS — AI Operations Intelligence System, an expert SRE.
...
P1 - Critical: production down, immediate action required
...
"""
```
This is the standing instruction given to the LLM on every call.
It defines AOIS's identity and the severity classification system.

The important detail for Claude:
```python
system=[
    {
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    }
]
```
`cache_control: ephemeral` activates Anthropic's prompt caching.
After the first call, Anthropic stores this system prompt on their side.
Every subsequent call pays roughly 10% of the normal token cost for it.
On a high-volume system this cuts Claude costs dramatically.

---

### The Tool — Forcing Structured Output
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
This is Anthropic's native tool format (different from OpenAI's format — v2 unifies them).

Without this, Claude returns a paragraph of text.
With this, you are telling Claude: you have one tool called analyze_incident,
and you must call it with these exact fields.

`"enum": ["P1", "P2", "P3", "P4"]` means Claude cannot return "Critical" or "Sev-1".
It must pick from exactly those four values.

Then this line forces Claude to always use the tool, never skip it:
```python
tool_choice={"type": "tool", "name": "analyze_incident"}
```

---

### Parsing the Response
```python
for block in response.content:
    if block.type == "tool_use":
        return IncidentAnalysis(**block.input)
```
Claude's response is a list of content blocks.
We loop through them looking for the tool_use block.
`block.input` is already a dict that matches our Pydantic model.
`**block.input` unpacks it into keyword arguments.

---

### OpenAI Fallback
```python
def analyze_with_openai(log: str) -> IncidentAnalysis:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"}
    )
    data = json.loads(response.choices[0].message.content)
    return IncidentAnalysis(**data)
```
OpenAI does not use the same tool format as Anthropic.
Here we use `response_format: json_object` and instruct the model via the prompt
to return the fields we need. Less strict than tool use — the model could still
return wrong field names and this would crash. v3 (Instructor) fixes this.

---

### The Endpoint
```python
@app.post("/analyze", response_model=IncidentAnalysis)
def analyze(data: LogInput):
    try:
        return analyze_with_claude(data.log)
    except Exception as claude_error:
        try:
            return analyze_with_openai(data.log)
        except Exception as openai_error:
            raise HTTPException(status_code=503, detail={...})
```
Try Claude. If it fails for any reason, try OpenAI. If that fails, return 503.
Simple two-provider fallback, hardcoded. v2 makes this configurable.

---

## What v1 does NOT have (solved in later versions)
- No routing — always calls Claude regardless of log volume or cost
- No cost tracking — no idea what each call costs
- No provider visibility — response does not say which model answered
- Provider-specific code — adding a third provider means writing more if/else
- OpenAI fallback is fragile — JSON prompt engineering, not structured tool use
