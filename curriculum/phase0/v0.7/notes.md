# v0.7 — How LLMs Work: Before You Call One
⏱ **Estimated time: 2–4 hours**

## What this version is about

v1 will call Claude and get back a structured incident analysis in one function call. Before that makes sense, you need to understand what is actually happening: what a language model is, what tokens are, what a context window means, and why the raw API returns text instead of structured data.

This version makes one raw Claude API call. No frameworks, no FastAPI, no Pydantic validation on the output. Just the SDK and the response. You will see what Claude actually returns and understand exactly why v1 wraps it with tooling.

---

## Prerequisites

- v0.1–v0.6 complete
- Anthropic API key in `.env`
- Anthropic SDK installed

Verify:
```bash
python3 -c "import anthropic; print(anthropic.__version__)"
```
Expected: a version number. If you get `ModuleNotFoundError`:
```bash
pip install anthropic python-dotenv
```

Verify your API key works:
```bash
cd /workspaces/aois-system
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()
key = os.getenv('ANTHROPIC_API_KEY')
print('Key present:', bool(key))
print('Key prefix:', key[:15] if key else 'None')
"
```
Expected:
```
Key present: True
Key prefix: sk-ant-api03-...
```
If `Key present: False`, your `.env` file is missing or the key name does not match exactly.

---

## Learning goals

By the end of this version you will:
- Understand what a language model is at a conceptual level
- Know what tokens are and why they are the unit of LLM cost
- Understand context windows and why they matter
- Know how system prompts, user messages, and assistant messages work
- Understand temperature and max_tokens
- Make a raw Claude API call and read the response object
- Understand why free-text responses need tooling to be production-safe
- Know the exact cost of a call and why prompt caching matters

---

## Part 1 — What a language model actually is

A language model predicts the next token given all previous tokens. That is the complete mechanism.

Given: `"The payment service is returning HTTP 503 errors. The most likely cause is"`
The model predicts the next token. Then the next. Then the next. It continues until it decides to stop.

Result: `" a database connection pool exhaustion, typically caused by too many concurrent requests"`

The model has seen billions of documents during training. It has learned which patterns of tokens tend to follow which other patterns. It does not "understand" in the human sense — but because it learned from so much human writing, engineering documentation, and technical content, its predictions are remarkably accurate for technical reasoning.

**Why prompting works:**

When you write:
```
System: You are an expert SRE. Classify this log by severity P1-P4.
User: OOMKilled pod/payment-service memory_limit=512Mi restarts=14
```

You are not "telling the model what to do" in a command sense. You are selecting which learned patterns activate. The model has seen thousands of SRE-written incident reports, severity classifications, and Kubernetes log analyses. Your system prompt steers the model toward those patterns.

This is why a well-written system prompt produces consistently useful outputs, and why a vague prompt produces vague outputs.

---

## Part 2 — Tokens: the unit of cost and context

A token is roughly 4 characters or 0.75 words. It is a subword unit determined by the model's tokenizer (a vocabulary of ~100,000 subword pieces).

```
"OOMKilled"           → ~3 tokens
"CrashLoopBackOff"    → ~4 tokens
"the"                 → 1 token
"authentication"      → ~3 tokens
"Hello, world!"       → 4 tokens
```

**Why tokens matter:**

1. **Cost** — you pay per token, not per request:
   - Claude input tokens: approximately $3 per million tokens
   - Claude output tokens: approximately $15 per million tokens
   - With prompt caching: cached input costs ~$0.30 per million tokens (90% reduction)

2. **Context window** — the maximum tokens the model can process at once

A typical AOIS call:
- System prompt: ~300 tokens
- User message (the log): ~100 tokens
- Response: ~200 tokens
- Total: ~600 tokens
- Cost per call: ~$0.004
- With caching on the system prompt: ~$0.002 per call

At 10,000 calls/day without caching: ~$40/day
At 10,000 calls/day with caching: ~$20/day

At 100,000 calls/day (real production scale): the difference is $400/day vs $200/day. Caching the system prompt is not optional at scale.

