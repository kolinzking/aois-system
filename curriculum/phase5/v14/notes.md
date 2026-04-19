# v14 — vLLM on Modal: Self-Hosted GPU Inference

⏱ **Estimated time: 3–4 hours**

---

## Prerequisites

Phase 5 started. v13 code is committed (NIM tier in main.py). Modal account created.

Verify:
```bash
python3 -c "import modal; print(modal.__version__)"
# Expected: 0.6x.x (any recent version)

modal token list
# Expected: shows your authenticated token
# If not authenticated: modal token new
```

Verify AOIS still runs:
```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

---

## Learning Goals

By the end you will be able to:

- Explain what vLLM is and why it exists (throughput problem, KV cache, continuous batching)
- Deploy a quantized open-source model on Modal serverless GPU
- Route AOIS traffic to your own model endpoint via LiteLLM
- Describe the full inference provider landscape: Groq vs NIM vs Modal/vLLM vs Ollama — when each wins
- Read throughput/latency benchmarks and make cost-per-call routing decisions

---

## Why This Version Exists

At v2 you built LiteLLM routing with four tiers. The cheapest tier was Groq. Groq is fast and cheap but:

1. You don't control the model. Groq's model catalog is limited.
2. You can't fine-tune what runs there (that's v15).
3. At high volume, Groq's rate limits become real.
4. For air-gapped or compliance environments, you need your own inference.

vLLM solves all four. It is the production-grade inference engine used at Mistral, Anyscale, and most organizations running their own models. After v14, AOIS can use any open-source model ever trained — no API key required, no rate limits, no external dependency.

The catch: you need a GPU. Modal gives you serverless GPU — pay per second, scale to zero when idle.

---

## What Is vLLM?

vLLM is a high-throughput inference server built at UC Berkeley. It was the first implementation of **PagedAttention** — a memory management technique that treats the GPU KV cache like virtual memory in an OS. Before PagedAttention, the KV cache (the memory of what a model has seen in a conversation) was statically allocated. Most of it was wasted. Throughput was limited by that waste.

PagedAttention allocates KV cache in small pages, reuses them across requests, and enables **continuous batching** — instead of waiting for a full batch before processing, vLLM starts on new requests as soon as previous ones finish. The result: 10–24x throughput improvement over naive inference at the same latency.

In plain terms: one A10G GPU with vLLM can serve what would require 10 GPUs with a naive inference loop.

**The things you need to understand:**

| Term | What it means |
|------|--------------|
| KV cache | Stored key/value attention tensors from previous tokens — what lets the model "remember" earlier context without recomputing |
| Continuous batching | Process requests as they arrive, not in fixed-size batches — eliminates GPU idle time between requests |
| PagedAttention | Non-contiguous KV cache memory allocation — the core vLLM innovation |
| gpu_memory_utilization | Fraction of GPU VRAM vLLM reserves for KV cache (0.90 = 90%) |
| tensor parallelism | Split a single model across multiple GPUs (needed for 70B+ models) |

---

## The Inference Provider Landscape (Full Picture)

After v14, AOIS can route to all of these. Here is where each wins:

| Provider | Latency | Cost/1M tokens | Best for | Limit |
|----------|---------|----------------|----------|-------|
| Claude (Anthropic) | 800–2000ms | $3–$15 | P1/P2 incidents, reasoning | Expensive at volume |
| GPT-4o-mini | 400–800ms | $0.15 | Standard summarization | OpenAI dependency |
| Groq | 100–300ms | $0.05–$0.20 | Ultra-low latency | Limited model catalog |
| Together AI | 400–1000ms | $0.10–$0.80 | Open-source models, batch | Shared infra |
| Fireworks AI | 300–800ms | $0.10–$0.50 | Fast open-source inference | Shared infra |
| NVIDIA NIM | 200–600ms | NGC credit / free tier | NVIDIA-hosted Llama/Mistral | NGC key required |
| **Modal + vLLM** | 1000–4000ms* | $0.000012/call† | P3/P4 volume, any model | Cold start penalty |
| Ollama (local) | 500–2000ms | $0 (hardware) | Air-gapped, testing | Single machine |

*Cold start adds 30–120s first time. Warm container: 1–4s.
†A10G at $0.000612/sec, Mistral-7B at ~20 tokens/sec = ~0.03s/call = $0.000018/call.

**The insight:** at 10,000 P3/P4 calls per day, Modal+vLLM costs ~$0.18/day. Groq at the same volume costs ~$1.00/day. Claude costs ~$50/day. The right tier matters.

---

## What Is Modal?

Modal is serverless GPU compute. You define your function in Python, decorate it with `@app.cls(gpu=...)`, and Modal handles:

- Provisioning the GPU instance
- Building and caching the container image
- Downloading and caching model weights
- Scaling to zero when no requests arrive
- Scaling up when requests arrive

You pay per second of GPU time. Zero requests = zero cost.

The alternative is renting a Hetzner GPU server (€2.49/hr) or an AWS GPU instance — both charge by the hour even when idle. For intermittent workloads like AOIS, Modal wins on cost unless your utilization is >40%.

---

## Step 1 — Install Modal and Authenticate

```bash
pip install modal
modal token new
# Opens browser, authenticate with GitHub or Google
# Expected output: Token stored at /home/<user>/.modal/credentials

