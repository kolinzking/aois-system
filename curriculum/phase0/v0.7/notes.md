# v0.7 — How LLMs Work: Before You Call One

## What this version builds

A raw Claude API call — no FastAPI, no Pydantic models, no frameworks. Just the SDK, the HTTP request, and the response. You will see what the model actually returns, understand what tokens are, and understand why structured output needs tooling.

Then v1 arrives and wraps this raw power into a production API.

---

## What a language model actually is

A language model predicts the next token given all previous tokens. That is the entire mechanism. Everything else — reasoning, coding, log analysis, tool use — emerges from doing this at scale on massive amounts of text.

```
Input:  "The payment service is returning HTTP 503 errors. The likely cause is"
Output: " database connection pool exhaustion"

Input:  "Severity levels: P1=critical, P2=high. This log shows OOMKilled. Severity:"
Output: " P2"
```

The model has seen billions of documents. It has learned which tokens tend to follow which other tokens. When you write a good system prompt, you are setting context that steers which patterns the model activates.

This is why prompt engineering works: you are not "telling the model what to do" — you are selecting which learned patterns apply to this generation.

---

## Tokens — the unit of LLM cost and context

A token is roughly 4 characters or 0.75 words. It is not a word, not a character — it is a subword unit determined by the model's tokenizer.

```
"OOMKilled"          → 3 tokens: ["O", "OM", "Killed"]
"CrashLoopBackOff"  → 4 tokens: ["Crash", "Loop", "Back", "Off"]
"the"               → 1 token
"Hello, world!"     → 4 tokens: ["Hello", ",", " world", "!"]
```

**Why it matters:**
- You pay per token (input tokens + output tokens)
- The context window is measured in tokens
- `max_tokens` in your API call limits how long the response can be

Rough pricing for Claude (as of 2026):
- Input: ~$3 per million tokens
- Output: ~$15 per million tokens
- With prompt caching: cached input ~$0.30 per million tokens

A typical log analysis call:
- System prompt: ~300 tokens
- User message (the log): ~100 tokens
- Response: ~200 tokens
- Total: ~600 tokens ≈ $0.004 per call
- With caching on the system prompt: ~$0.002 per call

At 1,000 calls/day: ~$2/day cached vs ~$4/day uncached. At 100,000 calls/day: $200/day vs $400/day. Caching the system prompt is not optional in production.

---

## Context window

The context window is the maximum number of tokens the model can "see" at once — everything in the system prompt, user message, assistant response, conversation history.

Claude's context window: 200,000 tokens (~150,000 words — longer than most novels).

**What this means for AOIS:**
- Your system prompt + a single log line fits easily in any model's context window
- When you add agent memory (v20), conversation history grows — you need to manage what stays in context
- Long context ≠ free — you pay for every input token every call
- Prompt caching (v1) solves the system prompt cost specifically

---

## System prompt vs user message vs assistant message

```python
messages = [
    # The system prompt sets the model's role and rules — sent every call
    {"role": "system", "content": "You are an expert SRE..."},
    
    # The user message is what you are sending this call
    {"role": "user", "content": "Analyze this log: OOMKilled pod/payment-service"},
    
    # The assistant message is what the model returned — used in multi-turn conversations
    {"role": "assistant", "content": "This is a P2 incident..."},
    
    # You can continue the conversation
    {"role": "user", "content": "What should I check first?"}
]
```

For AOIS, every call is a fresh single-turn exchange: system prompt + user log. No conversation history needed. Later (v20, agent memory), you will build multi-turn exchanges where the agent remembers what it investigated.

---

## Temperature

Temperature controls randomness. Range: 0.0 to 1.0 (some models allow higher).

- `temperature=0.0` — deterministic: same input gives same output every time. Use for classification, analysis, structured output.
- `temperature=0.5` — some variation. Use for summaries where slight rephrasing is fine.
- `temperature=1.0` — high creativity. Use for writing, brainstorming.

For AOIS log analysis: always `temperature=0.0` or close to it. You want consistent, repeatable severity classification. A P1 should always be P1 on the same log, not sometimes P1 and sometimes P2 based on random sampling.

---

## Raw API call with curl

Before writing any Python, see the raw HTTP request:

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "max_tokens": 256,
    "system": "You are an expert SRE. Analyze infrastructure logs.",
    "messages": [
      {
        "role": "user",
        "content": "Analyze this log: OOMKilled pod/payment-service memory_limit=512Mi restarts=14"
      }
    ]
  }'
```

The response looks like:
```json
{
  "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "This log indicates a critical memory issue with the payment-service pod. The container has been OOMKilled (Out of Memory Killed) 14 times, suggesting it's repeatedly exceeding its 512Mi memory limit. This is a P2 incident...\n\nSuggested actions:\n1. Increase the memory limit..."
    }
  ],
  "model": "claude-opus-4-6-20250514",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 87,
    "output_tokens": 143
  }
}
```

Notice: the response is **free text**. It is readable, accurate, and helpful — but it is not structured. You cannot do `response["severity"]`. You get a paragraph. This is why v1 adds tool use.

---

## Raw Python SDK call

Create `/workspaces/aois-system/practice/raw_claude.py`:

```python
from dotenv import load_dotenv
import os
import anthropic

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# The simplest possible Claude call
response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=512,
    system="You are an expert SRE. Analyze infrastructure logs concisely.",
    messages=[
        {
            "role": "user",
            "content": "Analyze this log: OOMKilled pod/payment-service memory_limit=512Mi restarts=14"
        }
    ]
)