**Estimate tokens:**
```python
# Rule of thumb: len(text) / 4 ≈ token count
text = "OOMKilled pod/payment-service memory_limit=512Mi restarts=14 exit_code=137"
approx_tokens = len(text) / 4
print(f"Approximate tokens: {approx_tokens}")  # ~18
```

---

## Part 3 — Context window

The context window is the maximum number of tokens the model can process in one call — everything: system prompt, user messages, assistant messages, conversation history, and the response it generates.

**Claude's context window: 200,000 tokens** (~150,000 words — longer than most novels).

For AOIS log analysis:
- System prompt (~300 tokens) + log line (~100 tokens) + response (~200 tokens) = ~600 tokens
- We use 0.3% of the context window per call

Why the context window matters for later versions:
- **v20 (Agent Memory)**: as AOIS investigates an incident over multiple tool calls, the conversation history grows. At 200,000 tokens you have a very long leash, but you still need to manage it.
- **v23 (LangGraph)**: multi-step agent loops accumulate tokens across many exchanges. You need to track what is in context and what to keep.

**Paying for unused context:**
Every token in the context window costs money, whether the model "uses" it or not. If your system prompt is 2,000 tokens and you make 10,000 calls per day, you pay for 20 million prompt tokens daily — just for the fixed system prompt. Prompt caching makes those tokens cost 10x less after the first call.

---

## Part 4 — System prompt vs user message vs assistant message

```python
messages = [
    {
        "role": "system",
        "content": "You are AOIS — AI Operations Intelligence System..."
    },
    {
        "role": "user",
        "content": "Analyze this log: OOMKilled pod/payment-service"
    },
    # In multi-turn: you include past assistant responses to give context
    {
        "role": "assistant",
        "content": "This is a P2 incident indicating..."
    },
    {
        "role": "user",
        "content": "What should I check first?"
    }
]
```

**System prompt**: permanent instructions that apply to the entire conversation. Identity, rules, format, constraints. Sent on every call. This is what you cache.

**User message**: what you are asking this specific call. The log line.

**Assistant message**: what the model previously said. Only used in multi-turn conversations. For AOIS v1-v5, every call is a fresh single-turn exchange — no conversation history.

For AOIS, the system prompt defines: what AOIS is, severity level definitions (P1-P4), and (v5 onwards) the security instructions to resist prompt injection.

---

## Part 5 — Temperature and max_tokens

**Temperature** controls randomness in token selection.

At temperature 0: the model always picks the highest-probability next token. Same input → same output every time.

At temperature 1: the model samples from the probability distribution. Same input → different outputs each time.

```python
# For AOIS — always use low temperature
# Log analysis must be consistent: same OOMKilled log → same P2 every time
temperature=0.0

# For creative tasks (not AOIS)
temperature=0.7    # some variation is acceptable or even desirable
```

**max_tokens** limits how long the response can be. You pay for output tokens, so set this to what you actually need plus some headroom.

```python
max_tokens=1024    # plenty for a log analysis (responses are ~150-200 tokens)
max_tokens=4096    # for longer agent responses with detailed reasoning
```

If the model hits `max_tokens` before finishing its response, the response is cut off. The `stop_reason` field in the response will be `"max_tokens"` instead of `"end_turn"`.

---

> **▶ STOP — do this now**
>
> Calculate token costs before you make a single API call:
> ```
> System prompt: ~80 tokens
> User message (average log): ~50 tokens
> Response: ~150 tokens
> Total per call: ~280 tokens
>
> At claude-opus-4-6 pricing ($15/M input, $75/M output):
> Input cost per call:  280 × $15/1,000,000 = $0.0042
> Output cost per call: 150 × $75/1,000,000 = $0.01125
> Total per call: ~$0.016
>
> At 1,000 calls/day:  $16/day = $480/month
> At 10,000 calls/day: $160/day = $4,800/month
> ```
> This is why prompt caching (v1) and routing to cheaper models (v2) matter. Write these numbers down. When you implement caching and see the savings, you will know exactly why you built it.

---

## Part 6 — Raw curl call to Claude

Before writing Python, see the raw HTTP exchange:

```bash
cd /workspaces/aois-system
source .env  # if your .env uses export, otherwise load differently

# Or load inline:
export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2)

curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "max_tokens": 512,
    "system": "You are an expert SRE. Analyze infrastructure logs concisely.",
    "messages": [
      {
        "role": "user",
        "content": "Analyze this log: OOMKilled pod/payment-service memory_limit=512Mi restarts=14"
      }
    ]
  }' | python3 -m json.tool
```

Expected response (abbreviated):
```json
{
    "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
    "type": "message",
    "role": "assistant",
    "content": [
        {
            "type": "text",
            "text": "**Incident Analysis**\n\nThe payment service container has been OOMKilled (Out of Memory Killed) 14 times. The container is configured with a 512Mi memory limit but is consistently exceeding it.\n\n**Assessment:** P2 — High severity. The service is degraded and requires intervention within 1 hour.\n\n**Suggested actions:**\n1. Increase memory limit to at least 1Gi in the pod spec\n2. Check for memory leaks: kubectl top pod payment-service --containers\n3. Review recent deployments for memory-intensive changes"
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

Read every field:
- `id` — unique ID for this call (useful for debugging, Langfuse traces reference this)
- `type: "message"` — this is a message response (as opposed to other response types)
- `role: "assistant"` — confirms this is the model's response
- `content` — array of content blocks. For text responses, one block with `type: "text"`
- `text` — the actual response. Free text. Well-written, accurate, but unstructured.
- `model` — exact model version used (including date suffix)
- `stop_reason: "end_turn"` — model chose to stop (good). If this was `"max_tokens"`, response was cut off.
- `usage.input_tokens: 87` — how many tokens your input was
- `usage.output_tokens: 143` — how many tokens the response was

**The problem in plain sight:**
The response text is excellent. But you cannot do `response["severity"]`. You get a markdown-formatted paragraph. Extracting `severity` from this reliably requires either regex (fragile, like v0.6) or tool use (v1).

---

## Part 7 — The Python SDK call

Create the script:

```bash
cat > /workspaces/aois-system/practice/raw_claude.py << 'EOF'
from dotenv import load_dotenv
import os
import anthropic

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

LOG_TO_ANALYZE = "OOMKilled pod/payment-service memory_limit=512Mi restarts=14 exit_code=137"

print(f"Analyzing: {LOG_TO_ANALYZE}")
print("=" * 50)

response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=512,
    system="You are an expert SRE. Analyze infrastructure logs. Be concise.",
    messages=[
        {
            "role": "user",
            "content": f"Analyze this log:\n\n{LOG_TO_ANALYZE}"
        }
    ]
)

# Inspect the response object
print(f"ID:            {response.id}")
print(f"Model:         {response.model}")
print(f"Stop reason:   {response.stop_reason}")
print(f"Input tokens:  {response.usage.input_tokens}")
print(f"Output tokens: {response.usage.output_tokens}")
print()

# The text content
print("Response text:")
print("-" * 40)
for block in response.content:
    if block.type == "text":
        print(block.text)
print("-" * 40)
print()

# Calculate cost manually
INPUT_PRICE_PER_MILLION = 3.00     # $3.00 per million input tokens
OUTPUT_PRICE_PER_MILLION = 15.00   # $15.00 per million output tokens

input_cost = response.usage.input_tokens * (INPUT_PRICE_PER_MILLION / 1_000_000)
output_cost = response.usage.output_tokens * (OUTPUT_PRICE_PER_MILLION / 1_000_000)
total_cost = input_cost + output_cost

print(f"Cost breakdown:")
print(f"  Input:   ${input_cost:.6f} ({response.usage.input_tokens} tokens × $3/M)")
print(f"  Output:  ${output_cost:.6f} ({response.usage.output_tokens} tokens × $15/M)")
print(f"  Total:   ${total_cost:.6f}")
print()

# Now try to extract structured data from free text
# This is the problem that tool use (v1) solves
print("Attempting to extract severity from free text (this is fragile):")
text = response.content[0].text.lower()
if "p1" in text or "critical" in text:
    extracted_severity = "P1"