modal token list
# Expected: lists your token with workspace name
```

---

## Step 2 — Create the HuggingFace Secret in Modal

vLLM downloads model weights from HuggingFace at build time. Mistral-7B-Instruct-v0.3 is not gated, but having a token avoids rate limiting on the HF Hub.

```bash
# In Modal dashboard: https://modal.com/secrets
# Create new secret named "huggingface-secret"
# Key: HF_TOKEN
# Value: your HuggingFace token (from hf.co/settings/tokens)
```

Then verify:
```bash
modal secret list
# Expected: shows huggingface-secret
```

If you do not have a HuggingFace token:
```bash
# Go to https://huggingface.co/settings/tokens
# Create a "read" token
# Paste it in the Modal secret
```

---

## Step 3 — Understand the Modal Deployment File

Read `vllm_modal/serve.py`. The key parts:

**`@app.build()`** — runs once when you `modal deploy`. Downloads Mistral-7B weights (~14GB) and bakes them into the container snapshot. After the first deploy, weights are cached — subsequent deploys are fast.

**`@app.enter()`** — runs when a container starts (cold start). Loads the vLLM engine into GPU VRAM. This is the slow part (~30–90s). Modal keeps the container warm for 5 minutes after the last request (`container_idle_timeout=300`).

**`@app.web_endpoint(method="POST")`** — exposes the function as an HTTPS endpoint. LiteLLM hits this directly.

**`allow_concurrent_inputs=32`** — vLLM handles its own batching internally. Telling Modal to allow 32 concurrent inputs means 32 requests can reach the vLLM engine simultaneously — it batches them via PagedAttention.

**The model revision is pinned** (`MODEL_REVISION = "e0bc86c..."`). Never use `main` or `latest` in production. A model author can push breaking changes to HuggingFace at any time. Pin to a commit hash.

---

▶ **STOP — do this now**

Grep the key configuration parameters from `vllm_modal/serve.py`:

```bash
grep -n 'gpu_memory_utilization\|allow_concurrent_inputs\|MODEL_REVISION\|container_idle_timeout\|keep_warm' vllm_modal/serve.py
```

Expected output (line numbers will vary):
```
7:MODEL_REVISION = "e0bc86c..."
28:    container_idle_timeout=300,
29:    allow_concurrent_inputs=32,
34:    gpu_memory_utilization=0.90,
```

Now calculate the GPU block impact of halving `gpu_memory_utilization`:

```python
# A10G has 24GB VRAM. vLLM reserves gpu_memory_utilization fraction for KV cache.
# Each KV cache block holds 16 tokens.
# Mistral-7B in fp16 uses each block at ~1MB (approximate).

vram_gb = 24
for util in [0.90, 0.50]:
    kv_vram_gb = vram_gb * util
    approx_blocks = int(kv_vram_gb * 1000)  # rough: 1MB per block
    print(f"gpu_memory_utilization={util}: ~{approx_blocks} KV blocks available")
