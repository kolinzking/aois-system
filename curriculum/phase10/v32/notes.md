# v32 — Edge AI with Ollama: Air-Gapped AOIS

⏱ **Estimated time: 4–5 hours**

---

## Prerequisites

v31 multimodal complete. Ollama installed and running.

```bash
# Verify Ollama is installed
ollama --version
# ollama version 0.x.x

# Verify Ollama is running
ollama list
# NAME                    ID              SIZE    MODIFIED
# (list of pulled models or empty)

# Pull the model used in this version
ollama pull llama3.2:3b
# pulling manifest...
# pulling...
# success

# Verify the model responds
ollama run llama3.2:3b "Classify: OOMKilled pod, one word: P1, P2, P3, or P4"
# P1
```

If `ollama` is not found: install from https://ollama.ai. On Linux: `curl -fsSL https://ollama.ai/install.sh | sh`. The install script adds `ollama` to PATH and creates a systemd service.

---

## Learning Goals

By the end you will be able to:

- Run AOIS locally with Ollama as the LLM backend — no internet, no API costs
- Explain the three real-world use cases that make air-gapped operation necessary
- Implement the edge node: analyze offline with Ollama, queue results, sync to central when online
- Configure LiteLLM to route to Ollama using the same interface as cloud models
- Benchmark Ollama latency and JSON compliance against Claude — know exactly where open models win and lose
- Operate the offline queue safely: partial syncs, atomic clears, and connectivity detection

---

## Why Edge AI Is Not Optional for Some Deployments

Three scenarios where AOIS must operate without internet — and in each case, without edge AI, incident analysis stops entirely.

**Scenario 1 — Regulated environments**: a major bank's Kubernetes cluster runs the payment processing pipeline. Legal counsel has confirmed that log data describing transaction failures cannot be sent to an external API — it is considered transaction metadata and falls under data residency requirements. All AI analysis must run on-premises. Without Ollama, AOIS cannot operate in this environment at all.

**Scenario 2 — Field deployments**: AOIS is deployed on a k3s cluster at a remote manufacturing facility with a satellite internet connection. During a production line incident at 2am, the satellite link goes down (common during weather events). The incident keeps generating log events. The on-call engineer needs AOIS to keep analyzing. With Ollama running locally, AOIS continues — the results queue locally and sync to the central cluster when connectivity is restored.

**Scenario 3 — Cost-zero development**: a team is developing a new AOIS integration. Every test request to Claude costs $0.002–$0.016. Running 500 tests during development costs $10–$8. With Ollama routing all development traffic locally, the cost is $0. The model is less capable, but for validating API plumbing and testing the code path, it is sufficient.

---

## Ollama's OpenAI-Compatible API

Ollama serves any downloaded model via an HTTP API at `localhost:11434`. The API is OpenAI-compatible, which means LiteLLM can route to it using the `ollama/` prefix — no custom code required.

```bash
# Ollama's native API (direct, no LiteLLM)
curl http://localhost:11434/api/generate \
  -d '{"model": "llama3.2:3b", "prompt": "Classify: OOMKilled pod. Return JSON: {\"severity\": \"P1\"}", "stream": false}'

# Expected response structure:
# {"model":"llama3.2:3b","created_at":"...","response":"{\"severity\":\"P1\"}","done":true}
```

```python
# Via LiteLLM (same interface as cloud models)
import litellm

response = litellm.completion(
    model="ollama/llama3.2:3b",
    messages=[{"role": "user", "content": "Classify: OOMKilled pod. Return JSON: {\"severity\": \"P1\"}"}],
    api_base="http://localhost:11434",
)
print(response.choices[0].message.content)
# {"severity": "P1"}  (70-85% of the time — open model JSON compliance)
```

The `api_base` parameter tells LiteLLM where to send requests. When running on the same machine as Ollama, it is always `http://localhost:11434`. On an edge node calling a remote Ollama instance, it would be `http://edge-host:11434`.

---

## ▶ STOP — do this now

