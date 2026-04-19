# v13 — NVIDIA NIM: GPU Inference at Scale
⏱ **Estimated time: 3–5 hours**

*Phase 5 — NVIDIA & GPU Inference. See `curriculum/phase5/00-introduction.md` for the phase overview and the v13→v14→v15 build arc.*

## What this version builds

Every previous version calls an external API. Claude, OpenAI, Groq — someone else's GPU, billed per token. v13 changes the model: you bring your own inference.

NVIDIA NIM (Neural Inference Microservices) packages any model — Llama, Mistral, Mixtral, Stable Diffusion — into a container that runs on any GPU. The container exposes an OpenAI-compatible API. You point LiteLLM at it. From AOIS's perspective, NIM looks identical to any other provider.

Why NIM matters for AOIS:
- **Cost at volume**: 1 million P3/P4 log analyses/day at OpenAI prices costs ~$100/day. On your own NIM instance: infrastructure cost only, typically $0.10–0.30/hr. At ~5000+ calls/day, NIM pays for itself.
- **Data sovereignty**: logs contain hostnames, IPs, error messages — internal infrastructure data. Sending them to OpenAI or Anthropic may violate data residency requirements. NIM runs in your VPC.
- **Latency control**: no rate limits, no cold starts, no external API dependencies. The inference runs where you control it.

At the end of v13:
- **NGC hosted NIM connected** — call NVIDIA's cloud-hosted NIM via LiteLLM, zero setup
- **AOIS routes by severity** — P1/P2 go to Claude (best reasoning), P3/P4 go to NIM (volume tier)
- **Cost-aware routing logic built** — the `auto_route` flag, the `SEVERITY_TIER_MAP`
- **Benchmark run** — NIM vs Claude vs Groq vs GPT-4o-mini, real latency and cost numbers
- **Modal GPU deploy understood** — the path to running your own NIM on GPU hardware

---

## Prerequisites

- v12 complete: EKS torn down, Hetzner k3s still running, AOIS live
- v10/v11 infrastructure built (Bedrock quota pending — not a blocker for v13)
- NVIDIA NGC API key (Step 0 — free, takes 5 minutes)

Verify the existing stack is working:
```bash
curl -s https://aois.46.225.235.51.nip.io/health | python3 -m json.tool
```
Expected:
```json
{
    "status": "ok",
    "tiers": ["enterprise", "premium", "standard", "fast", "nim", "local"]
}
```
The `"nim"` tier appearing confirms the v13 code changes are deployed.

---

## Learning Goals

By the end of this version you will be able to:
- Explain what NVIDIA NIM is and how it differs from vLLM, Ollama, and cloud APIs
- Connect AOIS to NGC-hosted NIM via LiteLLM's `nvidia_nim/` prefix
- Explain cost-aware routing: which logs go to which model tier and why
- Implement severity-based auto-routing in a FastAPI endpoint
- Compare NIM latency and cost against Claude, Groq, and GPT-4o-mini on a real benchmark
- Describe the path to deploying self-hosted NIM on Modal GPU infrastructure
- Explain when NIM makes financial sense vs always-on cloud APIs

---

## The Inference Landscape

You now have six model tiers in AOIS. Understanding the full landscape:

```
Speed  ←————————————————————————————→  Quality/Reasoning
       
Ollama    NIM       Groq     Standard  Enterprise  Premium
(local)  (GPU)    (LPU)    (GPT-4o)  (Bedrock)  (Claude)
 free    $0.001   $0.0001   $0.001    $0.0005     $0.015
 /call    /call    /call     /call     /call       /call
```

**Where each fits in AOIS:**
- **Ollama**: local dev and testing only — too slow for production
- **NIM** (v13): volume tier — P3/P4 logs, thousands/hour, cost-controlled
- **Groq**: fastest external API — when latency < 1s matters more than cost
- **Standard** (GPT-4o-mini): reliable fallback with broad model support
- **Enterprise** (Bedrock): regulated/compliance environments
- **Premium** (Claude): P1/P2 incidents — reasoning quality, cost irrelevant

**The hardware behind each:**
| Provider | Hardware | What makes it fast |
|----------|----------|-------------------|
| Ollama | Your CPU/GPU | Nothing — runs on whatever you have |
| NIM on A10G | NVIDIA A10G | CUDA tensor cores, optimized TensorRT-LLM |
| Groq | Groq LPU | Language Processing Unit — custom silicon, deterministic memory |
| OpenAI/Anthropic | H100 clusters | Scale + custom serving infrastructure |