```

Expected:
```
gpu_memory_utilization=0.90: ~21600 KV blocks available
gpu_memory_utilization=0.50: ~12000 KV blocks available
```

More blocks = more concurrent tokens in flight = higher throughput under load. Halving `gpu_memory_utilization` halves your effective batching capacity. Now you know the number, not just the direction.

---

## Step 3.5 — What Changed in main.py

Before deploying, understand the AOIS-side changes. Open `main.py` and find the `ROUTING_TIERS` dict. The vLLM tier entry looks like this:

```python
"vllm": {
    "model": "openai/mistralai/Mistral-7B-Instruct-v0.3",
    "cost_per_1k_input_tokens": 0.0000012,
    "cost_per_1k_output_tokens": 0.0000012,
},
```

And in `analyze()`, the extra kwarg block:

```python
extra_kwargs = {}
if tier == "vllm":
    vllm_url = os.getenv("VLLM_MODAL_URL")
    if not vllm_url:
        raise ValueError("VLLM_MODAL_URL not set in environment")
    extra_kwargs["api_base"] = vllm_url
```

**Why this pattern works:**

LiteLLM uses the `openai/` prefix to select the OpenAI provider adapter — which implements the chat completions API format. By passing `api_base`, you redirect where the request goes. The remote endpoint (your Modal container) speaks the same OpenAI wire protocol, so no adapter change is needed. This is the universal pattern for any self-hosted OpenAI-compatible server.

The cost values in `ROUTING_TIERS` are approximations — Modal charges by GPU time, not tokens. The numbers ($0.0000012/1k tokens) are back-calculated from A10G cost at ~20 tokens/sec. Langfuse will show these as the recorded cost per call — useful for comparison dashboards in v29.

**`SEVERITY_TIER_MAP` now drives automatic routing:**

```python
SEVERITY_TIER_MAP = {
    "P1": "premium",
    "P2": "premium",
    "P3": "vllm",
    "P4": "vllm",
}
```

This map is checked in `analyze()` when `auto_route=True` is set on the `LogInput`. The flow: log arrives → severity assessed quickly → tier selected → LiteLLM routes to the right provider. Claude never sees a P4 log. Modal never sees a P1 incident. The routing is enforced in code, not by caller discipline.

---

## Step 3.6 — Quantization: Fitting Larger Models in Less VRAM

Mistral-7B in the default fp16 format uses ~14GB VRAM. The A10G has 24GB — it fits. But a 13B model in fp16 uses ~26GB and will not fit. And on smaller GPUs (T4: 16GB, L4: 24GB), even 7B models can be tight when paired with a large KV cache.

**Quantization** reduces the precision of model weights from 16-bit float to 8-bit or 4-bit integers. This is a fundamental tool for production inference.

| Format | Precision | VRAM (7B model) | Quality impact |
|--------|-----------|-----------------|----------------|
| fp16 | 16-bit float | ~14GB | Baseline |
| int8 | 8-bit integer | ~7GB | <1% degradation |
| int4 (AWQ) | 4-bit integer | ~4GB | 1–3% degradation |
| int4 (GPTQ) | 4-bit integer | ~4GB | 1–4% degradation |

AWQ (Activation-aware Weight Quantization) and GPTQ are the two dominant 4-bit quantization methods. Both are supported natively in vLLM.

To serve a pre-quantized AWQ model, change one line in `serve.py`:

```python
# Replace:
MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.3"

# With an AWQ version (check HuggingFace for availability):
MODEL_NAME = "TheBloke/Mistral-7B-Instruct-v0.2-AWQ"

# And add to the vllm engine args:
AsyncEngineArgs(
    model=MODEL_NAME,
    quantization="awq",           # tell vLLM which quantizer was used
    gpu_memory_utilization=0.90,
    max_model_len=4096,
)
```

In fp16, after v14 deploys, you can always check how much VRAM is actually being used:

```bash
modal run vllm_modal/serve.py
# After the container starts, look for lines like:
# GPU blocks: 1872, CPU blocks: 2048
# Each block is a 16-token KV cache page
# More blocks = larger effective context window under concurrent load
```

**The production rule:** for 7B models on A10G, fp16 is fine. For 13B+ or when running on T4/L4, use AWQ. For maximum throughput on high-volume P4 logs, AWQ on a smaller GPU instance costs less than fp16 on a larger one.

---

## Step 4 — Deploy to Modal

```bash
modal deploy vllm_modal/serve.py
```

Expected output (first deploy — downloads ~14GB of weights):
```
✓ Initialized. View app at https://modal.com/apps/your-workspace/aois-vllm
✓ Created objects.
Building image aois-vllm-...
  Downloading model mistralai/Mistral-7B-Instruct-v0.3 (~14GB)...
  ... (2–5 minutes)
