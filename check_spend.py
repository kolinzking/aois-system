#!/usr/bin/env python3
"""
Check AOIS API spend — run from the terminal anytime.

Usage:
    python3 check_spend.py           # today's summary
    python3 check_spend.py --full    # all recorded calls
    python3 check_spend.py --month   # this month's total
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path

SPEND_LOG = Path(os.getenv("AOIS_SPEND_LOG", Path.home() / ".aois_spend.jsonl"))
DAILY_BUDGET = float(os.getenv("AOIS_DAILY_BUDGET_USD", "2.00"))
SESSION_BUDGET = float(os.getenv("AOIS_SESSION_BUDGET_USD", "0.50"))


def load_entries() -> list[dict]:
    if not SPEND_LOG.exists():
        return []
    entries = []
    for line in SPEND_LOG.read_text().splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Show all recorded calls")
    parser.add_argument("--month", action="store_true", help="Show this month's total")
    args = parser.parse_args()

    entries = load_entries()
    today = date.today().isoformat()
    this_month = today[:7]

    today_entries = [e for e in entries if e.get("date") == today]
    month_entries = [e for e in entries if e.get("date", "").startswith(this_month)]

    today_total = sum(e.get("cost_usd", 0) for e in today_entries)
    month_total = sum(e.get("cost_usd", 0) for e in month_entries)

    print(f"\n{'='*50}")
    print(f"  AOIS Spend Report — {today}")
    print(f"{'='*50}")
    print(f"  Today:     ${today_total:.4f}  /  ${DAILY_BUDGET:.2f} daily cap  ({100*today_total/DAILY_BUDGET:.1f}%)")
    print(f"  This month: ${month_total:.4f}")
    print(f"  Calls today: {len(today_entries)}")
    print(f"  Spend log:  {SPEND_LOG}")

    if today_entries:
        # Cost by tier today
        by_tier: dict[str, float] = defaultdict(float)
        by_tier_calls: dict[str, int] = defaultdict(int)
        for e in today_entries:
            t = e.get("tier", "unknown")
            by_tier[t] += e.get("cost_usd", 0)
            by_tier_calls[t] += 1
        print(f"\n  Cost by tier (today):")
        for tier in sorted(by_tier, key=lambda t: -by_tier[t]):
            print(f"    {tier:12s}  ${by_tier[tier]:.4f}  ({by_tier_calls[tier]} calls)")

        # Most expensive single calls
        expensive = sorted(today_entries, key=lambda e: -e.get("cost_usd", 0))[:5]
        if expensive[0].get("cost_usd", 0) > 0.001:
            print(f"\n  Top calls today (by cost):")
            for e in expensive:
                import datetime
                ts = datetime.datetime.fromtimestamp(e.get("ts", 0)).strftime("%H:%M:%S")
                print(f"    {ts}  ${e.get('cost_usd', 0):.4f}  {e.get('tier','?'):8s}  {e.get('model','')[:40]}")

    if args.full:
        print(f"\n  All recorded calls ({len(entries)} total):")
        for e in entries[-20:]:  # last 20
            import datetime
            ts = datetime.datetime.fromtimestamp(e.get("ts", 0)).strftime("%Y-%m-%d %H:%M")
            print(f"    {ts}  ${e.get('cost_usd',0):.4f}  {e.get('tier','?'):8s}")

    if args.month:
        daily_totals: dict[str, float] = defaultdict(float)
        for e in month_entries:
            daily_totals[e.get("date", "?")] += e.get("cost_usd", 0)
        print(f"\n  Daily totals this month:")
        for d in sorted(daily_totals):
            bar = "█" * int(daily_totals[d] / DAILY_BUDGET * 20)
            print(f"    {d}  ${daily_totals[d]:.4f}  {bar}")

    print()

    # Exit non-zero if at 80%+ of daily budget — useful in CI/cron
    if today_total >= DAILY_BUDGET * 0.80:
        print(f"  ⚠  WARNING: {100*today_total/DAILY_BUDGET:.0f}% of daily budget used")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
