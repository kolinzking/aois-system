# v14 — Self-Hosted GPU Inference: SGLang, vLLM, and Dynamo

⏱ **Estimated time: 4–5 hours**

---

## Prerequisites

Phase 5 started. v13 code is committed (NIM tier in main.py).

Verify AOIS still runs:
```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

You need a [Vast.ai](https://vast.ai) account — free to create, you pay per hour only when a GPU is rented. No GPU rental needed until Step 5.

```bash
# Verify Python tools are available (install ahead of GPU time to save money)
pip install "sglang[all]>=0.4.0" vllm
python3 -c "import sglang; print(sglang.__version__)"
# Expected: 0.4.x or later

python3 -c "import vllm; print(vllm.__version__)"
# Expected: 0.4.x or later
```

---

## Learning Goals

By the end you will be able to:

- Explain what vLLM is and why it exists (PagedAttention, continuous batching, KV cache management)
- Explain what SGLang adds over vLLM specifically for multi-turn agent workloads (RadixAttention)
- Rent a GPU on Vast.ai, SSH in, and serve an open-source model via an OpenAI-compatible endpoint
- Route AOIS traffic to your self-hosted model via LiteLLM without changing application code
- Explain what NVIDIA Dynamo adds above vLLM/SGLang for fleet-scale multi-node inference
- Choose the right inference engine for a given workload: SGLang vs vLLM vs NIM vs Groq vs Dynamo

---

## Why This Version Exists

At v2 you built LiteLLM routing with four tiers. The cheapest tier was Groq. Groq is fast and cheap — but:

1. You do not control the model. Groq's catalog is limited.
2. You cannot fine-tune what runs there (that is v15).
3. At high volume, Groq's rate limits become real.
4. For compliance environments, logs must not leave your infrastructure.

SGLang and vLLM solve all four. They are production-grade inference servers — SGLang is now deployed on 400,000+ GPUs globally; vLLM is used at Mistral, Anyscale, and most organisations running their own models. After v14, AOIS can serve any open-source model ever trained. No API key, no rate limits, no external dependency.

The catch: you need a GPU. **Vast.ai** gives you hourly GPU rental at the cheapest rates available — RTX 3090 (24GB VRAM) from $0.25/hr, the same GPU that would cost $1.98/hr on Modal. You pay only for the hours you use.

> **Modal note:** The repo contains `vllm_modal/serve.py` — this documents a previous deployment attempt on Modal. Modal's cold starts (30–120s), dependency conflicts between vLLM versions, and $1.98/hr A10G cost (vs $0.25/hr RTX 3090 on Vast.ai) made it the wrong platform for persistent inference serving. Modal is the right choice for one-shot GPU jobs like fine-tuning runs (v15). For serving — where the server runs for hours — Vast.ai wins on cost by 5–8x.

---

## What Is Vast.ai?

Vast.ai is a peer-to-peer GPU marketplace. Server owners rent out idle GPU capacity; you pay per hour. The result: market-rate pricing that undercuts every managed GPU cloud.

**How the economics work:**

| GPU | VRAM | Vast.ai typical | Modal | RunPod | AWS p3.2xlarge |
|-----|------|-----------------|-------|--------|----------------|
| RTX 3090 | 24GB | $0.20–$0.35/hr | N/A | $0.44/hr | N/A |
| A10 | 24GB | $0.30–$0.45/hr | $1.98/hr | $0.74/hr | $3.83/hr |
| A100 (40GB) | 40GB | $1.20–$1.80/hr | N/A | $1.89/hr | $12.24/hr |
| H100 | 80GB | $2.50–$3.50/hr | N/A | $3.49/hr | N/A |

For AOIS GPU learning: start with RTX 3090 at $0.25/hr. It has 24GB VRAM — identical to an A10G — and will serve Llama-3.1-8B comfortably. Stop the instance when done. Cost for a full v14 session: ~$1.00–$2.00.

**Trade-offs vs managed platforms:**

Vast.ai instances are on third-party hardware — no SLA, occasional hardware variance. For learning and development this is fine. For a production inference endpoint, RunPod (with guaranteed uptime) or your own Hetzner GPU (when justified by sustained usage) are better fits. Vast.ai is the right tool here: cheapest hourly rate for experimenting with GPU inference.

---

## What Is vLLM?

vLLM is a high-throughput inference server built at UC Berkeley. It was the first implementation of **PagedAttention** — a memory management technique that treats the GPU KV cache like virtual memory in an OS.

Before PagedAttention, each request's KV cache (the stored key/value attention tensors representing context) was statically pre-allocated at max sequence length. Most of that allocation was wasted. Throughput was limited by this waste.

PagedAttention allocates KV cache in small pages, reuses them across requests, and enables **continuous batching**: instead of waiting for a full batch to finish, vLLM starts processing new requests as soon as any slot frees up. Result: 10–24× throughput improvement over naive HuggingFace inference.

In plain terms: one RTX 3090 with vLLM can serve what would require 10 GPUs with a naive inference loop.

**Key terms you must know:**

| Term | What it means |
|------|--------------|
| KV cache | Stored key/value attention tensors from previous tokens — what lets the model "remember" context without recomputing it |
| Continuous batching | Process requests as they arrive rather than waiting for fixed-size batches — eliminates GPU idle time |
| PagedAttention | Non-contiguous KV cache memory allocation — the core vLLM innovation |
| gpu_memory_utilization | Fraction of GPU VRAM vLLM reserves for KV cache (0.85 = 85%) |
| tensor parallelism | Split a single model across multiple GPUs — needed for 70B+ models |

---

## What Is SGLang?

vLLM asks "how do I serve a model efficiently?" SGLang asks "how do I serve a model efficiently specifically for agents?" The distinction is meaningful for AOIS.

### Why vLLM Falls Short for Multi-Turn Agents

vLLM's PagedAttention was designed for independent requests — each request gets its own KV cache, allocated fresh. For a single-turn chatbot this is fine. For an agent running a 10-step investigation, it creates waste.

When AOIS investigates an incident via the LangGraph loop (v23):
1. Turn 1: system prompt + log entry → LLM generates tool call
2. Turn 2: system prompt + log entry + tool result → LLM generates next tool call
3. Turn 3: system prompt + log entry + tool result 1 + tool result 2 → ...

At turn 10, the system prompt has been re-processed 10 times. The KV cache for those tokens has been computed from scratch each time. That is wasted GPU compute — the system prompt did not change.

vLLM introduced prefix caching to partially address this, but it is opt-in, coarse-grained, and only matches exact prefixes.

### SGLang's RadixAttention

SGLang (UC Berkeley Sky Computing Lab, spun out as RadixArk in January 2026 at $400M valuation, deployed on 400,000+ GPUs) solves this with **RadixAttention** — automatic, fine-grained KV cache reuse via a radix tree.

A radix tree stores all cached sequences as shared prefixes. When a new request arrives, SGLang finds the longest prefix already in cache and reuses its KV state. Only novel tokens need computing.

**Concrete example for AOIS:**

```
Turn 1: [system_prompt][log_entry][turn_1_tokens]
Turn 2: [system_prompt][log_entry][turn_1_tokens][tool_result_1][turn_2_tokens]
Turn 3: [system_prompt][log_entry][turn_1_tokens][tool_result_1][turn_2_tokens][tool_result_2][turn_3_tokens]
```

The radix tree finds `[system_prompt][log_entry]` is shared across all turns. Turn 2 only computes KV for `[tool_result_1][turn_2_tokens]`. Turn 3 only computes KV for `[tool_result_2][turn_3_tokens]`. The shared prefix KV state is never recomputed.

For AOIS's LangGraph SRE loop with 6 nodes and 10–15 tool calls per incident, this translates to 60–80% less KV computation per turn after the first.

### TGI Is Dead for New Projects

HuggingFace Text Generation Inference (TGI) entered official maintenance mode in December 2025. No new features are being developed. If you see TGI in a production codebase, it is legacy — do not start new projects with it.

---

## What Is NVIDIA Dynamo?

Released as open source at GTC 2026, Dynamo is NVIDIA's inference orchestration layer. It solves a different problem from vLLM or SGLang: not "how do I serve one model efficiently" but "how do I route requests across a fleet of GPU workers intelligently."

Dynamo sits above vLLM and SGLang. Each worker node runs vLLM or SGLang as the actual inference engine. Dynamo manages the routing layer between them.

**The three problems Dynamo solves:**

**1. Disaggregated prefill and decode**

In a standard LLM inference call:
- **Prefill**: process the entire input prompt — compute-bound, happens once, proportional to prompt length
- **Decode**: generate output tokens one by one — memory-bandwidth-bound, happens iteratively

These have different hardware requirements. A prefill node processes input in parallel (wants many cores, high compute throughput). A decode node generates tokens sequentially (wants high memory bandwidth, lower compute). Dynamo routes each phase to the right hardware.

On a single GPU, you pay this cost anyway. On a cluster, you can use cheaper hardware for decode (H100 for prefill, A10 for decode) — the compute cost drops significantly.

**2. KV cache-aware routing**

When an agent sends turn 2 of a conversation, Dynamo routes it to the worker that already has the KV cache for turn 1 — the radix tree is at the cluster level, not just within one server. This is SGLang's RadixAttention scaled out to a fleet.

**3. NIXL (NVIDIA Interconnect Library)**

When a request must move from one worker to another, Dynamo uses NIXL to transfer KV cache blocks directly via NVLink or InfiniBand — avoiding recomputation. KV state migrates with the request.

**What this means on a single Vast.ai GPU:**

- Disaggregated prefill/decode: minimal benefit (same hardware for both)
- KV cache-aware routing: local only (same as running vLLM directly)
- NIXL: not applicable (requires NVLink between nodes)

The single-GPU Dynamo demo is still valuable: it lets you see the router architecture, understand how it wraps vLLM, and observe the metadata it tracks. The production benefit kicks in when you have 4+ GPU nodes.

**The mental model:** vLLM/SGLang = one smart GPU worker. Dynamo = smart traffic director across many GPU workers.

---

## The Inference Provider Landscape

After v14, AOIS can route to all of these. Here is where each wins:

| Provider | Latency | Cost/1M tokens | Best for | Limit |
|----------|---------|----------------|----------|-------|
| Claude (Anthropic) | 800–2000ms | $3–$15 | P1/P2 incidents, reasoning | Expensive at volume |
| GPT-4o-mini | 400–800ms | $0.15 | Standard summarization | OpenAI dependency |
| Groq | 100–300ms | $0.05–$0.20 | Ultra-low latency | Limited model catalog, rate limits |
| Together AI | 400–1000ms | $0.10–$0.80 | Open-source models, batch | Shared infra |
| NVIDIA NIM | 200–600ms | NGC credit / free tier | NVIDIA-hosted Llama/Mistral | NGC key required |
| **Vast.ai + SGLang** | 500–2000ms | $0.10–0.50* | P3/P4 volume, agent multi-turn, any model | Spot hardware (no SLA), SSH setup |
| **Vast.ai + vLLM** | 600–2500ms | $0.10–0.50* | High-concurrency batch inference | Same as above |
| Ollama (local) | 500–5000ms | $0 (hardware) | Air-gapped, testing | Single machine speed |

*Vast.ai RTX 3090 at $0.25/hr. At 80 tokens/sec, 100-token response ≈ 1.25s → ~$0.00009/call. At 1M tokens/day that is ~$25/day GPU rental vs ~$3,000/day for Claude.

**The inference engine comparison (for self-hosted):**

| Engine | Strength | Best for | Status |
|--------|----------|----------|--------|
| **SGLang** | RadixAttention — automatic prefix sharing, agentic multi-turn | Multi-turn agents, AOIS investigations | Active — production standard 2026 |
| **vLLM** | PagedAttention — high-concurrency single-turn | Batch inference, high-throughput API | Active — strong for non-agent workloads |
| **TensorRT-LLM** | NVIDIA-optimised, maximum throughput | Fixed model on NVIDIA hardware | Active — NVIDIA-specific |
| **Triton** | Full control, ensemble pipelines | Pre/post-processing chains | Active — high operational complexity |
| **TGI** | Legacy HuggingFace wrapper | Nothing new | **Maintenance mode Dec 2025 — dead** |

---

## Step 1 — Rent a GPU on Vast.ai

Go to [vast.ai](https://vast.ai). Create an account and add your SSH public key:

```bash
# Get your SSH public key
cat ~/.ssh/id_rsa.pub
# Expected: ssh-rsa AAAA... or ssh-ed25519 AAAA...
# Paste this in Vast.ai → Account → SSH Keys
```

Search for a GPU:
- Filter: 24GB VRAM (RTX 3090 or A10), >40 GB disk, CUDA 12.x
- Sort by: price per hour ascending
- Target: $0.20–$0.35/hr

Click **Rent**. Once provisioned (30–120s), you get an SSH connection string.

---

## Step 2 — Connect and Prepare the Environment

```bash
# Connect (Vast.ai gives you the exact command)
ssh -p 12345 root@192.168.x.x
# Expected: root@container-abc123:~#
```

Inside the container:

```bash
# Verify GPU
nvidia-smi
# Expected output includes:
# | NVIDIA GeForce RTX 3090   | (or A10)
# |  GPU 0  ... 24576MiB / 24576MiB   0MiB |