✓ App deployed in 312s.
  └── VLLMServer.v1_chat_completions => https://your-workspace--aois-vllm-vllmserver-v1-chat-completions.modal.run
```

Copy the `https://...modal.run` URL. That is your inference endpoint.

Subsequent deploys (weights cached):
```
✓ App deployed in 14s.
```

---

## Step 5 — Configure AOIS to Use the Endpoint

Add to `.env`:
```bash
VLLM_MODAL_URL=https://your-workspace--aois-vllm-vllmserver-v1-chat-completions.modal.run
```

LiteLLM uses the `openai/` prefix plus `api_base` to route to any OpenAI-compatible API. The model name in the `openai/mistralai/Mistral-7B-Instruct-v0.3` format tells LiteLLM which model to report in its cost tracking.

Test the connection directly:
```bash
curl -X POST "$VLLM_MODAL_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Say hello in one sentence."}
    ],
    "max_tokens": 50
  }'
```

Expected response:
```json
{
  "id": "cmpl-abc123",
  "object": "chat.completion",
  "model": "mistralai/Mistral-7B-Instruct-v0.3",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "Hello! It's great to meet you."},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21}
}
```

---

▶ **STOP — do this now**

Before running AOIS, test vLLM directly with a real log:

```bash
curl -X POST "$VLLM_MODAL_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "system",
        "content": "You are an SRE. Classify this log with severity P1-P4 and a one-sentence summary."
      },
      {
        "role": "user",
        "content": "pod/worker-9b4f2 OOMKilled exit code 137, memory limit 256Mi"
      }
    ],
    "max_tokens": 200
  }'
```

You are bypassing AOIS entirely — hitting vLLM directly. This is the baseline. Note:
- Response time (first call vs second call — warm vs cold)
- Whether the model follows the format instructions

Then route through AOIS:
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "pod/worker-9b4f2 OOMKilled exit code 137", "tier": "vllm"}'
```

Expected:
```json
{
  "summary": "Worker pod OOMKilled due to memory limit exceeded",
  "severity": "P2",
  "suggested_action": "Increase pod memory limit or investigate memory leak",
  "confidence": 0.85,
  "provider": "openai/mistralai/Mistral-7B-Instruct-v0.3",
  "cost_usd": 0.000018
}
```

---

## Step 6 — Run the Full Benchmark

```bash
python3 test_vllm.py
```

Expected output (truncated):
```
============================================================
Tier: premium
============================================================

  [OOMKilled]
  ✓ severity: P2 (expected P2)
    latency:    1243ms
    cost:       $0.001240
    provider:   anthropic/claude-opus-4-6

  [CrashLoopBackOff]
  ✓ severity: P2 (expected P2)
    latency:    989ms
    cost:       $0.001180

  [Disk pressure]
  ✓ severity: P3 (expected P3)
    latency:    876ms
    cost:       $0.000890

  [High latency]
  ✓ severity: P3 (expected P3)
    latency:    1102ms
    cost:       $0.001050

============================================================
Tier: vllm
============================================================

  [OOMKilled]
  ✓ severity: P2 (expected P2)
    latency:    1840ms
    cost:       $0.000018

  [CrashLoopBackOff]
  ✓ severity: P2 (expected P2)
    latency:    1560ms
    cost:       $0.000016

  [Disk pressure]
  ✓ severity: P3 (expected P3)
    latency:    1320ms
    cost:       $0.000015

  [High latency]
  ✓ severity: P3 (expected P3)
    latency:    1490ms
    cost:       $0.000014

============================================================
SUMMARY
============================================================
Log                  Tier        Latency         Cost  Correct
------------------------------------------------------------
OOMKilled            premium       1243ms  $0.001240      yes
OOMKilled            vllm          1840ms  $0.000018      yes
CrashLoopBackOff     premium        989ms  $0.001180      yes
CrashLoopBackOff     vllm          1560ms  $0.000016      yes
Disk pressure        premium        876ms  $0.000890      yes
Disk pressure        vllm          1320ms  $0.000015      yes
High latency         premium       1102ms  $0.001050      yes
High latency         vllm          1490ms  $0.000014      yes

Tier          Avg latency    Total cost   Accuracy
--------------------------------------------------
premium          1053ms       $0.004360      100%
vllm             1553ms       $0.000063      100%

