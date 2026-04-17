import httpx
import json

BASE_URL = "http://localhost:8000"

# One representative incident per tier
TIER_TESTS = [
    {
        "tier": "premium",
        "name": "OOMKilled — Claude (premium)",
        "log": "FATAL: pod/payment-service-7d9f8b-xkp2q in namespace production was OOMKilled. Container payment-api exceeded memory limit of 512Mi. Restarts: 14. Last exit code: 137."
    },
    {
        "tier": "standard",
        "name": "CertExpiry — GPT-4o-mini (standard)",
        "log": "WARNING: TLS certificate for api.production.company.com expires in 3 days (2026-04-20). Auto-renewal via cert-manager has failed 3 consecutive times. Last error: ACME challenge failed - DNS record not found."
    },
    {
        "tier": "fast",
        "name": "DiskPressure — Groq Llama (fast)",
        "log": "Node node-worker-3 has condition DiskPressure=True. Available disk: 1.2Gi of 100Gi. Kubelet evicting pods. Affected pods: elasticsearch-data-0, prometheus-0, loki-0."
    },
]

# Full incident suite run on premium tier
INCIDENTS = [
    "FATAL: pod/payment-service-7d9f8b-xkp2q in namespace production was OOMKilled. Container payment-api exceeded memory limit of 512Mi. Restarts: 14. Last exit code: 137.",
    "Warning  BackOff  pod/auth-service-5c6d7e-mn3qr  Back-off restarting failed container. CrashLoopBackOff. Restarts: 8 in the last 10 minutes. Last log: 'panic: runtime error: invalid memory address or nil pointer dereference'",
    "Node node-worker-3 has condition DiskPressure=True. Available disk: 1.2Gi of 100Gi. Kubelet evicting pods.",
    "ALERT: HTTP 503 error rate on api-gateway exceeded threshold. Current rate: 34%. Affected endpoints: /api/v1/orders, /api/v1/checkout. Duration: 7 minutes.",
    "WARNING: TLS certificate for api.production.company.com expires in 3 days. Auto-renewal via cert-manager has failed 3 consecutive times.",
    "Pod ml-inference-6f8b9c-zt4wx in namespace ml-prod has been Pending for 18 minutes. Reason: Insufficient nvidia.com/gpu. 0/5 nodes available.",
]


def run_tier_tests():
    print(f"AOIS v2 — Routing Tier Test\n{'='*50}\n")

    for test in TIER_TESTS:
        print(f"[{test['name']}]")
        try:
            r = httpx.post(f"{BASE_URL}/analyze", json={"log": test["log"], "tier": test["tier"]}, timeout=30.0)
            result = r.json()
            print(f"  Severity:  {result['severity']}")
            print(f"  Provider:  {result['provider']}")
            print(f"  Cost:      ${result['cost_usd']:.6f}")
            print(f"  Summary:   {result['summary'][:100]}...")
        except Exception as e:
            print(f"  ERROR: {e}")
        print()


def run_cost_comparison():
    print(f"\nCost Comparison — Same Log, All Tiers\n{'='*50}\n")
    log = INCIDENTS[0]  # OOMKilled
    print(f"Log: {log[:80]}...\n")

    for tier in ["premium", "standard", "fast"]:
        try:
            r = httpx.post(f"{BASE_URL}/analyze", json={"log": log, "tier": tier}, timeout=30.0)
            result = r.json()
            print(f"  {tier:<10} → {result['provider']:<40} ${result['cost_usd']:.6f}  [{result['severity']}]")
        except Exception as e:
            print(f"  {tier:<10} → ERROR: {e}")


if __name__ == "__main__":
    run_tier_tests()
    run_cost_comparison()