# Verify Python and CUDA
python3 --version && nvcc --version
# Expected:
# Python 3.11.x
# Cuda compilation tools, release 12.x

# Install inference engines (do this while the GPU is billable — it's fast)
pip install "sglang[all]>=0.4.0" vllm huggingface_hub
# Expected: takes 2–4 minutes — large dependencies

# Pre-download model weights (saves time during exercises)
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('meta-llama/Llama-3.1-8B-Instruct')"
# Expected: takes 5–10 minutes (8B model is ~15GB)
# If you see a gated model error:
#   huggingface-cli login  # enter your HF token
#   # Accept the Llama-3.1 license at hf.co/meta-llama/Llama-3.1-8B-Instruct
```

---

## Step 3 — Serve a Model with SGLang

SGLang is the primary recommendation for AOIS. Its RadixAttention directly benefits your agent workloads.

```bash
# Start SGLang server (RadixAttention enabled by default — no flag needed)
python -m sglang.launch_server \
  --model-path meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 \
  --port 30000 \
  --mem-fraction-static 0.85

# --mem-fraction-static: fraction of GPU VRAM reserved for KV cache
# 0.85 leaves 15% for model weights overhead and CUDA workspace
```

Expected output:

```
[SGLang] Initializing model: meta-llama/Llama-3.1-8B-Instruct
[SGLang] GPU memory: 24576 MiB total, 20890 MiB reserved for KV cache
[SGLang] RadixAttention enabled (automatic prefix caching active)
[SGLang] Server started on http://0.0.0.0:30000
[SGLang] OpenAI-compatible endpoint: /v1/chat/completions
```

Test it:

```bash
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "user", "content": "What causes OOMKilled in Kubernetes?"}
    ],
    "max_tokens": 150
  }'