Understanding the hardware matters because latency and cost are physical, not arbitrary. Groq is fast because of custom chips. NIM is cost-effective because you own the GPU.

---

## Step 0: Get an NVIDIA NGC API Key

NVIDIA provides free access to NIM-hosted models through their API catalog. No GPU, no Docker, no infrastructure — just an API key.

**In a browser:**
1. Go to **build.nvidia.com**
2. Click **"Get API Key"** (top right)
3. Log in or create a free NVIDIA Developer account
4. Click **"Generate Key"** — copy the key immediately (it is shown once)
5. The key starts with `nvapi-`

**Add to .env:**
```bash
echo "NVIDIA_NIM_API_KEY=nvapi-YOUR-KEY-HERE" >> .env
```

Verify it is loaded:
```bash
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); key = os.getenv('NVIDIA_NIM_API_KEY', ''); print('NIM key loaded:', key[:12] + '...' if key else 'NOT FOUND')"
```
Expected: `NIM key loaded: nvapi-xxxxxxx...`

**What the free tier gives you:**
- 40 API calls/minute
- Access to 100+ NIM-packaged models (Llama 3.1 8B/70B/405B, Mistral, Mixtral, Phi-3, etc.)
- No credit card required
- The same models you would run on your own GPU — just hosted by NVIDIA

---

## Step 1: Connect LiteLLM to NGC NIM

LiteLLM has native support for NVIDIA NIM via the `nvidia_nim/` prefix. The base URL is `https://integrate.api.nvidia.com/v1`.

Test the connection directly:
```python
python3 << 'EOF'
import litellm, os
from dotenv import load_dotenv
load_dotenv()

litellm.drop_params = True

resp = litellm.completion(
    model="nvidia_nim/meta/llama-3.1-8b-instruct",
    messages=[{"role": "user", "content": "Reply with exactly: NIM connection successful"}],
    max_tokens=20,
)
print(resp.choices[0].message.content)
print(f"Model: {resp.model}")
print(f"Tokens: {resp.usage.total_tokens}")
EOF
```
Expected:
```
NIM connection successful
Model: meta/llama-3.1-8b-instruct
Tokens: 28
```

LiteLLM reads `NVIDIA_NIM_API_KEY` from the environment automatically. No additional configuration needed.

▶ **STOP — do this now**

Verify AOIS can call NIM directly by hitting the `nim` tier:
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "disk usage at 85% on /var/log partition, inodes at 70%", "tier": "nim"}' | python3 -m json.tool
```
Expected response:
```json
{
    "summary": "Disk space at 85% and inode usage at 70% on /var/log...",
    "severity": "P3",
    "suggested_action": "Clean up old log files...",
    "confidence": 0.85,
    "provider": "nvidia_nim/meta/llama-3.1-8b-instruct",
    "cost_usd": 0.000008
}
```

Notice `provider` shows the NIM model and `cost_usd` is near zero — this is the volume tier economics working.

---

## Step 2: The Routing Architecture

v13 adds two things to `main.py`:

**1. The NIM tier in `ROUTING_TIERS`:**
```python
ROUTING_TIERS = {
    ...
    "nim": "nvidia_nim/meta/llama-3.1-8b-instruct",  # NVIDIA NIM — NGC hosted, volume tier
    ...
}
```

**2. The severity-based auto-routing map:**
```python
SEVERITY_TIER_MAP = {
    "P1": "premium",    # production down — best model, cost irrelevant
    "P2": "premium",    # degraded — still Claude
    "P3": "nim",        # warning — NIM handles volume cheaply
    "P4": "nim",        # preventive — NIM handles volume cheaply
}
```

**3. The `auto_route` flag in `LogInput`:**
```python
class LogInput(BaseModel):
    log: str
    tier: str = DEFAULT_TIER
    auto_route: bool = False  # if True, re-route after first analysis based on severity
```

**How auto-routing works:**
```
Caller sends: {"log": "...", "tier": "standard", "auto_route": true}
  │
  ▼
AOIS analyzes with standard tier → gets result with severity: P3
  │
  ▼
