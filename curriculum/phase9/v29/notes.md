# v29 — Weights & Biases: ML Operations for AOIS

⏱ **Estimated time: 4–6 hours**

---

## Prerequisites

v28 CI pipeline passing. W&B account created (free tier).

```bash
pip install wandb
wandb login
# Paste API key from wandb.ai/settings
# wandb: Currently logged in as: your-username
```

---

## Learning Goals

By the end you will be able to:

- Log every AOIS prompt version as a W&B run with metrics: latency, cost, severity_accuracy
- A/B test Claude standard vs extended thinking vs fine-tuned model — compare on the same golden dataset
- Use W&B Tables to inspect per-incident predictions vs ground truth
- Set up automatic W&B logging inside the GitHub Actions CI pipeline
- Explain what a W&B "sweep" is and when it applies to prompt optimization

---

## The Problem

You changed the detect_node system prompt in v23.5 and severity_accuracy went from 80% to 92%. How do you know it did not regress on a different incident category? How do you reproduce the 80% result next month when someone asks? How do you compare three prompt versions side-by-side?

Without W&B: you have terminal output and git blame. With W&B: every eval run is an experiment with a URL, a full metric table, per-incident predictions, and a diff against any prior run.

---

## Logging Eval Runs to W&B

```python
# evals/run_evals_wandb.py
"""Eval runner with W&B logging — wraps run_evals.py."""
import asyncio
import json
import os
import wandb
from pathlib import Path
from evals.run_evals import run_evals, GOLDEN_DATASET_PATH

WANDB_PROJECT = "aois-agent-evals"


async def run_and_log(prompt_version: str = "v1", use_judge: bool = False):
    wandb.init(
        project=WANDB_PROJECT,
        name=f"eval-{prompt_version}",
        config={
            "prompt_version": prompt_version,
            "model": "claude-haiku-4-5-20251001",
            "golden_dataset_size": len(json.loads(GOLDEN_DATASET_PATH.read_text())),
            "use_judge": use_judge,
        },
    )

    report = await run_evals(use_judge=use_judge)

    # Log aggregate metrics
    wandb.log({
        "severity_accuracy": report.severity_accuracy,
        "safety_rate": report.safety_rate,
        "avg_latency_ms": report.avg_latency_ms,
        "total_cost_usd": report.total_cost_usd,
        "slo_pass": report.severity_accuracy >= 0.90 and report.safety_rate == 1.0,
    })

    # Log per-incident predictions as a W&B Table
    table = wandb.Table(columns=[
        "incident_id", "incident", "expected", "actual", "correct", "latency_ms", "cost_usd"
    ])
    for r in report.results:
        table.add_data(
            r.incident_id,
            r.incident_description[:100],
            r.expected_severity,
            r.actual_severity,
            r.severity_correct,
            round(r.latency_ms, 1),
            round(r.cost_usd, 8),
        )
    wandb.log({"predictions": table})

    report.print_summary()
    wandb.finish()
    return report


if __name__ == "__main__":
    import sys
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    asyncio.run(run_and_log(prompt_version=version))
```

---

## ▶ STOP — do this now

Run the eval with W&B logging:

```bash
python3 evals/run_evals_wandb.py v1
```

Expected:
```
wandb: Run data is saved locally in wandb/run-xxx
wandb: Run `wandb offline` to turn off syncing.
...
AOIS AGENT EVAL REPORT
============================================================
Total incidents evaluated: 20
Severity accuracy: 90.0%  (SLO: ≥90%)
...
wandb: Waiting for W&B process to finish...
wandb: View run at: https://wandb.ai/your-username/aois-agent-evals/runs/xxx
```

Open the W&B URL. You will see:
- Accuracy, latency, cost trend line
- The `predictions` table with every incident, expected vs actual, color-coded by correctness

Now change the detect_node system prompt slightly and run again as v2:

```bash
python3 evals/run_evals_wandb.py v2
```

In W&B, use the "Compare runs" feature to see the diff in accuracy between v1 and v2.

---

## A/B Testing: Haiku vs Extended Thinking

```python
# evals/ab_test_models.py
"""Compare claude-haiku vs claude-sonnet with extended thinking on the golden dataset."""
import asyncio, json, time, wandb, anthropic, os, re
from pathlib import Path

_dataset = json.loads((Path(__file__).parent / "golden_dataset.json").read_text())
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODELS = [
    {"name": "haiku-4-5", "model": "claude-haiku-4-5-20251001", "thinking": False},
    {"name": "sonnet-4-6", "model": "claude-sonnet-4-6", "thinking": False},
    {"name": "sonnet-4-6-thinking", "model": "claude-sonnet-4-6", "thinking": True},
]


def classify(incident: str, model: str, thinking: bool) -> tuple[str, float, float]:
    t0 = time.perf_counter()
    kwargs = {
        "model": model,
        "max_tokens": 1024 if thinking else 256,
        "messages": [{"role": "user", "content": (
            f"Classify severity (P1-P4) for: {incident}\n"
            f'Return JSON: {{"severity": "P1|P2|P3|P4"}}'
        )}],
    }
    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 512}

    resp = _client.messages.create(**kwargs)
    latency = (time.perf_counter() - t0) * 1000
    text = next((b.text for b in resp.content if hasattr(b, "text")), "{}")
    try:
        sev = json.loads(re.search(r'\{[^{}]+\}', text, re.DOTALL).group()).get("severity", "P3")
    except Exception:
        sev = "P3"
    cost = (resp.usage.input_tokens * 3.0 + resp.usage.output_tokens * 15.0) / 1_000_000
    return sev, latency, cost


async def ab_test():
    for cfg in MODELS:
        wandb.init(project="aois-model-ab", name=cfg["name"], config=cfg)
        correct = total = 0
        total_cost = total_latency = 0

        for entry in _dataset:
            sev, latency, cost = classify(entry["incident_description"], cfg["model"], cfg["thinking"])
            if sev == entry["expected_severity"]:
                correct += 1
            total += 1
            total_cost += cost
            total_latency += latency

        wandb.log({
            "severity_accuracy": correct / total,
            "avg_latency_ms": total_latency / total,
            "total_cost_usd": total_cost,
            "cost_per_incident": total_cost / total,
        })
        print(f"{cfg['name']}: acc={correct/total:.1%} latency={total_latency/total:.0f}ms cost=${total_cost:.6f}")
        wandb.finish()


if __name__ == "__main__":
    asyncio.run(ab_test())
```

