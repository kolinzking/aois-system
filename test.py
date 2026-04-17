import httpx
import json

BASE_URL = "http://localhost:8000"

INCIDENTS = [
    {
        "name": "OOMKilled",
        "log": "FATAL: pod/payment-service-7d9f8b-xkp2q in namespace production was OOMKilled. Container payment-api exceeded memory limit of 512Mi. Restarts: 14. Last exit code: 137."
    },
    {
        "name": "CrashLoopBackOff",
        "log": "Warning  BackOff  pod/auth-service-5c6d7e-mn3qr  Back-off restarting failed container. CrashLoopBackOff. Restarts: 8 in the last 10 minutes. Last log: 'panic: runtime error: invalid memory address or nil pointer dereference'"
    },
    {
        "name": "DiskPressure",
        "log": "Node node-worker-3 has condition DiskPressure=True. Available disk: 1.2Gi of 100Gi. Kubelet evicting pods. Affected pods: elasticsearch-data-0, prometheus-0, loki-0."
    },
    {
        "name": "5xx Spike",
        "log": "ALERT: HTTP 503 error rate on api-gateway exceeded threshold. Current rate: 34% (baseline: 0.1%). Affected endpoints: /api/v1/orders, /api/v1/checkout. Duration: 7 minutes. Upstream: order-service timing out after 30s."
    },
    {
        "name": "CertExpiry",
        "log": "WARNING: TLS certificate for api.production.company.com expires in 3 days (2026-04-20). Certificate issuer: Let's Encrypt. Auto-renewal via cert-manager has failed 3 consecutive times. Last error: ACME challenge failed - DNS record not found."
    },
    {
        "name": "PodPending",
        "log": "Pod ml-inference-6f8b9c-zt4wx in namespace ml-prod has been Pending for 18 minutes. Reason: Insufficient nvidia.com/gpu. 0/5 nodes available: 5 Insufficient nvidia.com/gpu. Node GPU utilization: 100%."
    },
]

def run_tests():
    print(f"AOIS v1 — Test Suite\n{'='*50}\n")

    for incident in INCIDENTS:
        print(f"[{incident['name']}]")
        print(f"Log: {incident['log'][:80]}...")

        try:
            response = httpx.post(
                f"{BASE_URL}/analyze",
                json={"log": incident["log"]},
                timeout=30.0
            )
            result = response.json()
            print(f"Severity:   {result['severity']}")
            print(f"Summary:    {result['summary']}")
            print(f"Action:     {result['suggested_action']}")
            print(f"Confidence: {result['confidence']:.0%}")
        except Exception as e:
            print(f"ERROR: {e}")

        print()

if __name__ == "__main__":
    run_tests()