auto_route=True + severity in SEVERITY_TIER_MAP → optimal_tier = "nim"
  │
  ▼
optimal_tier != current tier → re-analyze with NIM tier
  │
  ▼
Return NIM result (cheaper, same quality for P3)
```

The double-call is intentional — the first call (fast/cheap) classifies severity. The second call uses the optimal model for that severity. For P3/P4, the second call is NIM which is cheaper than standard. For P1/P2, the second call upgrades to Claude. Total cost is still lower than always using Claude.

**The endpoint change:**
```python
@app.post("/analyze", response_model=IncidentAnalysis)
@limiter.limit("10/minute")
def analyze_endpoint(request: Request, data: LogInput):
    tier = data.tier if data.tier in ROUTING_TIERS else DEFAULT_TIER
    try:
        result = analyze(data.log, tier)
        if data.auto_route and result.severity in SEVERITY_TIER_MAP:
            optimal_tier = SEVERITY_TIER_MAP[result.severity]
            if optimal_tier != tier:
                result = analyze(data.log, optimal_tier)
        return result
    except Exception as e:
        ...
```

▶ **STOP — do this now**

Test auto-routing with a P3 log and a P1 log:
```bash
# P3 log — should auto-route to NIM
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "disk at 80%, warning threshold", "tier": "standard", "auto_route": true}' \
  | python3 -m json.tool

# P1 log — should auto-route to Claude premium
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "production database connection pool exhausted, all writes failing", "tier": "standard", "auto_route": true}' \
  | python3 -m json.tool
```

For the P3 log, check `provider` — it should be `nvidia_nim/meta/llama-3.1-8b-instruct`.
For the P1 log, check `provider` — it should be `anthropic/claude-opus-4-6`.

This is cost-aware routing working automatically: the caller does not need to know which model is appropriate. AOIS decides based on what it finds.

---

## Step 3: Run the Benchmark

`test_nim.py` benchmarks all four tiers on the same log:

```bash
python3 test_nim.py
```

Expected output (actual numbers vary):
```
NVIDIA NIM vs Claude vs Groq — Latency & Cost Benchmark
================================================================================
Model routing philosophy:
  P1/P2 (critical/high) → Claude premium — best reasoning, cost irrelevant
  P3/P4 (warning/low)   → NIM llama-8b  — volume tier, ~10x cheaper

Benchmarking nim_llama_8b...
  nim_llama_8b              | mean: 1.82s | stddev: 0.21s | ~$0.000008/call | The auth-service pod...
Benchmarking groq_llama_8b...
  groq_llama_8b             | mean: 0.43s | stddev: 0.08s | ~$0.000001/call | The auth-service pod...
Benchmarking gpt4o_mini...
  gpt4o_mini                | mean: 1.21s | stddev: 0.15s | ~$0.000110/call | The auth-service pod...
Benchmarking claude_premium...
  claude_premium            | mean: 3.43s | stddev: 0.41s | ~$0.015000/call | The auth-service pod...
```

**What to read from this data:**
- NIM at ~$0.000008/call vs Claude at ~$0.015/call = **1875x cheaper** for P3/P4 volume
- NIM latency (~1.8s) is acceptable for P3/P4 — these are warning-level, not emergencies
- Groq is fastest and cheapest but uses Llama (same family as NIM) — if Groq is available, it may be preferred over NGC NIM for latency-sensitive cases
- Claude's cost is justified for P1/P2 — you would pay $100 to prevent a $1M outage

▶ **STOP — do this now**

Run the benchmark and record your actual numbers. Then answer:
1. At 10,000 P3/P4 log analyses per day, what is the monthly cost difference between always-on Claude premium and NIM?
2. At what call volume does NIM on a dedicated Modal GPU (~$0.59/hr A10G) become cheaper than NGC hosted NIM?

For question 2: NGC charges per token (similar to OpenAI pricing). A dedicated GPU has a flat hourly cost. At some request volume, flat cost wins.

---

## Step 4: The Modal Path (Self-Hosted NIM on GPU)

NVIDIA NGC API is convenient but you are still paying per token. The production pattern for high-volume inference is a dedicated GPU running NIM.

**Modal** is serverless GPU compute — you pay per second of GPU use, no minimum. An A10G costs ~$1.10/hr, billed in seconds. For bursty workloads, this is the cheapest path to running your own NIM.

The deployment pattern (no execution required — infrastructure cost is real):
```python
# modal_nim.py — deploy NIM on Modal GPU (run when needed)
import modal

