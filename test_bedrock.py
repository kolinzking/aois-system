"""
v10 — Bedrock vs Anthropic direct benchmark.
Run after midnight UTC when daily quota resets, or after quota increase.
"""
import litellm
import time
import statistics
import os
from dotenv import load_dotenv

load_dotenv()

LOG_SAMPLE = "pod/auth-service-7d9f CrashLoopBackOff — OOMKilled, exit code 137, 5 restarts in 10 minutes"

MODELS = {
    "anthropic_direct": "anthropic/claude-opus-4-6",
    "bedrock_haiku":    "bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "bedrock_sonnet":   "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
}

def benchmark(label, model, n=3):
    times = []
    last_response = ""
    for i in range(n):
        start = time.time()
        try:
            resp = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": f"Analyze this k8s log in one sentence: {LOG_SAMPLE}"}],
                max_tokens=100,
                aws_region_name="us-east-1",
            )
            elapsed = time.time() - start
            times.append(elapsed)
            last_response = resp.choices[0].message.content[:80]
        except Exception as e:
            print(f"{label:25} | attempt {i+1} ERROR: {e}")
            return

    mean = statistics.mean(times)
    stddev = statistics.stdev(times) if len(times) > 1 else 0
    print(f"{label:25} | mean: {mean:.2f}s | stddev: {stddev:.2f}s | response: {last_response}...")

print("Bedrock vs Anthropic Direct — Latency Benchmark")
print("=" * 80)
for label, model in MODELS.items():
    benchmark(label, model)