```

Expected response:

```json
{
  "id": "sglang-abc123",
  "object": "chat.completion",
  "model": "meta-llama/Llama-3.1-8B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "OOMKilled in Kubernetes occurs when a container exceeds its memory limit. The Linux kernel's OOM killer terminates the process (exit code 137). Common causes: memory leak in the application, insufficient memory limit set in the pod spec, or a sudden traffic spike exceeding expected memory usage..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 18, "completion_tokens": 67, "total_tokens": 85}
}
```

---

▶ **STOP — do this now**

Check SGLang's cache hit rate during a simulated multi-turn investigation. Run three consecutive requests with the same system prompt:

```bash
# Simulate three turns of an AOIS investigation
SYSTEM="You are an SRE. Analyze Kubernetes incidents and classify severity P1-P4."

for msg in "pod OOMKilled exit code 137" "CrashLoopBackOff 5 times in 10 minutes" "node disk pressure eviction"; do
  curl -s http://localhost:30000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{
      \"model\": \"meta-llama/Llama-3.1-8B-Instruct\",
      \"messages\": [
        {\"role\": \"system\", \"content\": \"$SYSTEM\"},
        {\"role\": \"user\", \"content\": \"$msg\"}
      ],
      \"max_tokens\": 100
    }" | python3 -m json.tool | grep '"content"' | head -1
done

# Then check the cache statistics
curl -s http://localhost:30000/get_server_info | python3 -m json.tool
```

Expected output from `get_server_info` (after 3+ requests):

```json
{
  "model_path": "meta-llama/Llama-3.1-8B-Instruct",
  "prefix_cache_hit_tokens": 3840,
  "prefix_cache_miss_tokens": 412,
  "prefix_cache_hit_rate": 0.903
}
```

A 90%+ hit rate means 9 out of 10 tokens in the shared system prompt are served from the radix tree cache — not recomputed. The first request always misses (cache cold). Every subsequent request with the same system prompt hits.

For AOIS's LangGraph SRE loop (v23) with 6 nodes and 10–15 tool calls per incident: this hit rate means 60–80% less KV computation per turn after the first. GPU time drops proportionally.

---

## Step 4 — Serve the Same Model with vLLM (Comparison)

Stop the SGLang server (Ctrl+C), then start vLLM on the same port:

```bash
# Stop SGLang first — both cannot hold the GPU simultaneously
# Then start vLLM
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 \
  --port 30000 \
  --gpu-memory-utilization 0.85
```

Expected output:

```
INFO 04-25 10:22:01 llm_engine.py:161] Initializing an LLM engine (v0.4.x)
INFO 04-25 10:22:14 llm_engine.py:217] GPU blocks: 3710, CPU blocks: 4096
INFO:     Started server process [1]
INFO:     Uvicorn running on http://0.0.0.0:30000
```

Run the same three test requests as above. Then compare:

```python
# Run this comparison script on your local machine (not the Vast.ai instance)
# It measures first-request latency vs third-request latency for each engine

import requests, time

ENDPOINT = "http://<vast-ai-ip>:30000/v1/chat/completions"
SYSTEM = "You are an SRE. Analyze Kubernetes incidents and classify severity P1-P4."
MESSAGES = [
    "pod OOMKilled exit code 137",
    "CrashLoopBackOff 5 times in 10 minutes",
    "node disk pressure eviction",
]

latencies = []
for i, msg in enumerate(MESSAGES, 1):
    start = time.time()
    resp = requests.post(ENDPOINT, json={
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": msg}
        ],
        "max_tokens": 100
    })
    elapsed = (time.time() - start) * 1000
    latencies.append(elapsed)
    print(f"Turn {i}: {elapsed:.0f}ms — {resp.json()['choices'][0]['message']['content'][:60]}...")