Run AOIS's classify logic against Ollama directly, before wiring it into the routing tiers:

```python
import litellm, json, re

def classify_with_ollama(incident: str) -> dict:
    response = litellm.completion(
        model="ollama/llama3.2:3b",
        messages=[{"role": "user", "content": (
            f"SRE incident: {incident}\n"
            f"Classify severity P1-P4.\n"
            f'Return JSON only: {{"severity": "P1", "reason": "brief explanation"}}'
        )}],
        api_base="http://localhost:11434",
        timeout=60,
    )
    text = response.choices[0].message.content
    try:
        return json.loads(re.search(r'\{[^{}]+\}', text, re.DOTALL).group())
    except Exception:
        return {"severity": "P3", "reason": "parse_failed", "raw": text[:200]}

test_cases = [
    "auth-service OOMKilled exit code 137 — pods not restarting",
    "disk usage 91% on node-3 — approaching limit",
    "cert expiry in 72 hours for payments.api.internal",
    "CPU usage 45% — normal operation",
]

for case in test_cases:
    result = classify_with_ollama(case)
    print(f"[{result.get('severity', '?')}] {case[:60]}")
    if "raw" in result:
        print(f"  ↳ JSON parse failed: {result['raw'][:80]}")
```

Expected:
```
[P1] auth-service OOMKilled exit code 137 — pods not restarting
[P2] disk usage 91% on node-3 — approaching limit
[P3] cert expiry in 72 hours for payments.api.internal
[P4] CPU usage 45% — normal operation
```

You will likely see 1–2 JSON parse failures in the first run. This is the open model JSON compliance gap — llama3.2:3b adds text around the JSON more often than Claude. The fix is in the retry section below.

---

## Adding Ollama to the LiteLLM Routing Tiers

In `main.py`, add Ollama as the `local` tier:

```python
ROUTING_TIERS = {
    "premium": {
        "model": "claude-sonnet-4-6",
        "description": "Claude Sonnet — highest accuracy, P1/P2",
    },
    "fast": {
        "model": "groq/llama-3.1-8b-instant",
        "description": "Groq — sub-250ms, P3/P4 volume",
    },
    "local": {
        "model": "ollama/llama3.2:3b",
        "api_base": "http://localhost:11434",
        "description": "Ollama — air-gapped, zero cost, development",
    },
}

# Severity-based tier selection
def select_tier(severity: str, aois_mode: str = "cloud") -> str:
    if aois_mode == "edge":
        return "local"  # always use Ollama in edge mode
    return "premium" if severity in ("P1", "P2") else "fast"
```

The `AOIS_MODE=edge` environment variable forces all classification through Ollama, regardless of severity. This is the switch that makes the whole system work offline.

---

## The Edge Node Architecture

The edge AOIS instance operates in three states:

```
State 1: ONLINE
  Log event → analyze_local() (Ollama) → queue_for_sync() → sync_to_central() immediately
  (if connectivity check passes, sync immediately instead of queuing)

State 2: OFFLINE
  Log event → analyze_local() (Ollama) → queue_for_sync() → persist to JSONL file
  (incident analyzed locally; result waits for connectivity)

State 3: RECONNECTING
  sync_to_central() drains the queue → central cluster receives all offline analyses
  Queue file deleted on full sync; truncated on partial sync
```

