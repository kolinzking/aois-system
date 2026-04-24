# v32 — Edge AI with Ollama: Air-Gapped AOIS

⏱ **Estimated time: 4–5 hours**

---

## Prerequisites

v31 multimodal complete. Ollama installed.

```bash
# Ollama running
ollama list
# NAME                    ID              SIZE    MODIFIED
# ...

# Pull a small model for testing
ollama pull llama3.2:3b
ollama run llama3.2:3b "Classify: OOMKilled pod, one word: P1, P2, P3, or P4"
# P1
```

---

## Learning Goals

By the end you will be able to:

- Run AOIS locally with Ollama as the LLM backend — no internet, no API costs
- Explain the air-gapped use case: regulated environments, field deployments, cost-zero testing
- Implement the sync mechanism: edge node analyzes offline, syncs results to central cluster when online
- Benchmark Ollama latency and quality vs Claude API — know where open models win and lose
- Configure LiteLLM to route to Ollama using the same interface as cloud models

---

## Why Edge AI Matters

Three real scenarios where AOIS must work without internet:

**1. Regulated environments**: healthcare or financial systems where LLM data cannot leave the network. All analysis must run on-premises.

**2. Field deployments**: AOIS on a Kubernetes cluster at a remote facility with intermittent connectivity. Incidents happen with or without internet. The analysis must happen locally.

**3. Cost-zero development**: run AOIS locally for development and testing with no API costs. All prompts hit local Ollama instead of Anthropic.

---

## Ollama as AOIS Backend

Ollama provides an OpenAI-compatible API. LiteLLM routes to it using the same `client.messages.create()` interface.

```python
# In main.py — add Ollama tier to routing
ROUTING_TIERS = {
    ...
    "local": {
        "model": "ollama/llama3.2:3b",
        "base_url": "http://localhost:11434",
        "description": "Local Ollama — air-gapped, zero cost",
    },
}
```

LiteLLM format:
```python
import litellm

response = litellm.completion(
    model="ollama/llama3.2:3b",
    messages=[{"role": "user", "content": "Classify: OOMKilled pod. Return JSON: {\"severity\": \"P1-P4\"}"}],
    api_base="http://localhost:11434",
)
print(response.choices[0].message.content)
```

---

## ▶ STOP — do this now

Run the AOIS classifier with Ollama:

```bash
# Start Ollama in the background
ollama serve &

# Run AOIS against Ollama
python3 - << 'EOF'
import litellm, json, re

response = litellm.completion(
    model="ollama/llama3.2:3b",
    messages=[{"role": "user", "content": (
        "Classify severity (P1-P4) for: auth-service pod OOMKilled exit code 137\n"
        'Return JSON: {"severity": "P1", "reason": "..."}'
    )}],
    api_base="http://localhost:11434",
)
text = response.choices[0].message.content
print("Raw:", text)
try:
    data = json.loads(re.search(r'\{[^{}]+\}', text, re.DOTALL).group())
    print("Severity:", data.get("severity"))
except Exception:
    print("Parse failed — open model JSON compliance is lower than Claude")
EOF
```

Expected: severity=P1 most of the time, but JSON compliance is lower than Claude. This is the quality tradeoff of air-gapped operation.

---

## Edge Node Configuration

The edge AOIS instance runs with `AOIS_MODE=edge`:

```python
# edge/edge_aois.py
"""AOIS edge node — runs on Ollama when offline, syncs to central when online."""
import asyncio
import httpx
import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("aois.edge")

CENTRAL_SYNC_URL = os.getenv("AOIS_CENTRAL_URL", "")
LOCAL_QUEUE_PATH = Path("/var/aois/offline_queue.jsonl")
LOCAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")


async def analyze_local(incident: str) -> dict:
    """Analyze using local Ollama — works offline."""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": "llama3.2:3b",
                    "prompt": (
                        f"SRE incident: {incident}\n"
                        f"Classify severity P1-P4 and propose action.\n"
                        f'Return JSON: {{"severity":"P1","proposed_action":"...","confidence":0.8}}'
                    ),
                    "stream": False,
                    "format": "json",
                },
            )
            data = resp.json()
            result = json.loads(data.get("response", "{}"))
            return {**result, "model": "ollama/llama3.2:3b", "source": "edge"}
        except Exception as e:
            log.error("Ollama analysis failed: %s", e)
            return {"severity": "P3", "proposed_action": "manual review", "source": "edge_fallback"}


async def queue_for_sync(incident: str, local_result: dict):
    """Store the incident and local result for later sync to central."""
    entry = {
        "timestamp": time.time(),
        "incident": incident,
        "local_result": local_result,
    }
    with open(LOCAL_QUEUE_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    log.info("Queued for sync: %s", incident[:60])


async def sync_to_central():
    """Send offline queue to central AOIS when connectivity returns."""
    if not CENTRAL_SYNC_URL:
        log.warning("AOIS_CENTRAL_URL not set — cannot sync")
        return 0

    if not LOCAL_QUEUE_PATH.exists():
        return 0

    queue = LOCAL_QUEUE_PATH.read_text().strip().split("\n")
    synced = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for line in queue:
            if not line:
                continue
            try:
                entry = json.loads(line)
                await client.post(f"{CENTRAL_SYNC_URL}/api/edge_sync", json=entry)
                synced += 1
            except Exception as e:
                log.warning("Sync failed for entry: %s", e)
                break  # stop on first failure — connectivity may be gone again

    # Clear successfully synced entries
    if synced == len([l for l in queue if l]):
        LOCAL_QUEUE_PATH.unlink()
        log.info("Sync complete — %d entries uploaded, queue cleared", synced)
    else:
        log.info("Partial sync — %d/%d entries uploaded", synced, len(queue))

    return synced


async def edge_analyze(incident: str) -> dict:
    """Main edge entry point: analyze locally and queue for sync."""
    result = await analyze_local(incident)
    await queue_for_sync(incident, result)
    return result
```

