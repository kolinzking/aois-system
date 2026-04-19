"""v11 — Lambda vs always-on k8s cost comparison."""

def lambda_monthly_cost(calls_per_day, duration_seconds=3, memory_gb=0.5):
    gb_seconds = calls_per_day * 30 * duration_seconds * memory_gb
    compute_cost = gb_seconds * 0.0000166667
    request_cost = max(0, (calls_per_day * 30 - 1_000_000)) * 0.0000002
    apigw_cost = calls_per_day * 30 * 0.0000035
    return compute_cost + request_cost + apigw_cost

hetzner_monthly = 4.50

print(f"{'Calls/day':>12} | {'Lambda/month':>14} | {'Hetzner/month':>14} | {'Winner':>8}")
print("-" * 60)
for calls in [10, 100, 1_000, 10_000, 100_000, 200_000]:
    lc = lambda_monthly_cost(calls)
    winner = "Lambda" if lc < hetzner_monthly else "Hetzner"
    print(f"{calls:>12,} | ${lc:>13.4f} | ${hetzner_monthly:>13.2f} | {winner:>8}")