```python
# edge/edge_aois.py
"""AOIS edge node — analyzes offline with Ollama, syncs to central when online."""
import asyncio, httpx, json, logging, os, time
from pathlib import Path

log = logging.getLogger("aois.edge")

CENTRAL_SYNC_URL = os.getenv("AOIS_CENTRAL_URL", "")
LOCAL_QUEUE_PATH = Path(os.getenv("AOIS_QUEUE_PATH", "/var/aois/offline_queue.jsonl"))
LOCAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


async def analyze_local(incident: str) -> dict:
    """Analyze using local Ollama — works without internet."""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": (
                        f"SRE incident: {incident}\n"
                        f"Classify severity P1-P4 and propose one remediation action.\n"
                        f'Return JSON: {{"severity":"P1","proposed_action":"...","confidence":0.8}}'
                    ),
                    "stream": False,
                    "format": "json",  # Ollama JSON mode — increases compliance
                },
            )
            data = resp.json()
            result = json.loads(data.get("response", "{}"))
            return {**result, "model": f"ollama/{OLLAMA_MODEL}", "source": "edge"}
        except Exception as e:
            log.error("Ollama analysis failed: %s", e)
            return {
                "severity": "P3",
                "proposed_action": "manual review — Ollama unavailable",
                "confidence": 0.0,
                "source": "edge_fallback",
            }
```

The `"format": "json"` parameter instructs Ollama to enforce JSON output at the model level — this improves JSON compliance from ~70% to ~85% for llama3.2:3b. It is not 100% (Claude is 99%+), but it meaningfully reduces parse failures.

---

## The Offline Queue

The offline queue is a JSONL file — one JSON object per line. JSONL is chosen deliberately:

- **Append-safe**: each write is a single `f.write(json.dumps(entry) + "\n")` — atomic at the OS level for lines under 4KB
- **Streaming-parseable**: process one entry at a time without loading the full file into memory
- **Human-readable**: an operator can inspect the queue with `cat /var/aois/offline_queue.jsonl | jq .`
- **Partial-sync safe**: after a partial sync, remove synced lines and rewrite only unsynced lines

```python
async def queue_for_sync(incident: str, local_result: dict) -> None:
    entry = {
        "timestamp": time.time(),
        "incident": incident,
        "local_result": local_result,
    }
    with open(LOCAL_QUEUE_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    log.info("Queued for sync: %s", incident[:60])


async def sync_to_central() -> int:
    """Drain the offline queue to central AOIS. Returns number of synced entries."""
    if not CENTRAL_SYNC_URL:
        log.warning("AOIS_CENTRAL_URL not set — cannot sync")
        return 0

    if not LOCAL_QUEUE_PATH.exists():
        return 0

    raw = LOCAL_QUEUE_PATH.read_text().strip()
    if not raw:
        return 0

    queue = [line for line in raw.split("\n") if line.strip()]
    synced = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for line in queue:
            try:
                entry = json.loads(line)
                await client.post(f"{CENTRAL_SYNC_URL}/api/edge_sync", json=entry)
                synced += 1
            except Exception as e:
                log.warning("Sync failed at entry %d: %s", synced + 1, e)
                break  # stop on first failure — connectivity may be lost again

    if synced == len(queue):
        LOCAL_QUEUE_PATH.unlink()
        log.info("Sync complete — %d entries uploaded, queue cleared", synced)
    else:
        # Rewrite only the unsynced tail — preserve what we couldn't send
        remaining = queue[synced:]
        LOCAL_QUEUE_PATH.write_text("\n".join(remaining) + "\n")
        log.info("Partial sync — %d/%d entries uploaded", synced, len(queue))

    return synced
```

The partial sync logic is important: if the network drops mid-sync, don't lose the entries that weren't uploaded. Rewrite the file with only the unsynced entries. This makes sync idempotent — you can run it repeatedly without losing data.

---

## ▶ STOP — do this now

Run the edge analysis end-to-end and inspect the offline queue:

```python
import asyncio
from edge.edge_aois import edge_analyze, sync_to_central
from pathlib import Path

async def main():
    # Analyze 3 incidents offline
    incidents = [
        "auth-service OOMKilled — offline cluster, edge node",
        "payments-api CrashLoopBackOff exit code 1",
        "disk usage 88% on edge-node-1 /var/lib/containerd",
    ]

    for incident in incidents:
        result = await edge_analyze(incident)
        print(f"[{result.get('severity', '?')}] {incident[:50]}")
        print(f"  action: {result.get('proposed_action', '')[:60]}")
        print(f"  source: {result.get('source', '')}")
        print()

    # Inspect the offline queue
    queue_path = Path("/var/aois/offline_queue.jsonl")
    if queue_path.exists():
        lines = [l for l in queue_path.read_text().split("\n") if l.strip()]
        print(f"Queue contains {len(lines)} entries")
        import json
        for line in lines:
            entry = json.loads(line)
            print(f"  {entry['local_result'].get('severity','?')} | {entry['incident'][:50]}")

asyncio.run(main())
```