app = modal.App("aois-nim")
nim_image = modal.Image.from_registry(
    "nvcr.io/nim/meta/llama-3.1-8b-instruct:latest",
    add_python="3.11",
).env({"NGC_API_KEY": modal.Secret.from_name("ngc-api-key")})

@app.cls(
    gpu="A10G",
    image=nim_image,
    container_idle_timeout=300,   # 5 min idle → GPU released → $0 cost
)
class NIMService:
    @modal.enter()
    def load_model(self):
        import subprocess
        subprocess.Popen(["nim_llm"])   # NIM server starts on container boot
    
    @modal.web_endpoint(method="POST")
    def generate(self, request: dict):
        import requests
        return requests.post("http://localhost:8000/v1/chat/completions", json=request).json()
```

**Why `container_idle_timeout=300` matters:** When no requests come in for 5 minutes, Modal terminates the container and you stop paying. Cold start takes ~60s (model loading). This is the scale-to-zero pattern — but for GPU inference, not pods. For AOIS, this means: overnight when P3/P4 volume is low, the GPU shuts down. Morning traffic cold-starts it. Steady-state during business hours: GPU stays warm.

**LiteLLM connection to Modal NIM:**
```python
# Once Modal deploys the NIM endpoint, update ROUTING_TIERS:
ROUTING_TIERS = {
    ...
    "nim": "openai/meta/llama-3.1-8b-instruct",  # same OpenAI-compat API
    ...
}
# Set in .env:
# OPENAI_API_BASE=https://your-modal-endpoint.modal.run
# OPENAI_API_KEY=dummy  # NIM doesn't need a real key
```

NIM exposes an OpenAI-compatible API. LiteLLM routes to it identically to any other OpenAI endpoint. The model string changes; the AOIS code does not.

**When to use NGC API vs Modal NIM vs Dedicated GPU:**

| Scenario | Best option |
|----------|------------|
| Learning / prototyping | NGC API (free tier, zero setup) |
| Bursty production (<1M calls/day) | Modal GPU (pay per second, auto scale-to-zero) |
| Steady production (>1M calls/day) | Dedicated GPU (Hetzner GPU server, ~€2/hr A30) |
| Air-gapped / data residency | Dedicated GPU on-prem or in your VPC |

For AOIS in this curriculum: NGC API is correct for v13. The Modal pattern appears in v14 (vLLM). A dedicated GPU appears in v15 (fine-tuning). By v15 you will have used all three paths.

---

## Step 3b: Reading the benchmark numbers correctly

The benchmark reports mean latency, stddev, and cost per call. Here is what to look for beyond the headline numbers:

**Coefficient of variation (stddev / mean):**
A model with mean=1.8s and stddev=0.8s is less predictable than mean=2.5s stddev=0.1s. For P3/P4 logs where AOIS is running a background batch, unpredictability is acceptable. For P1/P2 where an on-call engineer is waiting, it is not. This is why P1/P2 stay on Claude — not just quality, but consistent latency.

**The cost math at production scale:**
```python
# Run this to see the routing decision at different volumes
python3 << 'EOF'
nim_cost_per_call = 0.000008      # actual from your benchmark
claude_cost_per_call = 0.015      # actual from your benchmark
gpt4o_mini_cost = 0.000110        # actual from your benchmark

print(f"{'Volume':>12} | {'All Claude':>12} | {'All GPT-mini':>12} | {'NIM (P3/P4)':>12} | {'Savings':>10}")
print("-" * 68)
for calls_per_day in [100, 1_000, 10_000, 100_000]:
    all_claude = calls_per_day * 30 * claude_cost_per_call
    all_mini = calls_per_day * 30 * gpt4o_mini_cost
    # Assume 70% P3/P4, 30% P1/P2
    nim_mixed = calls_per_day * 30 * (0.7 * nim_cost_per_call + 0.3 * claude_cost_per_call)
    savings = all_claude - nim_mixed
    print(f"{calls_per_day:>12,} | ${all_claude:>11.2f} | ${all_mini:>11.2f} | ${nim_mixed:>11.2f} | ${savings:>9.2f}")