print(f"\nLatency trend: {[f'{l:.0f}ms' for l in latencies]}")
```

Expected pattern with SGLang (RadixAttention active):
```
Turn 1: 1240ms — OOMKilled pods occur when containers exceed memory limits...
Turn 2:  890ms — CrashLoopBackOff indicates a container that repeatedly...
Turn 3:  820ms — Disk pressure eviction removes pods to free disk space...
Latency trend: ['1240ms', '890ms', '820ms']
```

Expected pattern with vLLM (no RadixAttention by default):
```
Turn 1: 1250ms — OOMKilled pods occur when containers exceed memory limits...
Turn 2: 1240ms — CrashLoopBackOff indicates a container that repeatedly...
Turn 3: 1230ms — Disk pressure eviction removes pods to free disk space...
Latency trend: ['1250ms', '1240ms', '1230ms']
```

SGLang's latency falls on turns 2–3 as the system prompt hits cache. vLLM's latency is flat — every turn recomputes the system prompt KV state. This is the RadixAttention benefit made concrete.

---

## Step 5 — Wire SGLang to AOIS via LiteLLM

Keep SGLang running on the Vast.ai instance. On your local machine, set up SSH port forwarding:

```bash
# Forward remote port 30000 to local port 30000
ssh -N -L 30000:localhost:30000 -p 12345 root@<vast-ai-ip>
# Leave this running in a separate terminal
```

Now test the forwarded port:

```bash
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "meta-llama/Llama-3.1-8B-Instruct", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 10}'
# Expected: {"choices": [{"message": {"content": "Hello! How can I help..."}}]}
```

Add to `.env`:

```bash
SGLANG_URL=http://localhost:30000/v1
```

In `main.py`, add the SGLang tier to `ROUTING_TIERS`:

```python
ROUTING_TIERS = {
    "premium": {
        "model": "claude-sonnet-4-6",
        "cost_per_1k_input_tokens": 0.003,
        "cost_per_1k_output_tokens": 0.015,
    },
    "fast": {
        "model": "groq/llama-3.1-8b-instant",
        "cost_per_1k_input_tokens": 0.00005,
        "cost_per_1k_output_tokens": 0.00008,
    },
    "sglang": {
        "model": "openai/meta-llama/Llama-3.1-8B-Instruct",
        "cost_per_1k_input_tokens": 0.0001,  # back-calculated: $0.25/hr GPU at 80 tok/s
        "cost_per_1k_output_tokens": 0.0001,
    },
}
```

In `analyze()`, add the URL injection for SGLang (same pattern as any self-hosted endpoint):

```python
extra_kwargs = {}
if tier == "sglang":
    sglang_url = os.getenv("SGLANG_URL")
    if not sglang_url:
        raise ValueError("SGLANG_URL not set — start SGLang and set this env var")
    extra_kwargs["api_base"] = sglang_url
```

Test end-to-end:

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "pod/worker-9b4f2 OOMKilled exit code 137, memory limit 256Mi", "tier": "sglang"}'
```

Expected:

```json
{
  "summary": "Worker pod killed by OOM due to memory limit exceeded",
  "severity": "P2",
  "suggested_action": "Increase memory limit in pod spec or investigate memory leak in application code",
  "confidence": 0.82,
  "provider": "openai/meta-llama/Llama-3.1-8B-Instruct",
  "cost_usd": 0.000012
}
```

---

▶ **STOP — do this now**

Run a head-to-head benchmark. This tests the same 4 log samples against the `premium` tier (Claude) and the `sglang` tier:

```bash
python3 test_vllm.py
# This script was committed in v14's original implementation
# Update the tier names to match: "sglang" instead of "vllm"
```

Expected output:

```
============================================================
Tier: premium
============================================================
  [OOMKilled]    ✓ P2  latency: 1243ms  cost: $0.001240
  [CrashLoop]    ✓ P2  latency:  989ms  cost: $0.001180
  [Disk pressure] ✓ P3  latency:  876ms  cost: $0.000890
  [High latency]  ✓ P3  latency: 1102ms  cost: $0.001050

============================================================
Tier: sglang
============================================================
  [OOMKilled]    ✓ P2  latency: 1240ms  cost: $0.000012
  [CrashLoop]    ✓ P2  latency:  890ms  cost: $0.000011
  [Disk pressure] ✓ P3  latency:  820ms  cost: $0.000010
  [High latency]  ✓ P3  latency:  780ms  cost: $0.000009

============================================================
SUMMARY
============================================================
Tier          Avg latency    Total cost   Accuracy
--------------------------------------------------
premium          1053ms       $0.004360      100%
sglang            933ms       $0.000042      100%

SGLang vs Claude:  104x cheaper per call
SGLang vs Groq:    ~2x cheaper at 1,000+ calls/day sustained GPU usage
```

Reading the results: SGLang latency drops below Claude by turn 3 (cache warming). Accuracy is equivalent on P1–P4 classification. At 10,000 P3/P4 calls/day, you save ~$4,300/year over Claude.

---

## Step 6 — Update SEVERITY_TIER_MAP (Condition-Based)

After v13 benchmarking, P3/P4 currently route to Groq (`fast` tier — 0.22s, $0.000001/call). SGLang is the right alternative when you need:

- A custom model (v15 fine-tune, can't run on Groq)
- Data sovereignty (logs stay on your GPU, not Groq's servers)
- Volume that justifies sustained GPU rental (>3,000 P3/P4 calls/day)

Switch P3/P4 to SGLang only when one of those conditions applies:

```python
# Current (after v13 benchmarking)
SEVERITY_TIER_MAP = {
    "P1": "premium",
    "P2": "premium",
    "P3": "fast",    # Groq — 220ms, $0.000001/call, best for latency
    "P4": "fast",
}

# Switch to SGLang when you need self-hosted (fine-tuned model, data sovereignty, high volume)
SEVERITY_TIER_MAP = {
    "P1": "premium",
    "P2": "premium",
    "P3": "sglang",  # self-hosted Llama-3.1-8B — no per-call API cost, GPU time only
    "P4": "sglang",
}
```

---

▶ **STOP — do this now**

Calculate the break-even. Open Python:

```python
# Scenario: 10,000 P3/P4 log analyses per day
calls_per_day = 10_000

claude_cost  = calls_per_day * 0.001200   # average Claude premium
groq_cost    = calls_per_day * 0.000001   # Groq Llama-3.1-8B
sglang_cost  = 24 * 0.25                  # Vast.ai RTX 3090 @ $0.25/hr, 24hr rental

print(f"Claude premium/day:  ${claude_cost:.2f}")
print(f"Groq fast/day:       ${groq_cost:.2f}")
print(f"SGLang/day (GPU rental): ${sglang_cost:.2f}")
print(f"Groq crossover: {sglang_cost/0.000001:.0f} calls/day")
print(f"Claude crossover: {sglang_cost/0.001200:.0f} calls/day")
```

Expected output:

```
Claude premium/day:  $12.00
Groq fast/day:       $0.01
SGLang/day (GPU rental): $6.00

Groq crossover: 6,000,000 calls/day
Claude crossover: 5,000 calls/day
```

**The insight:** Groq stays cheaper than self-hosted SGLang unless you're running >6M calls/day. SGLang wins over Claude at >5,000 calls/day. The reason to choose SGLang over Groq is not cost — it is model control (fine-tuning, v15) and data sovereignty. Never self-host to save money at AOIS's scale; self-host to run your own model.

---

## Quantization: Fitting Larger Models in Less VRAM

Llama-3.1-8B in the default fp16 format uses ~16GB VRAM. The RTX 3090 has 24GB — it fits. But a 13B model in fp16 uses ~26GB and will not fit. Quantization reduces model weight precision to shrink the footprint.

| Format | Precision | VRAM (8B model) | Quality impact |
|--------|-----------|-----------------|----------------|
| fp16 | 16-bit float | ~16GB | Baseline |
| int8 | 8-bit integer | ~8GB | <1% degradation |
| int4 (AWQ) | 4-bit integer | ~4GB | 1–3% degradation |
| int4 (GPTQ) | 4-bit integer | ~4GB | 1–4% degradation |

AWQ (Activation-aware Weight Quantization) and GPTQ are supported natively in both SGLang and vLLM.

To serve a pre-quantized AWQ model (allows 13B on 24GB VRAM):

```bash
# SGLang with AWQ quantization
python -m sglang.launch_server \
  --model-path TheBloke/Llama-2-13B-chat-AWQ \
  --host 0.0.0.0 \
  --port 30000 \
  --mem-fraction-static 0.85 \
  --quantization awq

# vLLM with AWQ quantization
vllm serve TheBloke/Llama-2-13B-chat-AWQ \
  --quantization awq \
  --gpu-memory-utilization 0.85
```

The production rule: for 8B models on RTX 3090, fp16 is fine. For 13B+ or when running on smaller GPUs (T4: 16GB, L4: 24GB), use AWQ. For maximum throughput on high-volume P4 logs, AWQ on a smaller GPU costs less than fp16 on a larger one.

---

## Understanding Throughput vs Latency

These are different axes. The distinction matters at production scale.

**Latency**: time for one request to complete. SGLang warm: ~800–2000ms. Groq: 100–300ms. For a single call, Groq wins.

**Throughput**: requests per second the system can handle before queuing. SGLang with 32 concurrent requests and RadixAttention can process all 32 simultaneously with shared KV cache. At 32 concurrent users, SGLang's effective throughput exceeds Groq's API rate limits.

The tradeoff:
- **Interactive, real-time** (human watching a dashboard): Groq wins — 200ms per-call latency matters
- **Background processing, high volume** (batch log analysis): SGLang wins — throughput and cost matter
- **Critical incidents** (P1/P2): Claude wins — quality is non-negotiable, cost is secondary

AOIS auto-routes by severity, which maps naturally to these profiles:
- P1/P2 = human waiting for response → Claude
- P3/P4 = background batch analysis → Groq (or SGLang for self-hosted models)

---

## The Inference Hardware Race

After v14, you are using an NVIDIA GPU with SGLang. You should understand what that GPU competes against.

**NVIDIA GPU (RTX 3090, A10, A100, H100)**

NVIDIA is the default for self-hosted inference. The RTX 3090 has 24GB VRAM, and the A100 (80GB) handles 70B models. The H100 achieves 4× the A100's throughput for transformer workloads via the transformer engine and FP8 support.

SGLang and vLLM were built for NVIDIA GPUs. PagedAttention and RadixAttention map directly to how CUDA manages memory. For self-hosted inference, NVIDIA is the safe choice.

**Groq LPU (Language Processing Unit)**

Groq is not a GPU. It is a custom ASIC designed specifically for transformer inference — a deterministic dataflow chip with no caches and no memory bandwidth bottleneck. The result: sub-100ms inference for 7B–70B models.

Why Groq exists: GPUs are general-purpose. A chip designed only for the transformer attention pattern will beat a GPU on per-request latency. Groq proved it. The limit: you cannot run custom models, and rate limits apply under high concurrent load.

**Cerebras WSE (Wafer Scale Engine)**

The largest chip ever made — the entire wafer is one chip. 900,000 AI cores and 44GB of SRAM on-die. No memory bandwidth bottleneck. Result: 70B models at 800+ tokens/second (versus ~40 tokens/sec on A100). Available as an API (inference.cerebras.ai), not self-hosted.

**Where each wins:**

| Scenario | Winner | Why |
|----------|--------|-----|
| Sub-100ms single-user latency | Groq | Deterministic ASIC |
| 70B+ model, fastest possible | Cerebras | Wafer-scale on-chip SRAM |
| High-volume batch, custom model | NVIDIA + SGLang/vLLM | You own the weights |
| Fine-tuned model deployment | NVIDIA + SGLang/vLLM | Groq/Cerebras don't accept custom weights |
| Cost at high throughput, model control | NVIDIA + SGLang/vLLM | Amortized GPU cost + full control |
| Air-gapped / compliance | NVIDIA + SGLang/vLLM | No external API |

---

## NVIDIA Dynamo: Single-Node Demo

Now that you understand SGLang and vLLM, you are ready to understand Dynamo — the layer above them.

Dynamo wraps SGLang or vLLM as its execution backend and adds the orchestration layer: disaggregated prefill/decode, KV cache-aware routing, and NIXL-based KV migration between nodes.

**Install Dynamo:**

```bash
# On your Vast.ai instance
pip install "ai-dynamo[vllm]>=0.1.0"

# Verify
python3 -c "import dynamo; print(dynamo.__version__)"
# Expected: 0.1.x or later
```

**Single-node configuration file:**

```yaml
# dynamo_single_node.yaml
# Single GPU demo: one router + one vLLM worker
version: "1.0"

router:
  port: 8080
  type: round_robin      # KV-aware routing requires multiple workers to show benefit

workers:
  - name: worker-0
    backend: vllm
    model: meta-llama/Llama-3.1-8B-Instruct
    gpu_memory_utilization: 0.85
    port: 8001
```

**Start Dynamo:**

```bash
dynamo serve --config dynamo_single_node.yaml
```

Expected output:

```
[Dynamo] Router starting on http://0.0.0.0:8080
[Dynamo] Registering worker worker-0 (vLLM backend, port 8001)
[Dynamo] KV cache metadata tracking: enabled
[Dynamo] NIXL interconnect: not available (single node — expected)
[Dynamo] Ready. Route requests to http://localhost:8080/v1/chat/completions
```

Query through the Dynamo router:

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "messages": [{"role": "user", "content": "pod OOMKilled, classify severity"}],
    "max_tokens": 100
  }'
# Expected: same OpenAI-compatible response — Dynamo is transparent to the caller
```

Check what Dynamo tracks:

```bash
curl http://localhost:8080/metrics
# Expected output includes:
# dynamo_requests_total{worker="worker-0"} 1.0
# dynamo_kv_cache_hits_total 0.0          # 0 on single node — expected
# dynamo_request_duration_seconds_bucket ...
```

On a single node, `dynamo_kv_cache_hits_total` stays at 0 — there is only one worker and it manages its own KV cache internally. KV-aware routing only fires when a request can be sent to the worker that already holds the relevant KV state, which requires multiple workers.

---

▶ **STOP — do this now**

Work through the Dynamo architecture exercise. Open a second terminal window and look at both the Dynamo router log and the vLLM worker log simultaneously while sending requests:

```bash
# Terminal 1: watch Dynamo router
dynamo serve --config dynamo_single_node.yaml

# Terminal 2: watch the vLLM worker logs (Dynamo starts it as a subprocess)
# The worker port is 8001 as configured above
curl http://localhost:8001/metrics 2>/dev/null | grep -E "request|kv_cache" | head -10

# Terminal 3: send 5 requests
for i in $(seq 1 5); do
  curl -s http://localhost:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "meta-llama/Llama-3.1-8B-Instruct",
         "messages": [{"role": "user", "content": "classify severity: pod OOMKilled"}],
         "max_tokens": 50}' > /dev/null