Expected output:
```
[P1] auth-service OOMKilled — offline cluster, edge node
  action: kubectl describe pod auth-service-xxx | grep -A5 OOMKilled
  source: edge

[P2] payments-api CrashLoopBackOff exit code 1
  action: kubectl logs payments-api-xxx --previous
  source: edge

[P2] disk usage 88% on edge-node-1 /var/lib/containerd
  action: kubectl exec -it edge-node-1 -- df -h /var/lib/containerd
  source: edge

Queue contains 3 entries
  P1 | auth-service OOMKilled — offline cluster, edge node
  P2 | payments-api CrashLoopBackOff exit code 1
  P2 | disk usage 88% on edge-node-1 /var/lib/containerd
```

Now simulate connectivity returning and syncing:

```python
async def test_sync():
    # Simulate AOIS_CENTRAL_URL set (even if it fails, we see the sync attempt)
    import os
    os.environ["AOIS_CENTRAL_URL"] = "http://localhost:8000"
    synced = await sync_to_central()
    print(f"Synced: {synced} entries")

asyncio.run(test_sync())
```

---

## Benchmarking: Ollama vs Claude

Run this benchmark to record your actual numbers — the table below shows typical values, but your hardware determines Ollama's actual latency.

```python
import asyncio, json, time, re
import litellm

INCIDENTS = [
    "auth-service OOMKilled exit code 137",
    "payments-api CrashLoopBackOff — 50 restarts in 10 minutes",
    "node-3 NotReady — kubelet stopped responding",
    "disk usage 92% on /var/lib/containerd",
    "cert expiry in 48 hours for api.internal",
]

async def benchmark():
    results = {}

    for backend, model, api_base in [
        ("ollama", "ollama/llama3.2:3b", "http://localhost:11434"),
        ("claude", "claude-haiku-4-5-20251001", None),  # Claude for cost comparison
    ]:
        latencies = []
        parse_ok = 0

        for incident in INCIDENTS:
            t0 = time.perf_counter()
            try:
                kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": f"Classify: {incident}. Return JSON: {{\"severity\":\"P1\"}}"}],
                    "max_tokens": 200,
                    "timeout": 90,
                }
                if api_base:
                    kwargs["api_base"] = api_base

                resp = litellm.completion(**kwargs)
                latency = (time.perf_counter() - t0) * 1000
                latencies.append(latency)

                text = resp.choices[0].message.content
                try:
                    json.loads(re.search(r'\{[^{}]+\}', text, re.DOTALL).group())
                    parse_ok += 1
                except Exception:
                    pass

            except Exception as e:
                latencies.append(90000)  # timeout sentinel
                print(f"  {backend} error: {e}")

        results[backend] = {
            "avg_ms": sum(latencies) / len(latencies),
            "json_rate": parse_ok / len(INCIDENTS),
        }
        print(f"{backend}: avg={results[backend]['avg_ms']:.0f}ms, json={results[backend]['json_rate']:.0%}")

    return results

asyncio.run(benchmark())
```

Typical results:

| | Ollama llama3.2:3b (CPU) | Ollama llama3.2:3b (GPU) | Claude Haiku |
|---|---|---|---|
| **Latency** | 2,000–8,000ms | 200–800ms | 350–600ms |
| **JSON compliance** | 70–85% | 70–85% | 99%+ |
| **Severity accuracy** | 60–75% | 60–75% | 90%+ |
| **Cost per call** | $0 | $0 | $0.0002 |