elif "p2" in text or "high severity" in text or "high priority" in text:
    extracted_severity = "P2"
elif "p3" in text or "medium" in text or "warning" in text:
    extracted_severity = "P3"
else:
    extracted_severity = "P4 (uncertain)"

print(f"  Extracted severity: {extracted_severity}")
print(f"  Problem: what if the model said 'Priority Two' instead of 'P2'?")
print(f"  Problem: what if it said 'this is a significant issue' instead of 'high severity'?")
print(f"  v1 solves this: tool use forces the model to output exactly the schema we define.")
EOF
```

Run it:
```bash
python3 /workspaces/aois-system/practice/raw_claude.py
```

Expected output:
```
Analyzing: OOMKilled pod/payment-service memory_limit=512Mi restarts=14 exit_code=137
==================================================
ID:            msg_01abc...
Model:         claude-opus-4-6-20250514
Stop reason:   end_turn
Input tokens:  78
Output tokens: 156

Response text:
----------------------------------------
**Incident Summary**

The payment service container has been OOMKilled 14 times...
[Several lines of good analysis]
----------------------------------------

Cost breakdown:
  Input:   $0.000234 (78 tokens × $3/M)
  Output:  $0.002340 (156 tokens × $15/M)
  Total:   $0.002574

Attempting to extract severity from free text (this is fragile):
  Extracted severity: P2
  Problem: what if the model said 'Priority Two' instead of 'P2'?
  Problem: what if it said 'this is a significant issue' instead of 'high severity'?
  v1 solves this: tool use forces the model to output exactly the schema we define.
```

---

## Part 8 — Asking Claude to return JSON

Attempt 2: ask the model to return JSON directly.

```bash
python3 << 'EOF'
from dotenv import load_dotenv
import os
import anthropic
import json

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=512,
    system="""You are an expert SRE. Analyze logs and respond with JSON ONLY.
Use exactly this format:
{"summary": "...", "severity": "P1|P2|P3|P4", "suggested_action": "...", "confidence": 0.0}""",
    messages=[
        {
            "role": "user",
            "content": "Analyze: OOMKilled pod/payment-service memory_limit=512Mi restarts=14"
        }
    ]
)

text = response.content[0].text
print("Raw response text:")
print(repr(text[:200]))  # show any hidden characters
print()

try:
    data = json.loads(text)
    print("JSON parsed successfully:")
    print(f"  severity: {data.get('severity', 'MISSING')}")
    print(f"  confidence: {data.get('confidence', 'MISSING')}")
except json.JSONDecodeError as e:
    print(f"JSON parse FAILED: {e}")
    print("The model probably added text before or after the JSON.")
    print("This is what Instructor (v3) fixes.")
