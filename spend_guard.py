"""
Spend guard — hard daily and per-session cost caps for pay-as-you-go API usage.

Caps are read from env vars so you can change them without touching code:
  AOIS_DAILY_BUDGET_USD   — default $2.00  (hard stop, resets at midnight UTC)
  AOIS_SESSION_BUDGET_USD — default $0.50  (per process lifetime)
  AOIS_WARN_THRESHOLD_PCT — default 0.80   (log warning at 80% of daily budget)

When the daily cap is hit: calls to check_spend_and_block() raise BudgetExceeded.
The caller (main.py) catches this and returns HTTP 429 with a clear message.

Spend is tracked in two places:
  - In-process: a module-level float (resets on restart)
  - File: ~/.aois_spend.jsonl — one line per call, readable with `check_spend.py`
"""

import json
import os
import time
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger("aois.spend_guard")

DAILY_BUDGET = float(os.getenv("AOIS_DAILY_BUDGET_USD", "2.00"))
SESSION_BUDGET = float(os.getenv("AOIS_SESSION_BUDGET_USD", "0.50"))
WARN_PCT = float(os.getenv("AOIS_WARN_THRESHOLD_PCT", "0.80"))

SPEND_LOG = Path(os.getenv("AOIS_SPEND_LOG", str(Path.home() / ".aois_spend.jsonl")))

# In-process accumulators
_session_spend: float = 0.0
_session_calls: int = 0


class BudgetExceeded(Exception):
    pass


def _today() -> str:
    return date.today().isoformat()


def _load_daily_spend() -> float:
    """Read today's total spend from the spend log file."""
    if not SPEND_LOG.exists():
        return 0.0
    today = _today()
    total = 0.0
    try:
        for line in SPEND_LOG.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("date") == today:
                total += entry.get("cost_usd", 0.0)
    except Exception:
        pass
    return total


def record_spend(cost_usd: float, model: str, tier: str) -> None:
    """Record a call to the spend log and update in-process counters."""
    global _session_spend, _session_calls

    _session_spend += cost_usd
    _session_calls += 1

    entry = {
        "date": _today(),
        "ts": time.time(),
        "cost_usd": round(cost_usd, 6),
        "model": model,
        "tier": tier,
        "session_total": round(_session_spend, 6),
    }
    try:
        SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SPEND_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log.warning("Could not write spend log: %s", e)

    daily = _load_daily_spend()
    if daily >= DAILY_BUDGET * WARN_PCT:
        log.warning(
            "SPEND WARNING: $%.4f of $%.2f daily budget used (%.0f%%)",
            daily, DAILY_BUDGET, 100 * daily / DAILY_BUDGET,
        )


def check_spend_and_block(estimated_cost_usd: float = 0.0) -> None:
    """
    Call BEFORE making an LLM request. Raises BudgetExceeded if either cap
    would be exceeded by this call.
    """
    global _session_spend

    # Session cap
    if _session_spend + estimated_cost_usd > SESSION_BUDGET:
        raise BudgetExceeded(
            f"Session budget exhausted: ${_session_spend:.4f} spent "
            f"(cap: ${SESSION_BUDGET:.2f}). Restart AOIS to reset."
        )

    # Daily cap (reads file — slightly slower but cross-process safe)
    daily = _load_daily_spend()
    if daily + estimated_cost_usd > DAILY_BUDGET:
        raise BudgetExceeded(
            f"Daily budget exhausted: ${daily:.4f} spent today "
            f"(cap: ${DAILY_BUDGET:.2f}). Resets at midnight UTC."
        )


def spend_summary() -> dict:
    """Return current spend status — used by the /spend endpoint."""
    daily = _load_daily_spend()
    return {
        "daily_spend_usd": round(daily, 4),
        "daily_budget_usd": DAILY_BUDGET,
        "daily_remaining_usd": round(max(0.0, DAILY_BUDGET - daily), 4),
        "daily_pct_used": round(100 * daily / DAILY_BUDGET, 1),
        "session_spend_usd": round(_session_spend, 4),
        "session_budget_usd": SESSION_BUDGET,
        "session_calls": _session_calls,
        "spend_log": str(SPEND_LOG),
        "date": _today(),
    }


# Log caps on import so they're visible in startup logs
log.info(
    "Spend guard active — daily cap: $%.2f | session cap: $%.2f | warn at %.0f%%",
    DAILY_BUDGET, SESSION_BUDGET, WARN_PCT * 100,
)