EOF
```

Expected output (at these cost estimates):
```
      Volume |   All Claude |  All GPT-mini |  NIM (P3/P4) |    Savings
--------------------------------------------------------------------
         100 |        $45.00 |         $0.33 |        $13.65 |     $31.35
       1,000 |       $450.00 |         $3.30 |       $136.50 |    $313.50
      10,000 |     $4,500.00 |        $33.00 |     $1,365.00 |  $3,135.00
     100,000 |    $45,000.00 |       $330.00 |    $13,650.00 | $31,350.00
```
At 10,000 calls/day, routing P3/P4 to NIM saves ~$3,135/month vs always-on Claude. The savings justify even a dedicated Modal GPU ($1.10/hr A10G = ~$800/month) once you exceed ~3,000 calls/day.

**What the stddev tells you about reliability:**
If NIM stddev is high (>1s on a ~2s mean), run the benchmark again at different times of day. NGC hosted NIM shares GPU resources — load varies. A dedicated GPU has flat latency because you own the hardware.

---

## Step 5: The vLLM Alternative

NIM and vLLM solve the same problem: run a model efficiently on GPU and expose it via API. Understanding the difference:

| | NVIDIA NIM | vLLM |
|---|---|---|
| What it is | Container with TensorRT-optimized model | Python server with PagedAttention optimization |
| Models | NVIDIA-packaged only (curated catalog) | Any Hugging Face model |
| Performance | Faster (TensorRT, FP8 quantization) | Slightly slower, more flexible |
| Setup | `docker run nvcr.io/nim/...` — model downloads automatically | Manual model download + server config |
| GPU requirement | NVIDIA only | NVIDIA, AMD (ROCm), or CPU (slow) |
| Best for | Standard models (Llama, Mistral) at max performance | Custom/fine-tuned models, model flexibility |

For AOIS v13: NIM is the right choice — Llama 3.1 8B is a NIM-packaged model and the performance is better. vLLM takes over in v14 when you deploy a fine-tuned model that NIM doesn't package.

---

## Common Mistakes

**`nvidia_nim/` model not found** *(recognition)*
Model IDs must match NVIDIA's catalog exactly. NIM model IDs use the organization/model format:
```
nvidia_nim/meta/llama-3.1-8b-instruct     ✓
nvidia_nim/llama-3.1-8b-instruct          ✗ (missing org prefix)
nvidia_nim/meta-llama/Llama-3.1-8B        ✗ (HuggingFace format, not NIM format)
```
*(recall)*: check available models at build.nvidia.com → Model Catalog. The model ID shown on each model page is the exact string for `nvidia_nim/`.

---

**Auto-routing double-calls P1 incidents expensively** *(recognition)*
With `auto_route=True` and initial `tier="standard"`: AOIS first calls GPT-4o-mini (cost: $0.0001), then re-calls Claude premium (cost: $0.015). For P1/P2, the premium re-call is correct. But if you set `tier="premium"` AND `auto_route=True`, AOIS calls Claude twice for P1/P2 (initial + re-route both hit Claude because `optimal_tier == tier`).

*(recall — trigger it)*:
```bash
# This calls Claude twice — wasteful
curl -X POST http://localhost:8000/analyze \
  -d '{"log": "prod db down", "tier": "premium", "auto_route": true}'
```
Fix: the `if optimal_tier != tier:` guard in the endpoint prevents the redundant call. Verify it is in the code. If auto-routing is the default, set `tier="standard"` (cheap first pass) and let SEVERITY_TIER_MAP upgrade/downgrade as needed.

---

**NIM returns P3 for a P1 incident** *(recognition)*
The `llama-3.1-8b-instruct` model is less capable at reasoning than Claude. For complex incidents (cascading failures, subtle correlation across multiple log lines), the 8B model may under-classify severity.

*(recall — test it)*:
```bash
# Send a complex P1 to NIM directly vs Claude
COMPLEX_P1="2026-04-19 14:00:01 auth-service: redis timeout
2026-04-19 14:00:02 payment-service: auth token validation failed (redis unavailable)
2026-04-19 14:00:03 api-gateway: 503 rate limiting due to auth failures
2026-04-19 14:00:04 monitoring: 10000 requests/min hitting api-gateway, all 503"