# What the response object looks like
print("=== Response object ===")
print(f"ID:          {response.id}")
print(f"Model:       {response.model}")
print(f"Stop reason: {response.stop_reason}")
print(f"Input tokens:  {response.usage.input_tokens}")
print(f"Output tokens: {response.usage.output_tokens}")
print()

# The actual text content
print("=== Content ===")
for block in response.content:
    if block.type == "text":
        print(block.text)
print()

# Cost estimate
input_cost = response.usage.input_tokens * (3.00 / 1_000_000)
output_cost = response.usage.output_tokens * (15.00 / 1_000_000)
print(f"=== Cost ===")
print(f"Input:  ${input_cost:.6f}")
print(f"Output: ${output_cost:.6f}")
print(f"Total:  ${input_cost + output_cost:.6f}")
```

Run it:
```bash
python3 /workspaces/aois-system/practice/raw_claude.py
```

Look at the output text. It is good analysis — probably better than the v0.6 regex version. But it is a paragraph. Try to extract severity from it programmatically:

```python
# Fragile parsing attempt
text = response.content[0].text
if "P1" in text:
    severity = "P1"
elif "P2" in text:
    severity = "P2"
# ...
```

This breaks immediately if the model says "critical" instead of "P1", or "Priority 2", or "second severity level". The output is semantically correct but syntactically unreliable.

This is exactly the problem tool use solves in v1.

---

## Ask Claude to return JSON

```python
response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=512,
    system="""You are an expert SRE. Analyze logs and respond with JSON only.
Format: {"summary": "...", "severity": "P1|P2|P3|P4", "suggested_action": "...", "confidence": 0.0-1.0}""",
    messages=[
        {
            "role": "user",
            "content": "Analyze: OOMKilled pod/payment-service memory_limit=512Mi restarts=14"
        }
    ]
)

import json
try:
    text = response.content[0].text
    data = json.loads(text)
    print(f"Severity: {data['severity']}")
    print(f"Confidence: {data['confidence']}")
except json.JSONDecodeError:
    print("Model did not return valid JSON")
    print(text)
```

This works most of the time. But "most of the time" is not acceptable in production. The model might:
- Add a preamble: "Here is the JSON you requested: {...}"
- Add a postamble: "{...}\n\nLet me know if you need more details"
- Use a slightly different key name: `"action"` instead of `"suggested_action"`
- Return `"confidence": "high"` instead of `"confidence": 0.9`

Tool use (v1) eliminates all of these failure modes. The model is not asked to generate JSON text — it is asked to call a function, and the parameters to that function must exactly match the schema you defined.

---

## The difference between Claude and GPT at a high level

| | Claude (Anthropic) | GPT-4o (OpenAI) |
|--|---|---|
| Context window | 200k tokens | 128k tokens |
| Reasoning | Extended thinking mode (v3) | o1/o3 reasoning models |
| Tool use format | `input_schema` | `parameters` |
| Prompt caching | Native, significant savings | Available |
| Vision | Yes (v31) | Yes |
| Best at | Long-context reasoning, coding, analysis | Broad ecosystem, fine-tuning |

For AOIS: Claude is primary because of context length (matters for agent memory in v20+), reasoning quality, and prompt caching economics. OpenAI is fallback in v1, and available as a routing tier throughout via LiteLLM.

---

## What v1 adds to this

| v0.7 (raw) | v1 (production) |
|-----------|----------------|
| Free text response | Structured JSON via tool use |
| Manual cost calculation | `litellm.completion_cost()` |
| No fallback | OpenAI fallback |
| No validation | Pydantic validates every field |
| Single function | FastAPI endpoint, served over HTTP |
| You parse the response | Anthropic SDK parses into typed objects |
| Prompt caching: manual | Prompt caching: built into system |

The intelligence is the same. v1 wraps it properly so it can be used by anything.

---

## Before moving to v1

Run this test with three different logs and observe:

```bash
python3 /workspaces/aois-system/practice/raw_claude.py
```

Change the log line in the file to:
1. `"auth service latency p99 is 12 seconds, up from 200ms baseline"`
2. `"node/worker-3 disk pressure: 94% used on /var/lib/docker"`
3. `"TEST environment: simulated OOMKill for load testing purposes"`

Notice how Claude handles context. The third one — a test environment OOMKill — Claude will likely classify as low severity or note that it is non-production. The v0.2 bash script and v0.6 regex API classified all OOMKills the same regardless of context.

That is intelligence. v1 packages it.