The key insight: on CPU, Ollama is slower than Claude for comparable quality. On GPU, latency is comparable. JSON compliance and severity accuracy are always lower — this is the fundamental quality tradeoff of air-gapped operation. For air-gapped deployments where data cannot leave the network, this tradeoff is non-negotiable: lower accuracy is better than no analysis.

---

## JSON Parse Failures: Retry Logic

Ollama models produce malformed JSON more frequently than Claude — typically 15–30% of responses in default mode, 10–20% with `"format": "json"`. Add a retry with escalating prompt pressure:

```python
async def analyze_local_with_retry(incident: str, max_attempts: int = 3) -> dict:
    """Analyze with Ollama, retrying with stricter JSON instructions on parse failure."""
    base_prompt = (
        f"SRE incident: {incident}\n"
        f"Classify severity P1-P4 and propose one remediation action.\n"
    )

    for attempt in range(max_attempts):
        if attempt == 0:
            json_instruction = 'Return JSON: {"severity":"P1","proposed_action":"...","confidence":0.8}'
        elif attempt == 1:
            json_instruction = (
                'IMPORTANT: Return ONLY valid JSON. No text before or after.\n'
                'Format: {"severity":"P1","proposed_action":"...","confidence":0.8}'
            )
        else:
            json_instruction = (
                '{"severity":"P1","proposed_action":"restart the pod","confidence":0.8}\n'
                'Output EXACTLY that format, filling in real values for this incident.'
            )

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": base_prompt + json_instruction,
                        "stream": False,
                        "format": "json",
                    },
                )
                data = resp.json()
                result = json.loads(data.get("response", "{}"))
                return {**result, "model": f"ollama/{OLLAMA_MODEL}", "source": "edge", "attempts": attempt + 1}
        except Exception as e:
            log.warning("Attempt %d failed: %s", attempt + 1, e)

    return {
        "severity": "P3",
        "proposed_action": "manual review — all Ollama retries failed",
        "confidence": 0.0,
        "source": "edge_fallback",
        "attempts": max_attempts,
    }
```

The third-attempt prompt shows the model an example with the exact structure — few-shot prompting at the failure boundary. This technique recovers roughly half of the remaining parse failures.

---

## ▶ STOP — do this now

Test the retry logic with a deliberately ambiguous incident:

```python
import asyncio
from edge.edge_aois import analyze_local_with_retry

async def test_retry():
    # Use an ambiguous incident — more likely to cause format issues
    incident = "intermittent timeouts observed — possibly network or application"
    result = await analyze_local_with_retry(incident, max_attempts=3)
    print("Severity:", result.get("severity"))
    print("Proposed action:", result.get("proposed_action", "")[:80])
    print("Attempts needed:", result.get("attempts", 1))
    print("Source:", result.get("source"))

asyncio.run(test_retry())
```

If `attempts=1`, the first prompt produced valid JSON — model was cooperative. If `attempts=3`, the ambiguous incident triggered format issues and the retry logic was necessary. Record which incidents consistently cause format issues — those are candidates for tighter prompt engineering.

---

## Routing P3/P4 to Ollama, P1/P2 to Claude

In production at a financial institution, the routing rule is:
- P1/P2 (high severity): must use Claude for accuracy — the cost of a wrong classification is far higher than the API cost
- P3/P4 (low severity, high volume): route to Ollama — the data stays on-premises, cost is zero, and accuracy at P3/P4 is acceptable

```python
# In main.py — add to the severity-tier mapping
SEVERITY_TIER_MAP = {
    "P1": "premium",   # Claude Sonnet
    "P2": "premium",   # Claude Sonnet
    "P3": "local",     # Ollama — stays on-prem for regulated environments
    "P4": "local",     # Ollama — cost zero for informational events
}

ROUTING_TIERS = {
    "premium": {
        "model": "claude-sonnet-4-6",
        "description": "Claude — P1/P2, maximum accuracy",
    },
    "local": {
        "model": "ollama/llama3.2:3b",
        "api_base": "http://localhost:11434",
        "description": "Ollama — P3/P4, data stays on-premises",
    },
}
```