curl -X POST http://localhost:8000/analyze \
  -d "{\"log\": \"$COMPLEX_P1\", \"tier\": \"nim\"}"

curl -X POST http://localhost:8000/analyze \
  -d "{\"log\": \"$COMPLEX_P1\", \"tier\": \"premium\"}"
```
If NIM returns P2 and Claude returns P1, the severity routing decision matters. Fix: use `auto_route=True` with `tier="standard"` (GPT-4o-mini) for the first pass — it is better at severity classification than 8B models while being cheaper than Claude.

---

**NGC API rate limit on free tier** *(recognition)*
The NGC free tier allows 40 requests/minute. If you run the benchmark with `n=10` or fire multiple concurrent requests, you hit the limit:
```
litellm.RateLimitError: NVIDIAException - {"title":"Too Many Requests", "status":429}
```
*(recall)*: The benchmark uses `n=3` (3 iterations per model). If you need higher throughput for testing, use the paid NGC tier or switch to Modal's dedicated GPU (no rate limit).

---

**Forgetting that `auto_route` calls the model twice** *(recognition)*
`auto_route=True` makes two LLM calls: one to classify severity, one with the optimal tier. If the initial tier is already the optimal tier (e.g., `tier=premium` for a P1 log), the second call is skipped by the `if optimal_tier != tier:` guard. But if you set `tier=standard` and the log is P1, you pay for one GPT-4o-mini call + one Claude call. This is intentional (standard classifies, Claude analyzes), but callers should be aware.

*(recall)*: Check cost_usd in the response. For a P1 log with `auto_route=True, tier=standard`:
```bash
curl -X POST http://localhost:8000/analyze \
  -d '{"log": "all database connections exhausted, writes failing", "tier": "standard", "auto_route": true}' \
  | python3 -m json.tool | grep cost_usd
```
The `cost_usd` reflects the second (Claude) call only. The first (GPT-4o-mini) call cost is not tracked separately. For full cost visibility across both calls, Langfuse traces each individually.

---

## Troubleshooting

**`litellm.AuthenticationError` on NIM call:**
```
litellm.AuthenticationError: NVIDIAException - {"title":"Unauthorized"}
```
The `NVIDIA_NIM_API_KEY` is not set or expired. Check:
```bash
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('NVIDIA_NIM_API_KEY', 'NOT SET')[:15])"
```
If it shows `NOT SET`, the key is missing from `.env`. If it shows the key but the error persists, regenerate the key at build.nvidia.com (keys do not expire but can be revoked).

**NIM model returns wrong JSON structure:**
Instructor validates the response. If the 8B model returns malformed JSON or a response that does not match `IncidentAnalysis`, Instructor retries (up to `max_retries=2`). If all retries fail:
```
instructor.exceptions.InstructorRetryException: Max retries exceeded
```
This means the 8B model is consistently unable to fill the schema correctly for this log. The fallback in the endpoint (`analyze(data.log, "standard")`) catches this and retries with GPT-4o-mini. This is the safety net for NIM quality failures.

**NIM latency spikes on first call (cold start):**
NGC hosted NIM may have a warm-up period. The first call can take 5–10s while the model loads on NVIDIA's infrastructure. Subsequent calls are faster. Run the benchmark twice — ignore the first result of the first run.

If cold start latency matters for your use case, NGC offers dedicated endpoints (paid tier) that keep the model warm. For AOIS P3/P4 routing, the occasional cold start is acceptable — these are warning-level incidents, not production-down emergencies where seconds matter.

**`litellm.BadRequestError` with NIM model:**
Some NIM models do not support `tool_use` / function calling — the feature Instructor relies on. If the 8B model returns:
```
litellm.BadRequestError: NVIDIAException - tool_use is not supported for this model
```
Switch to a model that supports tool use. As of 2026, `meta/llama-3.1-8b-instruct` supports it. If you switch to a different model from the NGC catalog, check its page for "Function Calling: Supported" before routing Instructor calls to it. The fallback in the endpoint (`analyze(data.log, "standard")`) handles this gracefully — if NIM fails, GPT-4o-mini picks it up.

---

## Connection to later phases

- **v14 (vLLM)**: vLLM serves fine-tuned models that NIM cannot package. The architecture is identical — OpenAI-compatible API, LiteLLM routes to it. The difference: vLLM runs anything from HuggingFace; NIM runs NVIDIA-approved models at TensorRT speed. Both appear in AOIS's routing table.
- **v15 (Fine-tuning)**: You fine-tune Mistral 7B on 500 AOIS incident classifications. The fine-tuned model is deployed via vLLM. The routing question becomes: does the fine-tuned model outperform NIM's Llama 8B on your specific log patterns? The eval framework answers this.
- **v16 (OpenTelemetry)**: NIM calls generate the same OTel spans as Claude calls — `gen_ai.model`, `gen_ai.prompt_tokens`, `gen_ai.completion_cost`. Grafana shows you real-time: "what % of my inference cost is NIM vs Claude?" and "does auto-routing actually save money?"
- **v29 (Weights & Biases)**: Track NIM accuracy as an experiment. Does the 8B model classify AOIS incidents with acceptable accuracy compared to Claude? W&B gives you the chart that answers this systematically, not by gut feel.
- **The principle**: The routing table in AOIS will keep growing — NIM, vLLM, fine-tuned models, Cerebras, Groq. LiteLLM abstracts all of it. The mental model from v2 (one codebase, any model) is what makes adding each new tier a 2-line change.

---

## Mastery Checkpoint

**1. The NGC API connection**
Without running the server, verify LiteLLM can reach NIM directly:
```python
python3 -c "
import litellm; from dotenv import load_dotenv; load_dotenv()
r = litellm.completion(model='nvidia_nim/meta/llama-3.1-8b-instruct',
    messages=[{'role':'user','content':'say: ok'}], max_tokens=5)