---

## ▶ STOP — do this now

Run the edge analysis and check the offline queue:

```python
import asyncio
from edge.edge_aois import edge_analyze

async def main():
    result = await edge_analyze("auth-service OOMKilled — offline cluster")
    print("Local result:", result)

    from pathlib import Path
    queue = Path("/var/aois/offline_queue.jsonl")
    if queue.exists():
        print("Queue:", queue.read_text()[:200])

asyncio.run(main())
```

When connectivity returns:
```python
synced = asyncio.run(sync_to_central())
print(f"Synced {synced} incidents to central")
```

---

## Benchmarking: Ollama vs Claude

```python
# Run on the golden dataset with both backends
import asyncio, json, time
from pathlib import Path

dataset = json.loads((Path("evals/golden_dataset.json")).read_text())

results = {"ollama": [], "claude": []}

for entry in dataset[:10]:  # 10 samples to limit cost
    for backend in ["ollama", "claude"]:
        t0 = time.perf_counter()
        if backend == "ollama":
            import litellm
            resp = litellm.completion(
                model="ollama/llama3.2:3b",
                messages=[{"role": "user", "content": f"Classify: {entry['incident_description']}. Return JSON: {{\"severity\": \"P1\"}}"}],
                api_base="http://localhost:11434",
            )
            sev = "P3"  # parse from resp
        # ...
        latency = (time.perf_counter() - t0) * 1000
        results[backend].append(latency)

for backend, latencies in results.items():
    print(f"{backend}: avg={sum(latencies)/len(latencies):.0f}ms")
```

Typical results:
| | Ollama llama3.2:3b | Claude Haiku |
|---|---|---|
| Latency (CPU) | 2,000–8,000ms | 350–600ms |
| Latency (GPU) | 200–800ms | 350–600ms |
| JSON compliance | 70–85% | 99%+ |
| Severity accuracy | 60–75% | 90%+ |
| Cost | $0 | $0.0002/call |

Ollama on CPU is slower and less accurate. On GPU, latency is comparable. JSON compliance gap is the biggest operational risk for air-gapped deployments — add retry logic.

---

## Common Mistakes

### 1. Ollama not running when AOIS starts

```
httpx.ConnectError: [Errno 111] Connection refused
```

Ensure Ollama is running: `ollama serve`. In production: `systemctl enable ollama && systemctl start ollama`.

### 2. Model not pulled before first request

```
{"error":"model 'llama3.2:3b' not found"}
```

Pull the model first: `ollama pull llama3.2:3b`. This can take minutes for large models. Pull as part of the deployment process, not at request time.

---

## Troubleshooting

### JSON parse failures from Ollama

Open models produce malformed JSON more often than Claude. Add a retry with stricter prompting:

```python
for attempt in range(3):
    response = ollama_call(prompt)
    try:
        return json.loads(re.search(r'\{.*\}', response, re.DOTALL).group())
    except Exception:
        prompt += "\nIMPORTANT: Return ONLY valid JSON. No text before or after the JSON object."
```

---

## Connection to Later Phases

### To v34.5 (Capstone): the edge node is deployed to Hetzner as a separate k3s node. During the game day, network between edge and central is severed. AOIS continues analyzing on the edge node using Ollama. When connectivity is restored, offline_queue syncs automatically.

---

## Mastery Checkpoint

1. Run `ollama run llama3.2:3b "Classify: CrashLoopBackOff on payments-api. Return JSON: {\"severity\": \"P1-P4\"}"`. Record the output and whether the JSON is valid.
2. Run `edge_analyze("auth-service OOMKilled")`. Confirm the result appears in `/var/aois/offline_queue.jsonl`.
3. Compare latency: 10 Ollama calls vs 10 Claude Haiku calls on the same 10 golden dataset incidents. Show the numbers.
4. Configure LiteLLM to route P3/P4 incidents to Ollama and P1/P2 to Claude. Show the routing config.
5. Explain to an engineer at a financial institution why Ollama is necessary for their AOIS deployment. What compliance requirement does it satisfy?

**The mastery bar:** AOIS runs fully offline using Ollama, queues results locally, and syncs to central when connectivity is restored — zero external API calls needed during an air-gapped incident.

---

## 4-Layer Tool Understanding

### Ollama (Local LLM)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Some organizations cannot send log data to an external API. Ollama runs the AI model locally on your hardware — no data leaves the network. AOIS analyzes incidents using local compute and produces the same severity classifications without calling any cloud service. |
| **System Role** | Where does it sit in AOIS? | An alternative LLM backend in the routing tier. LiteLLM routes to `ollama/llama3.2:3b` using the same interface as cloud models. The edge node uses Ollama exclusively; the central cluster uses Ollama only for P3/P4 volume when cost reduction matters more than peak accuracy. |
| **Technical** | What is it precisely? | A local model serving tool that downloads and runs open-source LLMs (Llama, Mistral, Gemma) on CPU or GPU. Provides an OpenAI-compatible HTTP API at `localhost:11434`. Models are stored as GGUF files. Quantization (Q4_K_M by default) reduces model size and memory requirements at some quality cost. |
| **Remove it** | What breaks, and how fast? | Remove Ollama → air-gapped deployments have no LLM backend. Regulated environments cannot deploy AOIS. Local development requires API keys and incurs costs. The edge node cannot analyze incidents during network outages. Every AOIS analysis depends on internet connectivity to an external API. |