This hybrid routing gives financial institutions exactly what they need: accurate AI for critical incidents, on-prem AI for the high-volume low-severity events that make up 80% of all incident traffic.

---

## Common Mistakes

### 1. Ollama not running when AOIS starts

```
httpx.ConnectError: [Errno 111] Connection refused
```

`ollama serve` must be started before AOIS. In production: `systemctl enable ollama && systemctl start ollama`. On the edge node, add an Ollama readiness check to the AOIS startup:

```python
async def check_ollama_ready(max_wait: int = 30) -> bool:
    for _ in range(max_wait):
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                await client.get(f"{OLLAMA_URL}/api/tags")
                return True
        except Exception:
            await asyncio.sleep(1)
    return False
```

### 2. Model not pulled before first request

```
{"error":"model 'llama3.2:3b' not found, try pulling it first"}
```

Pull the model before deployment, not at request time. Pulling llama3.2:3b takes 2–5 minutes on a fast connection. Include `ollama pull llama3.2:3b` in the edge node provisioning script — never in the application startup path.

### 3. Assuming `"format": "json"` guarantees valid JSON

Ollama's JSON format mode instructs the model to produce JSON but does not guarantee it. The model can still produce JSON with unescaped characters, trailing commas, or truncated output if `max_tokens` is reached. Always wrap Ollama responses in a `try/except` around `json.loads()`.

### 4. Clearing the offline queue before sync completes

If you delete `offline_queue.jsonl` and then the sync fails halfway through, you lose the unsynced entries. Always: sync first, verify `synced == len(queue)`, then clear. The `sync_to_central()` function does this atomically — do not add separate `unlink()` calls outside it.

---

## Troubleshooting

### Ollama produces empty JSON `{}`

The model did not understand the prompt. Check:
1. Is the prompt too long? llama3.2:3b has a 128k context window but degrades on very long inputs
2. Is `"format": "json"` set? Without it, the model returns prose
3. Try running `ollama run llama3.2:3b "Return JSON: {\"test\": true}"` — if this returns `{"test": true}`, the model is working. The issue is in the prompt

### Offline queue grows unbounded

This happens when `AOIS_CENTRAL_URL` is not set or always unreachable. Monitor queue size:
```bash
wc -l /var/aois/offline_queue.jsonl
# Expected: 0 when synced, growing when offline
```

Set a queue size limit: if the queue exceeds 10,000 entries, alert the operator. A queue that large suggests the sync mechanism is broken, not just temporarily offline.

### `litellm.exceptions.APIConnectionError` when calling Ollama

LiteLLM expects the Ollama API to respond at `{api_base}/chat/completions` (OpenAI-compatible format). Older Ollama versions only support `/api/generate`. Ensure Ollama version is 0.1.27+:
```bash
ollama --version
# ollama version 0.1.x — upgrade if below 0.1.27
```

---

## Connection to Later Phases

### To v34.5 (Capstone): the edge node is deployed to Hetzner as a separate k3s node. During the game day, network between edge and central is simulated as severed. AOIS continues analyzing on the edge node using Ollama. When connectivity is restored, `offline_queue.jsonl` syncs automatically. The number of queued incidents and the sync time are measured as part of the game day SLO evaluation.

---

## Mastery Checkpoint