print(r.choices[0].message.content)
"
```
Expected: `ok` (or similar). If this fails, fix the API key before continuing.

**2. The routing decision from memory**
Without notes: state which model tier AOIS uses for each severity level with `auto_route=True`. Then explain why P3 goes to NIM (not Groq, not GPT-4o-mini). What is the deciding factor — latency, cost, or quality?

**3. Run the full benchmark and interpret results**
```bash
python3 test_nim.py
```
After running, answer: at 5,000 P3/P4 analyses per day for 30 days, what is the cost difference between routing all of them to NIM vs routing all of them to GPT-4o-mini? Show your calculation.

**4. Trigger the NIM quality fallback**
Send a log so complex that the 8B model is likely to misclassify it. Verify the endpoint falls back gracefully:
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "cascading failure across 4 services with root cause in redis sentinel", "tier": "nim"}'
```
Then send the same log to `tier: premium`. Compare the `severity`, `summary`, and `suggested_action`. Does the quality difference justify the cost difference for P1/P2?

**5. The cost-aware routing logic in code**
Locate `SEVERITY_TIER_MAP` and the auto-route logic in `main.py`. Change the routing so P2 also goes to NIM (instead of Claude). Restart the server. Send a P2 log with `auto_route=true`. Verify the provider in the response is NIM. Then revert — P2 should stay on Claude. Explain why.

**6. NIM in the inference landscape**
Fill in this table from memory:

| Provider | Hardware | Cost tier | Best use case for AOIS |
|----------|----------|-----------|----------------------|
| Ollama | ? | free | ? |
| NVIDIA NIM | ? | ~$0.000008/call | ? |
| Groq | ? | ~$0.000001/call | ? |
| GPT-4o-mini | H100s | ~$0.000110/call | ? |
| Claude premium | H100s | ~$0.015/call | ? |

Then answer: why does AOIS need all five tiers instead of just always using the cheapest one (Groq)?

**7. The inference hardware question**
NVIDIA NIM requires NVIDIA GPUs. Groq runs on custom LPU silicon. Claude runs on Anthropic's H100 clusters. For AOIS's specific workload (short-context log analysis, ~500 tokens in/out), which hardware property matters most — memory bandwidth, compute throughput, or silicon architecture? Research: what makes the Groq LPU faster than GPU for token generation, and why does that matter less for batch-style inference like AOIS's P3/P4 routing?

**The mastery bar:** You can route AOIS logs to NVIDIA NIM via LiteLLM, explain the cost-aware routing logic (`SEVERITY_TIER_MAP`, `auto_route`), and quantify the cost difference between NIM and Claude at production volume. You understand where NIM fits in the inference landscape and when to use Modal GPU vs NGC API vs a dedicated GPU.