Decision framework:
  vLLM (Modal A10G): ~$0.000010–0.000030/call, ~1000–3000ms, good for P3/P4 volume
  Claude premium:    ~$0.000500–0.002000/call, ~800–2000ms,  required for P1/P2
```

**Reading the results:**
- vLLM is ~60x cheaper than Claude premium per call
- vLLM is ~500ms slower on average (warm container)
- Accuracy is identical on these structured tasks
- The routing strategy from v13 (P3/P4 → cheap tier) now has a much better cheap tier

---

## Step 7 — Update SEVERITY_TIER_MAP (Optional)

If you got the NGC API key (v13), NIM and vLLM compete for the P3/P4 tier. If you don't have the NGC key, vLLM should be the P3/P4 tier:

```python
# In main.py — if no NGC key, route volume to vllm instead of nim
SEVERITY_TIER_MAP = {
    "P1": "premium",
    "P2": "premium",
    "P3": "vllm",    # self-hosted, cheapest, no external key
    "P4": "vllm",
}
```

This is the pattern: **cost-aware routing with quality gates.** The severity determines the quality tier; the tier map determines the provider. You can swap providers in the tier map without changing routing logic.

---

▶ **STOP — do this now**

Calculate the cost difference at scale. Open Python:

```python
# Scenario: 10,000 P3/P4 log analyses per day
calls_per_day = 10_000

claude_cost = calls_per_day * 0.001200  # average from your benchmark
vllm_cost   = calls_per_day * 0.000016  # average from your benchmark
groq_cost   = calls_per_day * 0.000050  # Groq Llama-3.1-8B approximate

print(f"Claude premium/day: ${claude_cost:.2f}")
print(f"vLLM (Modal)/day:   ${vllm_cost:.2f}")
print(f"Groq fast/day:      ${groq_cost:.2f}")
print(f"vLLM vs Claude:     {claude_cost/vllm_cost:.0f}x cheaper")
print(f"vLLM vs Groq:       {groq_cost/vllm_cost:.0f}x cheaper")
```

Expected output:
```
Claude premium/day: $12.00
vLLM (Modal)/day:   $0.16
Groq fast/day:      $0.50
vLLM vs Claude:     75x cheaper
vLLM vs Groq:       3x cheaper
```

At 10k calls/day, vLLM saves ~$4,300/year over Groq and ~$4,300/year over Claude. The Modal GPU cost is amortized across all those calls.

---

## Understanding Throughput vs Latency

These are different axes. This distinction matters at production scale.

**Latency**: time for one request to complete. vLLM on Modal warm: ~1–3s. That is slower than Groq (100–300ms) for a single call.

**Throughput**: requests per second the system can handle before queuing. vLLM with `allow_concurrent_inputs=32` and PagedAttention can process 32 concurrent requests and batch them. At 32 concurrent users, vLLM's effective throughput exceeds Groq's API limits.

The tradeoff:
- **Interactive, real-time** (human waiting): Groq wins — 200ms latency matters
- **Background processing, high volume** (batch log analysis): vLLM wins — throughput and cost matter
- **Critical incidents** (P1/P2): Claude wins — quality matters, cost irrelevant

AOIS auto-routes based on severity, which maps to these use cases naturally:
- P1/P2 = human waiting for response → Claude
- P3/P4 = background batch analysis → vLLM

---

## The Inference Hardware Race

You are now using vLLM on NVIDIA A10G. You should understand what the A10G is competing against and why there are multiple players in the inference hardware space.

**NVIDIA GPU (A10G, A100, H100)**

NVIDIA's hardware is the default. The A10G has 24GB VRAM, 250W TDP, and costs ~$0.60/hr on Modal. The A100 (80GB) handles 70B models. The H100 is the current flagship — 4x the throughput of A100 for transformer workloads due to the transformer engine and FP8 support.

vLLM was built for NVIDIA GPUs. PagedAttention maps directly to how CUDA manages memory. If you are running your own inference, NVIDIA is the safe default.

**Groq LPU (Language Processing Unit)**

Groq is not a GPU. It is a custom ASIC designed specifically for transformer inference. The architecture is a deterministic dataflow chip — no caches, no memory bandwidth bottleneck, completely predictable execution. The result: sub-100ms inference for 7B–70B models.

Why Groq exists: GPUs are general-purpose. They were designed for graphics, then repurposed for ML. A chip designed only for the transformer attention pattern will beat a GPU on latency every time. Groq proved that.

The limit: Groq's capacity is finite and shared. At high concurrent load, you hit rate limits. You do not own the hardware. You cannot run custom models. Groq wins on latency for API customers at moderate volume.

**Cerebras WSE (Wafer Scale Engine)**

Cerebras built the largest chip ever made — the entire wafer is one chip. A single WSE-3 chip has 900,000 AI cores and 44GB of SRAM on-chip. No memory bandwidth bottleneck at all — all memory is on the compute die.

The result: 70B models at 800+ tokens/second. For comparison, an A100 does ~40 tokens/second on a 70B model.

The limit: the WSE is not accessible as a self-hosted option. Cerebras offers an API (inference.cerebras.ai). Like Groq, you are renting capacity you do not control. The hardware is commercially available to enterprises at significant cost.

**Where each wins**

| Scenario | Winner | Why |
|----------|--------|-----|
| Sub-100ms single-user latency | Groq | Deterministic ASIC, no memory bottleneck |
| 70B+ model, one user, fastest | Cerebras | Wafer-scale on-chip SRAM |
| High-volume batch, custom model | NVIDIA + vLLM | You own the hardware, control the model |
| Fine-tuned model deployment | NVIDIA + vLLM | Groq/Cerebras don't accept custom weights |
| Cost at high throughput | NVIDIA + vLLM | Amortized hardware cost beats per-token fees |
| Air-gapped / compliance | NVIDIA + vLLM | No external API dependency |

**What this means for AOIS**

Your routing map now spans the full hardware landscape:
- Groq (`fast` tier) — when P3 latency still matters
- Modal + vLLM (`vllm` tier) — when P3/P4 volume and cost matter
- Claude (`premium` tier) — when P1/P2 quality is non-negotiable

A production AI platform engineer knows which hardware their traffic is hitting and why. You now do.

---

## Keep Warm: Eliminating Cold Starts in Production

Cold starts are acceptable in development. In production, a 90-second timeout on the first P1 alert is not acceptable.

Modal provides `keep_warm` — maintain N always-on container instances:

```python
@app.cls(
    gpu=GPU_CONFIG,
    container_idle_timeout=300,
    allow_concurrent_inputs=32,
    keep_warm=1,  # one container always running
    secrets=[modal.Secret.from_name("huggingface-secret")],
)
class VLLMServer:
    ...
