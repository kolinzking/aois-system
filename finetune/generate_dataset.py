"""
v15 — Generate SRE fine-tuning dataset.

Produces 500 (log, analysis) pairs in JSONL format ready for LoRA fine-tuning.
Uses Claude Haiku to generate diverse, realistic SRE responses.

Usage:
    python3 finetune/generate_dataset.py
Output:
    finetune/sre_dataset.jsonl   — full dataset
    finetune/sre_train.jsonl     — 450 samples (train)
    finetune/sre_eval.jsonl      — 50 samples (eval)
"""

import json
import os
import random
import time
from pathlib import Path
from dotenv import load_dotenv
import openai

load_dotenv()

# Groq for batch dataset generation — simple JSON classification, no reasoning needed.
# Never use Anthropic for bulk labelling jobs: no caching = full input token cost * N calls.
_groq = openai.OpenAI(
    api_key=os.getenv("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1",
)

# Seed logs covering the full range of SRE incident types AOIS sees
SEED_LOGS = [
    # OOM / Memory
    "OOMKilled: container aois-api exceeded memory limit 512Mi, exit code 137",
    "pod/worker-7d9f killed: memory limit exceeded, used 1.8Gi of 1Gi limit",
    "Java heap space OutOfMemoryError in payment-service, GC overhead limit exceeded",
    "Node memory pressure detected: available 128Mi of 8Gi, evicting pods",

    # CrashLoop
    "Back-off restarting failed container nginx-proxy in pod ingress-7f8d9, restarts: 14",
    "CrashLoopBackOff: auth-service failed 5 times in 10 minutes, last exit code 1",
    "pod/db-migrator CrashLoopBackOff: migration script failing on startup",

    # Disk
    "Disk usage at 94% on /var/lib/docker, inode exhaustion imminent",
    "PersistentVolumeClaim postgres-data: 95% full, 512Mi remaining of 10Gi",
    "No space left on device: /var/log partition full, log rotation failed",

    # Network / DNS
    "DNS resolution failed for redis.prod.svc.cluster.local: timeout after 5s",
    "Connection refused: postgres:5432, pod api-server-6b7d retrying (attempt 23)",
    "Network policy blocking egress from namespace prod to namespace monitoring",
    "Service mesh timeout: auth → payment latency p99=8900ms, threshold=3000ms",

    # TLS / Certs
    "TLS certificate for api.prod.company.com expires in 3 days",
    "certificate verify failed: self-signed certificate in chain, service unavailable",
    "cert-manager: CertificateRequest failed: ACME challenge DNS01 timed out",

    # 5xx spikes
    "HTTP 503 rate: 45% of requests, upstream payment-service unhealthy",
    "Error rate spike: 500 errors increased from 0.1% to 12% in last 5 minutes",
    "Gateway timeout (504): downstream checkout-service not responding",

    # CPU / Throttling
    "CPU throttling: container api-server throttled 78% of the time, limit 500m",
    "HPA unable to scale: CPU utilization 95%, max replicas 10 already reached",
    "Load average 48.3 on 8-core node, kernel scheduling delays detected",

    # Kubernetes
    "Node worker-3 NotReady: kubelet stopped posting node status, last heartbeat 8m ago",
    "Deployment rollout stuck: 3/5 pods ready, readiness probe failing on /healthz",
    "ImagePullBackOff: ghcr.io/org/api:v2.1.0 not found or no pull credentials",
    "Evicted: pod prometheus-0 evicted due to disk pressure on node worker-1",
    "PodDisruptionBudget violated: cannot evict pod, minAvailable=2 would be breached",

    # Database
    "PostgreSQL: max_connections reached (100/100), new connections being rejected",
    "Slow query alert: SELECT * FROM events WHERE timestamp > NOW() - INTERVAL '1 day' took 45s",
    "Replication lag: replica-2 is 4.2GB behind primary, catching up",
    "Deadlock detected in transaction on table orders, rolled back",
    "Redis: used_memory 7.8GB of 8GB maxmemory, evicting keys with allkeys-lru",

    # Security
    "Failed login attempts: 847 failures for user admin from IP 185.220.101.x in 1 hour",
    "Falco alert: unexpected outbound connection from pod api-server to 1.2.3.4:4444",
    "Pod running as root detected in namespace prod: container nginx uid=0",
    "Secret rotation overdue: database-credentials last rotated 180 days ago",

    # Kafka / Streaming
    "Consumer lag: topic aois-logs partition 0 lag=142000, consumer group aois-workers",
    "Kafka broker disk 87% full: /kafka/data, oldest offset retention at risk",
    "Producer timeout: unable to publish to topic events after 3 retries, broker unavailable",
]

SYSTEM_PROMPT = """You are an expert SRE at a large technology company. Given an infrastructure log message, provide a concise structured analysis as valid JSON with exactly these fields:
- summary: one sentence describing what is happening
- severity: exactly one of P1, P2, P3, P4
- suggested_action: specific actionable remediation step
- confidence: number between 0.0 and 1.0

P1 = production down / data loss risk
P2 = degraded / will break within 1 hour without action
P3 = warning / action needed within 24 hours
P4 = informational / preventive maintenance

Respond with only the JSON object, no other text."""

def analyze_log(log: str) -> dict | None:
    """Call Groq to generate one training example. Simple JSON classification — no reasoning needed."""
    try:
        msg = _groq.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=256,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Log: {log}"},
            ],
        )
        response_text = msg.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1]).strip()
        analysis = json.loads(response_text)
        # Validate required fields
        assert all(k in analysis for k in ["summary", "severity", "suggested_action", "confidence"])
        assert analysis["severity"] in ["P1", "P2", "P3", "P4"]
        return analysis
    except Exception as e:
        print(f"  Error: {e}")
        return None