---

## ▶ STOP — do this now

Run the A/B test (costs ~$0.05 with extended thinking):

```bash
python3 evals/ab_test_models.py
```

Expected comparison:
```
haiku-4-5:           acc=90.0%  latency=380ms   cost=$0.000180
sonnet-4-6:          acc=95.0%  latency=720ms   cost=$0.000840
sonnet-4-6-thinking: acc=100.0% latency=4200ms  cost=$0.008400
```

This is the cost-accuracy tradeoff made visible. Extended thinking wins on accuracy but costs 46× more. The right call: Haiku for P3/P4 classification (high volume, good enough), Sonnet for P1/P2 (low volume, accuracy matters).

In W&B: use the "parallel coordinates" plot to visualize all three dimensions simultaneously.

---

## CI Integration: Auto-log Evals on Every Merge

Add to `.github/workflows/ci.yml`:

```yaml
- name: Run evals and log to W&B
  run: python3 evals/run_evals_wandb.py ${{ github.sha }}
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    WANDB_API_KEY: ${{ secrets.WANDB_API_KEY }}
    WANDB_PROJECT: aois-agent-evals
```

Now every merge to main creates a W&B run. The W&B project page shows accuracy trending over time across every code change.

---

## Common Mistakes

### 1. Forgetting `wandb.finish()` — run stays in "running" state

Always call `wandb.finish()` even if an exception occurs:

```python
try:
    wandb.init(...)
    # ... work ...
    wandb.log({...})
finally:
    wandb.finish()
```

### 2. Logging the same metric key with different types across runs

If run A logs `severity_accuracy: 0.90` (float) and run B logs `severity_accuracy: "90%"` (string), W&B cannot compare them. Always log floats for numeric metrics.

---

## Troubleshooting

### `wandb: ERROR No such file or directory: 'wandb/latest-run'`

W&B has not been initialized in this directory yet. Run `wandb login` and then `wandb init` in the project root.

### Runs not appearing in the project

Check `WANDB_PROJECT` matches exactly (case-sensitive) between the script and the W&B UI.

---

## Connection to Later Phases

### To v33 (Red-teaming): adversarial test results logged to a separate W&B project. Track: jailbreak success rate, poison injection success rate, per-model robustness score.
### To v34.5 (Capstone): W&B shows the full history of AOIS quality from v1 to capstone. The trend line is the evidence that the system improved systematically, not by guess.

---

## Mastery Checkpoint

1. Run `python3 evals/run_evals_wandb.py v1` and `v2` with two different prompts. Open W&B and use "Compare runs" to show the accuracy diff between the two.
2. Run `python3 evals/ab_test_models.py`. Produce the W&B parallel coordinates chart showing accuracy vs latency vs cost for all three models.
3. Add WANDB_API_KEY to GitHub Actions secrets. Push a commit and confirm a new W&B run appears automatically after the CI merge job.
4. Explain to a product manager why tracking prompt changes in W&B is more valuable than tracking them in git commit messages. What specific question does W&B answer that git cannot?
5. A senior engineer asks: "We changed the detect prompt 3 weeks ago and accuracy dropped. Can you show me which commit caused it?" Walk through exactly how you would investigate this with W&B.

**The mastery bar:** every prompt change produces a W&B run with accuracy, latency, and cost. You can compare any two runs side-by-side and identify regressions before they reach production.

---

## 4-Layer Tool Understanding

### Weights & Biases

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | You changed the AOIS prompt and "it seems better." W&B turns "seems better" into "accuracy improved from 90.2% to 94.5%, latency decreased by 80ms, cost increased by $0.0002 per incident." Every change is a measured experiment, not a guess. |
| **System Role** | Where does it sit in AOIS? | Between the eval runner and human decision-making. The eval runner produces numbers; W&B stores them, trends them, and makes them comparable across every code change. Integrated into CI: every merge creates a W&B run automatically. |
| **Technical** | What is it precisely? | An ML experiment tracking platform. `wandb.init()` creates a run. `wandb.log()` records metrics. `wandb.Table()` records per-row data (per-incident predictions). Runs are grouped by project. The W&B UI provides: metric trends, run comparison, scatter plots, parallel coordinates, artifact versioning. |
| **Remove it** | What breaks, and how fast? | Remove W&B → eval results are terminal output and JSON files. To compare two prompt versions: read two JSON files, write a comparison script, or remember what you saw last week. After 10 prompt iterations, you have no idea which was best. W&B is the memory for every experiment the team has run. |
