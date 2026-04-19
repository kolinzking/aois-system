"""
v13 — NVIDIA NIM latency and cost benchmark.
Tests NGC-hosted NIM (llama-3.1-8b-instruct) vs Claude vs GPT-4o-mini.
Requires NVIDIA_NIM_API_KEY in .env (from build.nvidia.com).
"""
import litellm
import time
import statistics
import os
from dotenv import load_dotenv

load_dotenv()

litellm.drop_params = True

LOG_SAMPLE = "pod/auth-service-7d9f CrashLoopBackOff — OOMKilled, exit code 137, 5 restarts in 10 minutes"

MODELS = {
    "nim_llama_8b":     "nvidia_nim/meta/llama-3.1-8b-instruct",
    "groq_llama_8b":    "groq/llama-3.1-8b-instant",
    "gpt4o_mini":       "gpt-4o-mini",
    "claude_premium":   "anthropic/claude-opus-4-6",
}

NIM_API_BASE = "https://integrate.api.nvidia.com/v1"
NIM_API_KEY  = os.getenv("NVIDIA_NIM_API_KEY")

def benchmark(label, model, n=3):
    times = []
    last_response = ""
    extra = {}
    if model.startswith("nvidia_nim/"):
        # LiteLLM doesn't have NIM in its model map — call as openai-compatible
        model = "openai/" + model.split("nvidia_nim/", 1)[1]
        extra = {"api_base": NIM_API_BASE, "api_key": NIM_API_KEY}
    for i in range(n):
        start = time.time()
        try:
            resp = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": f"Analyze this k8s log in one sentence: {LOG_SAMPLE}"}],
                max_tokens=100,
                **extra,
            )
            elapsed = time.time() - start
            times.append(elapsed)
            last_response = resp.choices[0].message.content[:80]
            cost = litellm.completion_cost(completion_response=resp)
        except Exception as e:
            print(f"  {label:25} | attempt {i+1} ERROR: {e}")
            return

    mean = statistics.mean(times)
    stddev = statistics.stdev(times) if len(times) > 1 else 0.0
    print(f"  {label:25} | mean: {mean:.2f}s | stddev: {stddev:.2f}s | ~${cost:.6f}/call | {last_response[:60]}...")

print("NVIDIA NIM vs Claude vs Groq — Latency & Cost Benchmark")
print("=" * 80)
print("Model routing philosophy:")
print("  P1/P2 (critical/high) → Claude premium — best reasoning, cost irrelevant")
print("  P3/P4 (warning/low)   → NIM llama-8b  — volume tier, ~10x cheaper")
print()
for label, model in MODELS.items():
    print(f"Benchmarking {label}...")
    benchmark(label, model)

print()
print("Cost-aware routing decision:")
print("  If NIM latency < 3s and quality acceptable → route P3/P4 to NIM")
print("  If NIM latency > 5s or quality degraded    → keep on GPT-4o-mini")