1. Run `ollama run llama3.2:3b "Classify: CrashLoopBackOff on payments-api. Return JSON: {\"severity\": \"P1-P4\"}"`. Record the raw output. Is the JSON valid? Did the model add text before or after the JSON object?
2. Run `edge_analyze("auth-service OOMKilled")`. Confirm the result appears in `/var/aois/offline_queue.jsonl`. Show the file content with `cat /var/aois/offline_queue.jsonl | jq .`.
3. Run the latency benchmark: 5 Ollama calls vs 5 Claude Haiku calls on the same incidents. Show the numbers. What is the latency ratio on your hardware?
4. Configure LiteLLM to route P3/P4 incidents to Ollama and P1/P2 to Claude. Show the `ROUTING_TIERS` and `SEVERITY_TIER_MAP` config you would use.
5. Explain to an engineer at a financial institution why Ollama is required for their AOIS deployment. What specific compliance requirement does it satisfy? What accuracy tradeoff do they accept?
6. A Gartner analyst asks: "What is the quality gap between Ollama and Claude for incident classification?" Answer with the specific numbers from your benchmark: JSON compliance rate, severity accuracy rate, and latency comparison.
7. What happens if the edge node's offline queue is at 5,000 entries and the sync to central fails halfway through? Walk through exactly what the `sync_to_central()` function does, what remains in the queue, and what the operator should do next.

**The mastery bar:** AOIS runs fully offline using Ollama, queues results locally, and syncs to central when connectivity is restored. You can explain the quality tradeoffs, configure the hybrid routing for regulated environments, and handle the failure modes of the offline queue safely.

---

## 4-Layer Tool Understanding

### Ollama (Local LLM Server)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Some organizations cannot send log data to an external API — not because of technical limitations, but because regulators say so. Ollama runs the AI model on your hardware. No HTTP request leaves the network. The log event describing a failed transaction never touches an Anthropic server. AOIS analyzes incidents using local compute and produces the same severity classifications without any cloud dependency. |
| **System Role** | Where does it sit in AOIS? | An alternative LLM backend in the routing tier. LiteLLM routes to `ollama/llama3.2:3b` at `http://localhost:11434` using the same `completion()` interface as cloud models. The edge node uses Ollama exclusively. The central cluster uses Ollama for P3/P4 volume when data residency matters more than peak accuracy. |
| **Technical** | What is it precisely? | A local model serving tool that downloads and runs open-source LLMs (Llama, Mistral, Gemma, Phi) on CPU or GPU. Provides an OpenAI-compatible HTTP API at `localhost:11434`. Models are stored as GGUF files (quantized weights). `llama3.2:3b` with Q4_K_M quantization requires ~2GB RAM and runs at 2–8 tokens/second on CPU. The `"format": "json"` parameter enables JSON-constrained generation, improving structured output compliance. |
| **Remove it** | What breaks, and how fast? | Remove Ollama → air-gapped deployments have no LLM backend. Regulated environments cannot deploy AOIS. Local development requires API keys and incurs costs. The edge node cannot analyze incidents during network outages. Every AOIS analysis depends on internet connectivity to an external API — a hard blocker for the financial institution and field deployment use cases. |

### Offline Queue (JSONL + File-based Persistence)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | When the edge node is offline, incidents still happen. AOIS still analyzes them using Ollama. But those results need to reach the central cluster eventually — for the full incident history, for the Langfuse traces, for the compliance audit log. The offline queue is the bridge: a local file that stores results until connectivity returns, then drains to central. |
| **System Role** | Where does it sit in AOIS? | Between the edge analysis result and the central sync endpoint. After `analyze_local()` returns, `queue_for_sync()` appends to the JSONL file. When `connectivity_check()` succeeds, `sync_to_central()` drains the file to `POST /api/edge_sync`. No queue entry is lost — partial syncs rewrite only the unsynced tail. |
| **Technical** | What is it precisely? | An append-only JSONL file at `/var/aois/offline_queue.jsonl`. Each line is a JSON object: `{timestamp, incident, local_result}`. Append is atomic at OS level for entries under 4KB — no locking needed. Sync is ordered (oldest-first). Partial sync rewrites the file to preserve unsynced entries. Full sync deletes the file. The queue is bounded by disk — monitor size in production. |
| **Remove it** | What breaks, and how fast? | Remove the queue → edge analysis results exist only in memory. A network outage longer than a single request cycle means all offline analysis is lost. The operator never knows what happened during the 4-hour outage. The compliance audit trail has gaps. The central cluster's incident history is incomplete. The queue costs virtually nothing — the risk of removing it is all downside. |