def make_training_example(log: str, analysis: dict) -> dict:
    """Format as chat fine-tuning example (OpenAI/HuggingFace format)."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Log: {log}"},
            {"role": "assistant", "content": json.dumps(analysis)},
        ]
    }


def vary_log(base_log: str) -> str:
    """Create a variation of a seed log with different numbers/names."""
    import re
    # Vary numbers
    def replace_num(m):
        n = int(m.group())
        if n == 0:
            return str(n)
        lo = max(1, n - n // 3)
        hi = max(lo + 1, n + n // 3)
        return str(random.randint(lo, hi))
    varied = re.sub(r'\b\d+\b', replace_num, base_log)
    # Vary pod names
    suffixes = ["7d9f", "6b8c", "4a2e", "9f1d", "3c5b", "8e4a", "2d7f", "5b9c"]
    varied = re.sub(r'\b[a-z]+-[0-9a-f]{4}\b', lambda m: m.group().split('-')[0] + '-' + random.choice(suffixes), varied)
    return varied


def main():
    out_path = Path("finetune/sre_dataset.jsonl")
    target = 500
    batch_size = 10

    existing = []
    if out_path.exists():
        with open(out_path) as f:
            existing = [json.loads(l) for l in f if l.strip()]
        print(f"Resuming: {len(existing)} examples already generated")

    examples = existing[:]

    with open(out_path, "a") as f:
        while len(examples) < target:
            # Pick a seed log, create variation
            base = random.choice(SEED_LOGS)
            log = vary_log(base) if random.random() > 0.3 else base

            print(f"[{len(examples)+1}/{target}] {log[:60]}...")
            analysis = analyze_log(log)
            if analysis is None:
                continue

            example = make_training_example(log, analysis)
            examples.append(example)
            f.write(json.dumps(example) + "\n")
            f.flush()

            # Rate limit: Haiku is fast but be polite
            if len(examples) % batch_size == 0:
                print(f"  {len(examples)} examples generated")
                time.sleep(1)

    print(f"\nDataset complete: {len(examples)} examples")

    # Split train / eval
    random.shuffle(examples)
    train = examples[:450]
    eval_ = examples[450:]

    with open("finetune/sre_train.jsonl", "w") as f:
        for e in train:
            f.write(json.dumps(e) + "\n")

    with open("finetune/sre_eval.jsonl", "w") as f:
        for e in eval_:
            f.write(json.dumps(e) + "\n")

    print(f"Train: {len(train)} | Eval: {len(eval_)}")
    print("Done. Next: python3 finetune/finetune.py")


if __name__ == "__main__":
    main()