done

# Check Dynamo routing stats
curl http://localhost:8080/metrics | grep dynamo_
```

Expected:
```
dynamo_requests_total{worker="worker-0"} 5.0
dynamo_kv_cache_hits_total 0.0
dynamo_worker_queue_depth{worker="worker-0"} 0.0
```

All 5 requests went to `worker-0` (only worker). No KV cache hits because there is only one worker. Now answer: what would the routing look like with 3 workers and an incoming second turn of a conversation that already processed turn 1 on worker-1? (Answer: the router would check which worker holds the KV state from turn 1 and send turn 2 to that same worker — `dynamo_kv_cache_hits_total` increments.)

This is the mental model that matters. The single-node demo exists to show you the architecture before you encounter it at scale.

**When you would actually use Dynamo:** once AOIS is handling thousands of concurrent investigations across a fleet of GPU nodes — Hetzner GEX44s, AWS p3 instances, or Vast.ai multi-GPU — Dynamo is the routing layer that makes that fleet behave as one coherent inference pool.

---

## Common Mistakes

**Mistake 1: Starting both SGLang and vLLM simultaneously**

Trigger it: start SGLang, then start vLLM on a different port without stopping SGLang:

```bash
python -m sglang.launch_server --port 30000 &
vllm serve meta-llama/Llama-3.1-8B-Instruct --port 30001
```

You will see:
```
torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 14.00 GiB
  (GPU 0; 22.08 GiB total capacity; 20.50 GiB already allocated)
```

Both engines try to load the model into VRAM simultaneously. With only 24GB, there is not enough for two copies of an 8B model.

Fix: stop SGLang before starting vLLM. Use one inference engine at a time per GPU.

**Mistake 2: Setting `--mem-fraction-static` too high**

Trigger it: set `--mem-fraction-static 0.97` in SGLang:

```bash
python -m sglang.launch_server --model-path meta-llama/Llama-3.1-8B-Instruct --mem-fraction-static 0.97
```

You will see the server crash during initialization:
```
RuntimeError: CUDA error: out of memory
sglang: KV cache allocation failed. 
  Requested: 23116MiB, Available: 22190MiB
  Reduce --mem-fraction-static and retry.
```

SGLang tries to reserve 97% of VRAM for KV cache. The model itself (fp16 weights) already occupies ~16GB. With 24GB total, there is only ~8GB left for KV cache — but SGLang tried to grab 23GB.

Fix: set `--mem-fraction-static 0.80` to 0.85. This gives the model weights room to load and leaves KV cache space proportional to available VRAM after weights.

**Mistake 3: SSH port forward dies mid-session**

Trigger it: let your local laptop go to sleep while the port forward is running:

```bash
curl http://localhost:30000/v1/chat/completions \
  -d '{"model": "meta-llama/Llama-3.1-8B-Instruct", "messages": [{"role": "user", "content": "test"}], "max_tokens": 10}'
# After laptop sleep/wake:
```

You will see:
```
curl: (7) Failed to connect to localhost port 30000: Connection refused
```

Or in Python:
```
requests.exceptions.ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
```

Fix: restart the SSH port forward:
```bash
ssh -N -L 30000:localhost:30000 -p 12345 root@<vast-ai-ip>
```

For persistent sessions, use `autossh` or add `ServerAliveInterval 60` to your SSH config.

**Mistake 4: Forgetting `openai/` prefix in LiteLLM model name**

Trigger it: remove the `openai/` prefix from the model name in `ROUTING_TIERS`:

```python
# Wrong:
"model": "meta-llama/Llama-3.1-8B-Instruct"
```

Send a request via AOIS. You will see:
```
LiteLLM Error: No model 'meta-llama/Llama-3.1-8B-Instruct' in provider map.
  Use 'openai/meta-llama/Llama-3.1-8B-Instruct' with api_base for custom endpoints.
```

LiteLLM uses the prefix to select the OpenAI-compatible adapter. Without `openai/`, it does not know how to handle the model name.

Fix: restore the `openai/` prefix: `"openai/meta-llama/Llama-3.1-8B-Instruct"`.

**Mistake 5: Forgetting `api_base` in the extra_kwargs**

Trigger it: set `SGLANG_URL` correctly but forget to pass it in `extra_kwargs`:

```bash
SGLANG_URL="" python3 -c "
import requests
r = requests.post('http://localhost:8000/analyze',
  json={'log': 'pod OOMKilled', 'tier': 'sglang'})
print(r.json())
"
```

You will see:
```
ValueError: SGLANG_URL not set — start SGLang and set this env var
```

Or if the env var is set but `extra_kwargs["api_base"]` is not passed to LiteLLM:
```
openai.AuthenticationError: No API key provided.
# LiteLLM sent the request to api.openai.com instead of your SGLang instance
```

Fix: confirm that `analyze()` checks `tier == "sglang"` and passes `api_base` in `extra_kwargs`.

---

## Troubleshooting

**Error: `Connection refused` on port 30000 immediately after starting SGLang**
```bash
# SGLang takes 20–45 seconds to load the model into VRAM
# Watch for the ready message before sending requests:
python -m sglang.launch_server ... 2>&1 | grep -E "started|ready|error"
# Wait for: [SGLang] Server started on http://0.0.0.0:30000
```

**Error: `Model not found` on HuggingFace during model download**
```bash
# Check if the model requires authentication
huggingface-cli login
# Enter your HF token from hf.co/settings/tokens
# For gated models (Llama-3.x), accept the license at hf.co/<model-id>
```

**Error: Instructor `ValidationError` on SGLang responses**

Llama-3.1-8B can produce less reliable JSON compared to Claude. Instructor retries automatically (`max_retries=2`). If failures persist:

```python
# Add a system prompt reinforcement for the sglang tier in analyze():
if tier == "sglang":
    system_prompt += "\n\nIMPORTANT: Always respond using the analyze_incident tool. Your response must be valid JSON."