```

Cost of `keep_warm=1` on A10G:
- $0.000612/sec × 86,400 sec/day = $52.88/day idle
- Break-even: if you have >88,000 calls/day, keep_warm is cheaper than cold starts

For AOIS in development: do not use `keep_warm`. Accept cold starts. In production, add it only if P3/P4 volume justifies it.

Alternative: implement a lightweight `/warm` endpoint that returns immediately but keeps the container alive, and have a cron job ping it every 4 minutes (under the 5-minute idle timeout). Cost: ~2ms GPU time per ping vs $52/day for keep_warm.

---

## Monitoring Your vLLM Deployment

vLLM exposes a `/metrics` endpoint in Prometheus format. Once your Modal container is running, you can read it directly:

```bash
curl "$VLLM_MODAL_URL/../metrics"
# Note: the metrics path depends on how Modal routes requests
# Check Modal dashboard → app → endpoint for the base URL
```

More practically, watch Modal's built-in logs while a request is in flight:

```bash
modal logs aois-vllm --follow
```

What to look for in the logs:

```
INFO:     Started server process [1]
INFO:     Uvicorn running on http://0.0.0.0:8000
# ^ Container started. Still cold — vLLM engine loading next.

INFO 04-19 14:22:01 llm_engine.py:161] Initializing an LLM engine
INFO 04-19 14:22:01 llm_engine.py:217] GPU blocks: 1872, CPU blocks: 2048
# ^ Engine ready. GPU blocks = how many 16-token KV pages fit in VRAM.
# More blocks = longer max context per concurrent request.

INFO 04-19 14:22:14 async_llm_engine.py:364] Received request cmpl-abc: ...
INFO 04-19 14:22:15 async_llm_engine.py:364] Finished request cmpl-abc.
# ^ Request arrived and completed. "Finished" in ~1s = warm container.
```

**Cold vs warm container:** a cold start shows 30–90 seconds between "Started server process" and "GPU blocks:". A warm container skips straight to "Received request" — the engine is already in VRAM.

**The key metric to track in production:** `avg_generation_throughput_toks_per_s` in the Prometheus output. This tells you whether PagedAttention batching is working. Under sustained concurrent load, this number should climb above single-request baseline. If it is stuck at single-request throughput under high concurrency, your `allow_concurrent_inputs` setting may be too low.

---

▶ **STOP — do this now**

After deploying, run this to understand what your container is doing:

```bash
# Watch logs while sending two concurrent requests
modal logs aois-vllm --follow &