EOF
```

Run it a few times. Sometimes it works. Sometimes the model adds a preamble like "Here is the JSON you requested:" before the JSON, breaking `json.loads`. Sometimes it adds a trailing note after the closing `}`.

**This is the fragility of asking for JSON without tool use.** The model is not constrained — it is only asked. Tool use (v1) removes the option to reply in plain text. The model must call the function. It has no choice.

---

## Part 9 — Try three different logs and observe

Run the raw script three times with different logs. Edit `raw_claude.py` and change `LOG_TO_ANALYZE` each time:

```python
# Log 1: Staging environment OOMKill
LOG_TO_ANALYZE = "TEST: OOMKilled pod/test-runner in staging environment for load testing, non-production"
```
```python
# Log 2: Context-dependent severity
LOG_TO_ANALYZE = "auth service latency p99 jumped from 50ms to 8000ms, all regions affected, 100% of users impacted"
```
```python
# Log 3: Ambiguous log
LOG_TO_ANALYZE = "pod/worker-3 restarted"
```

Observe how Claude handles:
1. The staging OOMKill — Claude will note it is non-production and likely classify it lower than P2
2. The latency spike — Claude will likely classify this as P1 (all users affected), even though nothing in the log says "OOMKilled" or "CrashLoop"
3. The ambiguous restart — Claude will ask for more context or classify as P4 with low confidence

The v0.6 regex script could not do any of these correctly. The regex would:
1. Classify the staging OOMKill as P2 (ignores "TEST" and "staging")
2. Classify the latency spike as P4 (no matching pattern)
3. Classify the ambiguous restart as P4 (no matching pattern)

Claude's intelligence is real. v1 packages it into a production API.

---

## Part 10 — Prompt caching: why it matters

Without caching: every call pays full price for the system prompt tokens.
With caching: after the first call, the system prompt is cached. Subsequent calls pay ~10% for the cached portion.

In v1 you will see:
```python
system=[
    {
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    }
]
```

The `cache_control: {"type": "ephemeral"}` tells Anthropic: "cache this on your side for up to 5 minutes." After the first call, every subsequent call that sends the same system prompt pays ~0.30 per million tokens instead of $3.00.

This is why `SYSTEM_PROMPT` is a module-level constant. If the prompt text were generated differently each call (e.g., with a timestamp), the cache would never hit.

---

## Troubleshooting

**"AuthenticationError: Invalid API key":**
```bash
# Check your .env
cat /workspaces/aois-system/.env
# Verify the key format: should start with sk-ant-api03-
# Check there are no spaces or quotes around the value
```

**"RateLimitError: 429":**
You have hit Anthropic's rate limit. Wait 60 seconds and try again. Check your usage on console.anthropic.com.

**"APIConnectionError":**
```bash
curl -I https://api.anthropic.com    # can you reach Anthropic at all?
echo $ANTHROPIC_API_KEY              # is the key in the environment?
```
If the curl fails: network issue in your Codespace. Try refreshing the Codespace.

**"stop_reason: max_tokens" in response:**
The response was cut off. Increase `max_tokens`. For AOIS analysis, 1024 is enough.

**Script runs but response text is empty:**
```python
print(response.content)          # see the raw content blocks
print(len(response.content))     # how many blocks?
```
If `content` is `[]`: the model returned nothing. This is very rare — usually a model error. Try again.

---

## What v1 adds to this foundation

| v0.7 (raw call) | v1 (production) |
|----------------|----------------|
| Free text response | Structured JSON via tool use |
| Manual cost calculation | `litellm.completion_cost()` automatic |
| Single provider | LiteLLM routes to 4 providers |
| No fallback | OpenAI fallback on Claude failure |
| No output validation | Pydantic validates every field (v3: Instructor) |
| Served from your terminal | FastAPI endpoint, HTTP API |
| You parse the response | SDK parses into typed Python objects |

The intelligence is the same. v1 wraps it so anything can call it reliably.

---

## Connection to later phases

- **Phase 1 (v1)**: Tool use adds the `ANALYZE_TOOL` schema. Claude is forced to return exactly that structure. The unstructured text response disappears.
- **Phase 1 (v3)**: Instructor wraps the SDK call. You never write a tool definition — the Pydantic model IS the schema.
- **Phase 7 (v20)**: When AOIS uses tools like `get_pod_logs`, the same token + context concepts apply. A 10,000-line log file would consume the entire context window — you must think about what to send to the model.
- **Phase 5 (v15)**: Fine-tuning changes the probability distributions the model learned. You are no longer steering a general-purpose model with prompts — you are using a model that was specifically trained on SRE incident data.
- **The cost model**: Everything in this project has a cost per call. From Phase 2 onwards, every decision (which tier, when to cache, how much context to include) has a dollar amount attached to it. Understanding tokens is understanding cost.

---

## Deep Dive: What the Model is NOT Doing

These misconceptions trip up engineers who then design systems incorrectly. Read them once, internalize them.

**The model does not "read" your prompt.** It does not parse it for meaning. It predicts the most likely continuation of the token sequence that includes your prompt. When you write a clear system prompt, you are not instructing the model — you are placing tokens that shift the probability distribution toward the responses you want. This is why rephrasing a prompt changes the output: different tokens, different probabilities, different predictions.

**The model does not "think" step by step.** Standard completion predicts one token at a time, no deliberation. When Claude appears to reason, it is because the training data contains extensive examples of step-by-step reasoning. The model produces reasoning-like text because reasoning-like text was in the distribution it learned. Extended thinking mode (used in v3 and v15) is a genuine exception — it does allow iterative reasoning before the final response.

**The model does not "remember" previous conversations** unless you explicitly include them in the context window. Every call starts fresh. This is why v20 (Mem0) matters — memory is an engineering problem you have to solve, not something the model provides.

**The model does not "understand" infrastructure.** When it correctly classifies an OOMKilled pod as P2, it is not applying SRE knowledge. It has seen enough SRE-written incident reports and Kubernetes documentation in its training data that it correctly predicts what text an expert would write. The predictions are often extremely accurate — but the mechanism is pattern completion, not understanding.

**Why this matters for AOIS design:**
- If the model does not have a concept in its training data, it will hallucinate one (v33 tests for this)
- If the context window fills up, earlier context becomes less influential (v20 must manage this)
- Temperature 0 gives you reproducibility, not guaranteed correctness — the deterministic prediction can still be wrong
- Prompt injection works because the model treats all text as tokens to complete, regardless of whether you intended it as instructions or data

---

## Mastery Checkpoint

The concepts in v0.7 are foundational to every decision you make from v1 to v34. These exercises prove they are internalized, not just read.

**1. Calculate cost before calling the API**
Before running any API call, estimate the cost:
- Write the system prompt you plan to use (approximately 300 tokens based on AOIS's prompt)
- Estimate the user message (the log you are sending, ~50 tokens)
- Estimate the response (~200 tokens)
- Calculate: input cost + output cost at standard rates
Then run the call and compare your estimate to `usage.input_tokens` and `usage.output_tokens`. Get within 20% on your estimate.

**2. Prove prompt caching works with real numbers**
Run the 3-call caching test from Part 10. Record the exact token numbers for all three calls:
- Call 1: `cache_creation_input_tokens` should be non-zero, `cache_read_input_tokens` should be 0
- Call 2+: `cache_creation_input_tokens` should be 0, `cache_read_input_tokens` should be non-zero
Calculate the cost difference between Call 1 and Call 2 (cached). The cached call should cost approximately 10% of the uncached call for the system prompt tokens.

**3. The temperature experiment**
Run `raw_claude.py` three times with `temperature=0.0`. Record the exact text each time. Then change to `temperature=0.9` and run three more times. Compare:
- At temperature 0: are the responses identical? (They should be very similar, potentially identical)
- At temperature 0.9: are the responses different? (They should vary)
For AOIS, why is temperature 0.0 the correct choice?

**4. The JSON fragility demonstration**
Run Part 8 (asking Claude to return JSON directly) 10 times. Count:
- How many times did it return clean JSON that `json.loads` parsed successfully?
- How many times did it add preamble or postamble text?
- What specific phrases triggered the failures?
This is empirical evidence for why tool use exists.

**5. Context window reasoning**
Given these numbers:
- Claude's context window: 200,000 tokens
- AOIS system prompt: ~300 tokens
- Average log line: ~50 tokens
- Average response: ~200 tokens
- A 10,000-line log file: approximately how many tokens?

Answer: a 10,000-line log file would be approximately 500,000 tokens — larger than Claude's entire context window. When AOIS investigates an incident in Phase 7 by reading pod logs with `get_pod_logs`, you cannot just dump the entire log file. You must select, summarize, or chunk. This constraint drives the design of the agent memory system in v20.

**6. The "why tool use" comparison in one session**
In a single Python session, do both:
1. Ask Claude for JSON directly (Part 8) — observe the raw text
2. Use tool use with `tool_choice: force` (as in v1) — observe the structured response

Write a one-paragraph explanation of what tool use actually does mechanically: it does not "teach" the model to return JSON. It changes the API contract — instead of generating text, the model must generate a function call in JSON format. The JSON is part of the protocol, not the content.

**The mastery bar**: You understand LLMs well enough to make intelligent engineering decisions. When someone proposes "just ask the model nicely for structured JSON", you know why that fails in production. When someone asks about cost optimization, you know the levers: caching, tier routing, max_tokens, model selection. When someone asks about context management, you understand the constraint. These mental models guide every decision from v1 to v34.