```

**SGLang `prefix_cache_hit_rate` is 0.0 after multiple requests**

The cache starts cold — the first request always misses. If hit rate stays at 0 after 5+ requests with the same system prompt:

```bash
# Check if RadixAttention is actually enabled
curl http://localhost:30000/get_server_info | python3 -m json.tool | grep -i cache
# Expected: "radix_cache": true, "prefix_cache_hit_rate": > 0.0
# If radix_cache is false: SGLang version may not support it — upgrade to 0.4.0+
```

**Vast.ai instance shows CUDA driver mismatch**
```bash
nvidia-smi  # check CUDA version
python3 -c "import torch; print(torch.version.cuda)"
# If mismatch: reinstall PyTorch with matching CUDA version
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

---

## Connection to Later Phases

**v15 (next):** You will fine-tune a TinyLlama model on AOIS SRE log data using LoRA. The fine-tuned model is deployed on Modal (one-shot fine-tune job = Modal's right use case). After v15, you can serve the fine-tuned weights with SGLang via `--lora-paths` — same infrastructure, custom model weights.

```python
# v15 preview: serving a fine-tuned LoRA adapter with SGLang
python -m sglang.launch_server \
  --model-path meta-llama/Llama-3.1-8B-Instruct \
  --lora-paths aois-sre-lora=/path/to/lora/adapter \
  --port 30000
# The caller specifies: "lora_name": "aois-sre-lora" per request
```

**v16 (observability):** You will add OpenTelemetry spans to `analyze()`. Every tier — including SGLang — will emit latency, cost, and cache hit metrics to Grafana. SGLang's `/get_server_info` prefix cache hit rate becomes a Prometheus metric.

**v17 (Kafka):** AOIS consumes logs from Kafka and analyzes in real-time. At high consumer lag, KEDA scales AOIS pods. The SGLang endpoint handles the burst — RadixAttention batches concurrent multi-turn requests efficiently. The infrastructure you are building here is what makes that scale possible.

**v23 (LangGraph):** The 6-node SRE investigation loop sends 10–15 sequential tool calls to the LLM. SGLang's RadixAttention reuses the shared system prompt + incident context KV cache across every turn. You will see the cache hit rate in v16's Grafana dashboard — a direct measurement of the RadixAttention benefit in production.

**v34.5 (capstone):** Multi-node Dynamo is referenced in the game day scenario. When AOIS is handling hundreds of concurrent investigations, the routing layer above vLLM/SGLang is Dynamo. The mental model built here is what makes that section click.

---

## Mastery Checkpoint

Complete these before moving to v15:

1. You have a Vast.ai account and have rented a GPU. SGLang serves Llama-3.1-8B at port 30000. Direct curl returns a valid response.

2. `curl http://localhost:30000/get_server_info` shows `prefix_cache_hit_rate > 0.5` after running 5 consecutive requests with the same system prompt.

3. AOIS routes the `sglang` tier successfully. `curl localhost:8000/analyze -d '{"log": "...", "tier": "sglang"}'` returns a valid `IncidentAnalysis` with `provider` showing the Llama model.

4. You ran vLLM serving the same model and compared latency curves. SGLang latency dropped on turns 2–3; vLLM latency stayed flat. You can explain why in one sentence.

5. You can explain the Groq break-even: for pure cost savings, self-hosted SGLang never beats Groq at AOIS's scale. The reason to choose SGLang over Groq is model control — fine-tuning, data sovereignty, or running a model Groq does not offer.

6. You know the two knobs that control inference throughput: `--mem-fraction-static` (KV cache size in VRAM) and concurrent request concurrency (SGLang handles this automatically with RadixAttention).

7. You can explain what Dynamo adds above SGLang: disaggregated prefill/decode, KV cache-aware routing across multiple workers, and NIXL-based KV migration. And you know the single-GPU limitation: KV-aware routing requires ≥2 workers to show benefit.

8. Name the inference engine for each scenario: (a) AOIS LangGraph 10-step investigation, 8B model; (b) single-turn high-concurrency summarization API at 500 RPS; (c) P1 critical incident requiring best reasoning; (d) a fleet of 8 GPU workers needing smart KV routing. Justify each without notes.

9. You know why Modal was the wrong platform for v14: cold starts (30–120s), A10G at $1.98/hr vs RTX 3090 at $0.25/hr on Vast.ai, and dependency conflicts in vLLM 0.4.x–0.8.x made persistent serving unreliable. Modal's right use case is one-shot GPU jobs (v15 fine-tuning), not persistent inference servers.

**The mastery bar:** you understand self-hosted inference from first principles — vLLM's PagedAttention for concurrent batching, SGLang's RadixAttention for multi-turn agents, Dynamo's orchestration layer for fleet routing, and the economics that decide between managed APIs vs self-hosted GPU. You can route AOIS to any of them via LiteLLM without changing application code.

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### vLLM

| Layer | |
|---|---|
| **Plain English** | An open-source server for running large language models that uses smarter memory management to serve many requests simultaneously — turning a single GPU into a high-throughput inference engine. |
| **System Role** | vLLM is AOIS's self-hosted open-source inference engine option. It exposes an OpenAI-compatible endpoint, routed to via LiteLLM. The case for vLLM over managed APIs: once deployed, marginal inference cost is GPU rental time only — no per-token API charges. The case for vLLM over SGLang: better for high-concurrency single-turn workloads where shared prefix reuse does not apply. |
| **Technical** | vLLM uses PagedAttention — KV cache stored in non-contiguous memory pages, allocated on demand, shared across requests using copy-on-write. This eliminates KV cache fragmentation and enables continuous batching: new requests join mid-batch instead of waiting for the current batch to finish. Result: 2–24× higher throughput vs naive HuggingFace `pipeline()` inference. Served via `vllm serve` as an OpenAI-compatible HTTP server. |
| **Remove it** | Without vLLM, self-hosted inference uses HuggingFace `pipeline()` (single-threaded, no batching, 1/10th the throughput) or Triton (full control but requires manual batching configuration). vLLM is the standard for production open-source model serving — used at Mistral, scale-AI, and most inference-at-scale organisations as the internal engine. |

**Say it at three levels:**
- *Non-technical:* "vLLM is a smarter way to share a GPU. Instead of one user waiting for the previous one to finish, vLLM figures out how to run multiple requests at the same time on the same hardware."
- *Junior engineer:* "`vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8000`. Starts an OpenAI-compatible server. LiteLLM routes to it with `openai/llama-3.1-8b-instruct` and `api_base=http://localhost:8000/v1`. PagedAttention means the GPU does not pre-allocate max-sequence-length KV cache for every request — memory is used only as tokens are generated."
- *Senior engineer:* "PagedAttention's real benefit manifests at high concurrency — 50+ simultaneous requests. For AOIS's typical load (1–10 concurrent), the throughput advantage narrows. The production decision: vLLM for batch/high-concurrency single-turn; SGLang for multi-turn agents (RadixAttention); NIM when you want NVIDIA's managed operational simplicity. INT4 AWQ quantization cuts VRAM ~4× with ~5% benchmark degradation — real-world quality loss is task-dependent, always eval before deploying quantized models to production tiers."

---

### SGLang

| Layer | |
|---|---|
| **Plain English** | A smarter inference server built specifically for agents. Instead of recomputing the same context on every turn of a conversation, SGLang remembers the parts that did not change — so multi-step agent investigations get faster after the first turn, not slower. |
| **System Role** | SGLang is AOIS's primary self-hosted inference engine for agent workloads. It exposes an OpenAI-compatible endpoint that LiteLLM routes to identically to vLLM. For AOIS's LangGraph investigations (6-node loop, 10–15 tool calls), SGLang's RadixAttention reuses the shared system prompt KV cache across all turns — 60–80% fewer tokens recomputed per turn after the first. |
| **Technical** | SGLang (UC Berkeley Sky Computing Lab, spun out as RadixArk January 2026, deployed on 400,000+ GPUs) implements RadixAttention: a radix tree stores all cached key-value states as shared prefix paths. When a new request arrives, the longest matching prefix is found and reused. Only novel tokens are computed. TGI (HuggingFace Text Generation Inference) entered maintenance mode December 2025 — dead for new projects. SGLang is the de facto agentic inference standard. |
| **Remove it** | Without SGLang: use vLLM (adequate for single-turn, less optimal for agents), TensorRT-LLM (best throughput but NVIDIA-only and operationally heavier), or managed APIs at higher per-token cost. For AOIS's multi-turn LangGraph workloads, removing SGLang means higher GPU compute cost per investigation turn and higher latency by turn 3+. |

**Say it at three levels:**
- *Non-technical:* "SGLang is an AI inference server that remembers context between turns of a conversation. Instead of re-reading everything from the start on each reply, it picks up where it left off — getting faster as the conversation continues."
- *Junior engineer:* "`python -m sglang.launch_server --model-path meta-llama/Llama-3.1-8B-Instruct --port 30000`. RadixAttention is on by default — no flags needed. LiteLLM routes to it with `api_base=http://localhost:30000/v1`. Check cache hit rate at `/get_server_info`. For multi-turn agents expect 80%+ hit rate after the first request."
- *Senior engineer:* "RadixAttention's radix tree stores KV states indexed by token prefix. The tree is shared across all in-flight requests — a new multi-turn request that shares a prefix with a completed request reuses its KV without explicit session management. The operational tradeoff vs vLLM: SGLang's tree management adds memory overhead, and eviction under memory pressure requires tuning `--mem-fraction-static`. At low concurrency with long shared prefixes (AOIS's profile), RadixAttention dominates. At high concurrency with diverse prompts, the tree fragments and the benefit narrows — measure before committing."

---

### NVIDIA Dynamo

| Layer | |
|---|---|
| **Plain English** | A traffic controller for a fleet of GPU servers. When dozens of GPU machines are running inference, Dynamo decides which server handles each request — sending it to the one that already has the right context in memory, so no computation is repeated across the fleet. |
| **System Role** | Dynamo sits above SGLang or vLLM as an orchestration layer. In a multi-GPU AOIS deployment, Dynamo routes investigation requests to the worker that already holds the KV cache for that incident's context. On a single GPU (v14), you see the architecture — the full benefit (KV-aware routing, NIXL migration) requires ≥2 GPU workers. |
| **Technical** | Released by NVIDIA at GTC 2026 as open source. Key mechanisms: (1) Disaggregated prefill/decode — compute-bound input processing and memory-bandwidth-bound token generation run on separate hardware. (2) KV cache-aware routing — the router tracks which worker holds which KV state and routes follow-on turns to the same worker. (3) NIXL (NVIDIA Interconnect Library) — transfers KV cache blocks between nodes via NVLink or InfiniBand without recomputation. Backends: vLLM, SGLang, or TensorRT-LLM — Dynamo orchestrates, it does not replace. |
| **Remove it** | Without Dynamo at fleet scale: each GPU worker manages its own KV cache in isolation. A multi-turn request landing on a different worker than turn 1 recomputes all prior context from scratch. At 8+ GPU workers, the repeated KV computation becomes significant. For AOIS's current single-GPU deployment, removing Dynamo has zero impact — it becomes relevant when AOIS scales to handling thousands of concurrent investigations across a GPU cluster. |

**Say it at three levels:**
- *Non-technical:* "Dynamo is like an air traffic controller for AI servers. When you have many AI servers working together, Dynamo decides who handles each request — specifically choosing the server that already knows the history of that conversation, so it doesn't start over."
- *Junior engineer:* "`pip install ai-dynamo[vllm]`. Write a YAML config listing your workers. `dynamo serve --config config.yaml`. Requests hit the Dynamo router at port 8080, which routes them to the appropriate vLLM/SGLang worker. On a single node, routing is round-robin — the KV-aware routing benefit requires multiple workers with overlapping request patterns."
- *Senior engineer:* "Dynamo's disaggregated prefill/decode changes the hardware economics: prefill nodes need high FLOPs (H100 class), decode nodes need high memory bandwidth (A10 class). The ratio of prefill to decode nodes is workload-dependent — long prompts/short outputs shift toward prefill-heavy; short prompts/long outputs shift toward decode-heavy. NIXL's KV migration adds network latency for the transfer — the break-even is when recomputation cost > migration cost. For 8B models, the crossover is at context lengths >2K tokens or when the same context is reused across >3 requests from different workers."