curl -X POST "$VLLM_MODAL_URL" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "pod OOMKilled, classify severity P1-P4"}], "max_tokens": 100}' &

curl -X POST "$VLLM_MODAL_URL" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "disk pressure on node, classify severity P1-P4"}], "max_tokens": 100}' &

wait
```

Expected: both requests arrive in the log within milliseconds of each other. Both finish within 2–3 seconds. The engine batched them — you did not pay double latency for the second request.

This is PagedAttention working. Two requests, one batched execution pass. The first time you see this you understand why vLLM exists.

---

## Common Mistakes

**Mistake 1: Cold start surprise**

Trigger it: deploy and then wait 6+ minutes before sending a request (past the `container_idle_timeout=300` window). Then:
```bash
time curl -X POST "$VLLM_MODAL_URL" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "hello"}], "max_tokens": 10}'
```
You will see:
```
real    1m32.441s
```
The request hung for 92 seconds — Modal cold-started the container and loaded the vLLM engine into VRAM. This is expected. The error you may also see if your client has a short timeout:
```
curl: (28) Operation timed out after 30000 milliseconds
```

Fix: in `serve.py`, increase `container_idle_timeout=600` (10 min) for development. In production, use Modal's `keep_warm=1` to maintain one always-on container at low cost.

**Mistake 2: Forgetting `api_base`**

Trigger it: temporarily unset the env var and call the vllm tier:
```bash
VLLM_MODAL_URL="" python3 -c "
import requests
r = requests.post('http://localhost:8000/analyze',
  json={'log': 'pod OOMKilled', 'tier': 'vllm'})
print(r.json())
"
```
You will see:
```
LiteLLM Error: openai.AuthenticationError: No API key provided.
```
LiteLLM's `openai/` prefix without `api_base` sends the request to api.openai.com, not your Modal endpoint — and fails because you have no OpenAI key loaded for the vllm tier.

Fix: confirm `VLLM_MODAL_URL` is set in `.env` and that `analyze()` passes `api_base` in `extra_kwargs` when `tier == "vllm"`.

**Mistake 3: Wrong model name in LiteLLM**

Trigger it: change the model name in `ROUTING_TIERS["vllm"]` to remove the `openai/` prefix:
```python
# Wrong:
"model": "mistralai/Mistral-7B-Instruct-v0.3"
```
Send a request. You will see:
```
LiteLLM Error: model not found in provider map
```
LiteLLM uses the prefix to select the provider adapter. Without `openai/`, it does not know which adapter handles this model name.

Fix: restore the `openai/` prefix: `"openai/mistralai/Mistral-7B-Instruct-v0.3"`.

**Mistake 4: `gpu_memory_utilization=1.0`**

Trigger it: change `gpu_memory_utilization=1.0` in `serve.py` and redeploy. The container will start, then fail during engine initialization:
```
torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB
  (GPU 0; 22.08 GiB total capacity; 21.94 GiB already allocated)
```
vLLM reserves that fraction of VRAM at startup for the KV cache. At 1.0, there is no headroom left for CUDA operations (workspace, activations, temporary buffers).

Fix: revert to `gpu_memory_utilization=0.90`. Always leave 5–10% headroom.

**Mistake 5: Not pinning model revision**

This one does not produce an immediate error — it produces silent behavior drift. Trigger awareness of it:
```bash
# Check what commit your current pin points to
grep MODEL_REVISION vllm_modal/serve.py
# Expected: MODEL_REVISION = "e0bc86c..."

