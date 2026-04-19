"""
v14 — vLLM on Modal benchmark.

Tests the vllm tier against premium (Claude) on the same 4 log samples.
Measures latency and cost per tier.

Prerequisites:
  1. modal deploy vllm_modal/serve.py
  2. Copy the printed endpoint URL into .env as VLLM_MODAL_URL=https://...
  3. python3 test_vllm.py

Expected output: table comparing latency (ms) and cost ($) per tier per log.
"""

import os
import time
import json
from dotenv import load_dotenv

load_dotenv()

AOIS_URL = os.getenv("AOIS_URL", "http://localhost:8000")

LOGS = [
    {
        "name": "OOMKilled",
        "log": "pod/api-server-7d8b9c-xkp2q OOMKilled exit code 137, memory limit 512Mi exceeded",
        "expected_severity": "P2",
    },
    {
        "name": "CrashLoopBackOff",
        "log": "Back-off restarting failed container api-server in pod api-server-7d8b9c-xkp2q, restarts: 8",
        "expected_severity": "P2",
    },
    {
        "name": "Disk pressure",
        "log": "Node worker-3 condition DiskPressure=True, available: 2Gi, threshold: 10Gi",
        "expected_severity": "P3",
    },
    {
        "name": "High latency",
        "log": "p99 latency 4200ms on /api/checkout, up from baseline 180ms, no error rate change",
        "expected_severity": "P3",
    },
]

TIERS_TO_TEST = ["premium", "vllm"]


def call_analyze(log: str, tier: str) -> tuple[dict, float]:
    import httpx
    start = time.time()
    resp = httpx.post(
        f"{AOIS_URL}/analyze",
        json={"log": log, "tier": tier},
        timeout=600.0,  # vLLM cold start: 3-5min GPU + model load
    )
    elapsed_ms = (time.time() - start) * 1000
    resp.raise_for_status()
    return resp.json(), elapsed_ms


def run():
    vllm_url = os.getenv("VLLM_MODAL_URL", "")
    nim_key = os.getenv("NVIDIA_NIM_API_KEY", "")
    if vllm_url:
        backend = "Modal GPU (self-hosted vLLM)"
    elif nim_key:
        backend = "NVIDIA NIM — mistral-7b-instruct-v0.3 (same model, NGC-hosted)"
    else:
        backend = None

    if not backend:
        print("⚠️  No vLLM backend available. Set VLLM_MODAL_URL or NVIDIA_NIM_API_KEY in .env")
        print("Running premium tier only for comparison baseline...")
        tiers = ["premium"]
    else:
        print(f"vLLM backend: {backend}")
        tiers = TIERS_TO_TEST

    results = {}

    for tier in tiers:
        results[tier] = []
        print(f"\n{'='*60}")
        print(f"Tier: {tier}")
        print("="*60)

        for sample in LOGS:
            print(f"\n  [{sample['name']}]")
            try:
                data, latency_ms = call_analyze(sample["log"], tier)
                correct = data.get("severity") == sample["expected_severity"]
                marker = "✓" if correct else "✗"
                print(f"  {marker} severity: {data.get('severity')} (expected {sample['expected_severity']})")
                print(f"    latency:    {latency_ms:.0f}ms")
                print(f"    cost:       ${data.get('cost_usd', 0):.6f}")
                print(f"    provider:   {data.get('provider', 'unknown')}")
                print(f"    summary:    {data.get('summary', '')[:80]}...")
                results[tier].append({
                    "name": sample["name"],
                    "latency_ms": latency_ms,
                    "cost_usd": data.get("cost_usd", 0),
                    "severity": data.get("severity"),
                    "correct": correct,
                })
            except Exception as e:
                print(f"  ERROR: {e}")
                results[tier].append({"name": sample["name"], "error": str(e)})

    # Summary table
    print(f"\n\n{'='*60}")
    print("SUMMARY — latency and cost comparison")
    print("="*60)
    print(f"{'Log':<20} {'Tier':<10} {'Latency':>10} {'Cost':>12} {'Correct':>8}")
    print("-"*60)

    for tier in tiers:
        for r in results[tier]:
            if "error" in r:
                print(f"{r['name']:<20} {tier:<10} {'ERROR':>10}")
            else:
                correct_str = "yes" if r["correct"] else "NO"
                print(
                    f"{r['name']:<20} {tier:<10} "
                    f"{r['latency_ms']:>8.0f}ms "
                    f"${r['cost_usd']:>10.6f} "
                    f"{correct_str:>8}"
                )

    # Aggregate per tier
    print(f"\n{'Tier':<10} {'Avg latency':>14} {'Total cost':>12} {'Accuracy':>10}")
    print("-"*50)
    for tier in tiers:
        valid = [r for r in results[tier] if "error" not in r]
        if valid:
            avg_lat = sum(r["latency_ms"] for r in valid) / len(valid)
            total_cost = sum(r["cost_usd"] for r in valid)
            accuracy = sum(1 for r in valid if r["correct"]) / len(valid) * 100
            print(f"{tier:<10} {avg_lat:>12.0f}ms  ${total_cost:>10.6f}  {accuracy:>8.0f}%")

    print()
    print("Decision framework:")
    print("  vLLM (Modal A10G): ~$0.000010–0.000030/call, ~1000–3000ms, good for P3/P4 volume")
    print("  Claude premium:    ~$0.000500–0.002000/call, ~800–2000ms,  required for P1/P2")
    print()
    print("When GPU is amortized across 1000s of calls, vLLM beats Groq on cost.")
    print("When you need reasoning quality (P1/P2), Claude wins every time.")


if __name__ == "__main__":
    run()