# What happens if you used "main":
# modal deploy pulls HuggingFace HEAD on every deploy
# Three months from now, Mistral pushes a new checkpoint to "main"
# Your endpoint changes behavior — severity classifications shift — with zero visibility
```

Fix: always pin `MODEL_REVISION` to a specific git commit hash. Find the current hash on the HuggingFace model page under "Files and versions" → click the commit hash next to any file.

---

## Troubleshooting

**Error: `modal.exception.NotFoundError: Secret 'huggingface-secret' not found`**
```
modal secret list
# Verify the secret is named exactly "huggingface-secret"
# Modal secrets are case-sensitive
```

**Error: `vllm.engine.async_llm_engine.AsyncLLMEngine loading failed`**
```
modal logs aois-vllm
# Check the full build log — usually a VRAM OOM during engine load
# Mistral-7B needs ~14GB VRAM in fp16
# A10G has 24GB — should be fine unless other processes are using VRAM
```

**Error: Instructor `ValidationError` on vLLM responses**
Mistral-7B can produce less reliable JSON compared to Claude. Instructor retries automatically (max_retries=2 in main.py). If failures persist:
```python
# Increase max_retries to 3 in analyze()
# Or add a system prompt reinforcement specifically for vLLM tier:
# "IMPORTANT: Always respond using the analyze_incident tool. Never output raw JSON."
```

**vLLM endpoint returns 500 on first request after deploy**
Modal's container starts cold. The first request can hit before the vLLM engine finishes loading. Solution: run the smoke test (`modal run vllm_modal/serve.py`) after deploy to warm the container before routing live traffic.

---

## Connection to Later Phases

**v15 (next):** You will fine-tune Mistral-7B on AOIS-specific SRE log data using LoRA. The fine-tuned model will be served from this same vLLM endpoint on Modal. You built the serving infrastructure here; v15 changes the model weights.

One important detail to preview: vLLM has native LoRA adapter support via `--enable-lora`. Instead of baking the fine-tuned weights into a new full model, you can serve the base Mistral-7B and hot-swap LoRA adapters at request time:

```python
# v15 addition to serve.py (preview — do not add yet)
AsyncEngineArgs(
    model=MODEL_NAME,
    enable_lora=True,
    max_lora_rank=64,
    gpu_memory_utilization=0.90,
)
```

The caller then specifies which adapter to use per request. This means one deployed vLLM instance can serve the base model AND the fine-tuned SRE model simultaneously — routing via the request payload. The v14 infrastructure you are building right now is exactly what makes this possible.

**v16 (observability):** You will add OpenTelemetry spans to the `analyze()` function. Every tier — including vLLM — will emit latency and cost metrics to Grafana. The `gpu_memory_utilization` and throughput metrics from vLLM's built-in `/metrics` endpoint will flow into Prometheus.

**v17 (Kafka):** AOIS will consume logs from Kafka topics and analyze in real-time. At high consumer lag, KEDA will scale AOIS pods. The vLLM endpoint on Modal handles the burst — it batches concurrent requests via PagedAttention. You are building the full pipeline now.

**v29 (Weights & Biases):** Every prompt version and model version will be tracked as a W&B experiment. You will compare fine-tuned vLLM vs base vLLM vs Claude across a ground truth eval set. The routing decision (`SEVERITY_TIER_MAP`) becomes data-driven.

---

## Mastery Checkpoint

Complete these before moving to v15:

1. `modal deploy vllm_modal/serve.py` succeeds. Endpoint URL is in your `.env` as `VLLM_MODAL_URL`.

2. Direct vLLM call via curl returns a valid OpenAI-compatible response within 5 seconds (warm container).

3. `curl http://localhost:8000/analyze -d '{"log": "...", "tier": "vllm"}'` returns a valid `IncidentAnalysis` with `provider` field showing the Modal model.

4. `python3 test_vllm.py` completes. Both tiers produce correct severity classifications on ≥3 of 4 log samples.

5. You can explain in one sentence why vLLM's cost per call is lower than Groq's at high volume, even though Groq is faster per call. (Answer: throughput — vLLM batches many concurrent requests on owned GPU; Groq charges per token on shared infra.)

6. You know the two knobs that control vLLM throughput: `gpu_memory_utilization` (KV cache size) and `allow_concurrent_inputs` (max concurrent batched requests).

7. `SEVERITY_TIER_MAP` in `main.py` routes P3/P4 to `vllm`. You understand why — cost and throughput over latency for non-critical logs.

8. `modal logs aois-vllm` — you can read the container logs and identify a cold start vs a warm serving event.

**The mastery bar:** you can take any open-source model from HuggingFace, deploy it on Modal with vLLM, expose it as an OpenAI-compatible endpoint, and route AOIS traffic to it via a single `VLLM_MODAL_URL` env var — without changing any other code.
