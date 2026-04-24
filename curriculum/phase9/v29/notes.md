# v29 — Weights & Biases: ML Operations for AOIS

⏱ **Estimated time: 4–6 hours**

*Phase 9 — Production CI/CD and Platform Engineering. v28 automated deployments. v29 makes every prompt and model change measurable.*

---

## What This Version Builds

You changed the detect-node system prompt in v23.5. Severity accuracy went from 80% to 92%. How do you know it didn't regress on a specific incident category — database deadlocks, say, which had 100% accuracy before and now have 60%? How do you prove to your team that the change is safe to ship? How do you reproduce that 80% baseline three months from now when someone asks?

Without W&B: you have terminal output and git blame. With W&B: every eval run is an experiment with a URL, a full metric table, per-incident predictions color-coded by correctness, a diff against any prior run, and a trend line showing how accuracy has moved across every change you have made. The run that caused the regression is one click away.

AI systems differ from software systems in one critical way: the same code with a different prompt produces different behavior. You cannot track AI system quality with git alone — git tracks what changed, but not whether the change made things better or worse. W&B is the measurement layer.

By the end of v29:
- Every eval run produces a W&B experiment with aggregate metrics (accuracy, cost, latency) and a per-incident predictions table
- A/B test framework: compare Claude Haiku vs Sonnet vs Sonnet with extended thinking on the same golden dataset — the cost-accuracy-latency tradeoffs made quantitatively visible
- CI integration: every merge to `main` creates a W&B run automatically — accuracy trends across every code change
- You can answer "which commit caused the accuracy regression?" in under 2 minutes

---

## Prerequisites

```bash
# W&B account created (free tier at wandb.ai)
pip install wandb
wandb login
# Paste your API key from wandb.ai/settings → Danger Zone → API keys
```

Expected:
```
wandb: Logging into wandb.ai (Learn how to deploy a W&B server locally: https://wandb.me/wandb-server)
wandb: You can find your API key in your browser here: https://wandb.ai/authorize
wandb: Paste an API key from your profile and hit enter, or press ctrl+c to quit:
wandb: Appending key for api.wandb.ai to your netrc file: /home/collins/.netrc
```

Verify:
```bash
wandb verify
```

Expected:
```
Default host selected: https://api.wandb.ai
Find detailed logs for this run at: /tmp/verify-xxx
Verifying credentials...
✓ Credentials successfully verified!
```

```bash
# Eval suite from v23.5 is working
python3 evals/run_evals.py 2>&1 | tail -5
```

Expected:
```
AOIS AGENT EVAL REPORT
============================================================
Total incidents evaluated: 20
Severity accuracy: 90.0%  (SLO: ≥90%)   ✓ PASS
Safety rate:       100.0% (SLO: =100%)   ✓ PASS
```

```bash
# v28 GitHub Actions secrets are set
gh secret list | grep WANDB
# WANDB_API_KEY    Updated ...
```

If the W&B API key is not in GitHub secrets yet:
```bash
wandb_key=$(grep wandb_api_key ~/.netrc | awk '{print $6}' 2>/dev/null || cat ~/.netrc | grep -A2 'api.wandb.ai' | grep password | awk '{print $2}')
gh secret set WANDB_API_KEY --body "$wandb_key"
```

---

## Learning Goals

By the end of v29 you will be able to:

- Log every AOIS eval run as a W&B experiment with `wandb.init()`, `wandb.log()`, and `wandb.Table()` — the three primitives that handle 95% of ML tracking needs
- Use W&B's "Compare runs" feature to identify which specific prompt change caused an accuracy regression
- Run the A/B model comparison script and produce a W&B parallel coordinates plot showing accuracy vs. latency vs. cost for all three model configurations
- Set up W&B logging in the GitHub Actions CI pipeline so every merge automatically creates a W&B run — no manual tracking
- Explain what a W&B "sweep" is and the specific scenario where it applies to AOIS prompt optimization

---

## Part 1: Why Measure — The Problem With "It Seems Better"

Every AI change falls into one of three categories:

**Unmeasured changes**: "I tweaked the system prompt. It seems more accurate." The change ships. Three weeks later, accuracy on database incidents has dropped from 95% to 70%. No one knows when it happened or which change caused it. Investigation takes days.

**Measured changes at the wrong granularity**: "Accuracy is 91% overall." The change ships. The overall number looks fine but the aggregate masks a 70% rate on database incidents — which are exactly the incidents that get escalated to on-call. The regression is invisible in the aggregate.

**Measured changes at the right granularity**: "Overall accuracy is 91%. Breaking down by incident category: OOM 100%, CrashLoop 95%, Disk 90%, Database 70% — down from 95% last run." The regression is visible before the change ships. You fix the prompt, re-run, confirm database incidents are back to 95%, then merge.

W&B makes the third category the default. `wandb.Table` lets you see every incident, expected severity vs. actual severity, and whether it was correct — not just the aggregate. This is what "per-incident predictions" means.

---

## Part 2: The W&B Primitives

Three functions handle 95% of what you need in AOIS:

### `wandb.init()` — Start an Experiment

Every call to `wandb.init()` creates a new run in your W&B project. Think of a run as an experiment: one eval pass, one model configuration, one prompt version.

```python
wandb.init(
    project="aois-agent-evals",    # all AOIS eval runs go here
    name=f"eval-{prompt_version}", # human-readable name for this run
    config={                        # hyperparameters / configuration
        "prompt_version": prompt_version,
        "model": "claude-haiku-4-5-20251001",
        "golden_dataset_size": 20,
        "use_judge": use_judge,
    },
)
```

`config` is anything that defines the experiment — model name, prompt version, dataset size, any hyperparameter. W&B stores these alongside the metrics so you can filter runs by config and compare like-for-like.

### `wandb.log()` — Record Metrics

`wandb.log()` records scalar metrics for the current run. Call it once at the end with your aggregate results:

```python
wandb.log({
    "severity_accuracy": 0.90,
    "safety_rate": 1.0,
    "avg_latency_ms": 450.0,
    "total_cost_usd": 0.00180,
    "cost_per_incident": 0.000090,
    "slo_pass": True,               # boolean: did all SLOs pass?
})
```

Always log floats for numeric metrics, not strings. If run A logs `severity_accuracy: 0.90` and run B logs `severity_accuracy: "90%"`, W&B cannot plot them on the same axis or compute the diff.

### `wandb.Table()` — Per-Incident Predictions

This is the most valuable tool in AOIS. A W&B Table is a spreadsheet logged as part of the run — each row is one incident, each column is a field. You can filter, sort, and color-code cells in the W&B UI.

```python
table = wandb.Table(columns=[
    "incident_id",
    "incident",          # truncated log description
    "expected",          # ground truth severity (P1/P2/P3/P4)
    "actual",            # what the model predicted
    "correct",           # bool: expected == actual
    "latency_ms",
    "cost_usd",
])

for r in report.results:
    table.add_data(
        r.incident_id,
        r.incident_description[:100],   # truncate for readability
        r.expected_severity,
        r.actual_severity,
        r.severity_correct,
        round(r.latency_ms, 1),
        round(r.cost_usd, 8),
    )

wandb.log({"predictions": table})
```

In the W&B UI, the `predictions` table shows every incident. Rows where `correct` is `False` are the misclassified incidents — click on them to see the full log text and understand why the model got it wrong.

---

## Part 3: The Eval Runner with W&B Logging

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
    """Run the eval suite and log all results to W&B."""
    dataset = json.loads(GOLDEN_DATASET_PATH.read_text())

    wandb.init(
        project=WANDB_PROJECT,
        name=f"eval-{prompt_version}",
        config={
            "prompt_version": prompt_version,
            "model": "claude-haiku-4-5-20251001",
            "golden_dataset_size": len(dataset),
            "use_judge": use_judge,
            "git_sha": os.getenv("GITHUB_SHA", "local"),
        },
    )

    try:
        report = await run_evals(use_judge=use_judge)

        # Aggregate metrics
        wandb.log({
            "severity_accuracy": report.severity_accuracy,
            "safety_rate": report.safety_rate,
            "avg_latency_ms": report.avg_latency_ms,
            "total_cost_usd": report.total_cost_usd,
            "cost_per_incident": report.total_cost_usd / len(report.results),
            "slo_pass": (
                report.severity_accuracy >= 0.90
                and report.safety_rate == 1.0
            ),
        })

        # Per-incident predictions table
        table = wandb.Table(columns=[
            "incident_id", "incident", "expected", "actual",
            "correct", "latency_ms", "cost_usd",
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

        # Accuracy broken down by incident category
        categories = {}
        for r in report.results:
            cat = r.incident_category  # e.g., "oom", "database", "network"
            if cat not in categories:
                categories[cat] = {"correct": 0, "total": 0}
            categories[cat]["total"] += 1
            if r.severity_correct:
                categories[cat]["correct"] += 1

        category_metrics = {
            f"accuracy_{cat}": data["correct"] / data["total"]
            for cat, data in categories.items()
        }
        wandb.log(category_metrics)

        report.print_summary()
        return report

    finally:
        wandb.finish()   # ALWAYS call finish, even on exception


if __name__ == "__main__":
    import sys
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    asyncio.run(run_and_log(prompt_version=version))
```

**Why `finally: wandb.finish()`**: if the eval throws an exception, W&B needs `finish()` to be called or the run stays in "running" state forever in the W&B UI. You will see phantom runs that look active but are actually failed. Always call `wandb.finish()` in a `finally` block.

**Why `git_sha` in config**: when this runs in GitHub Actions, `GITHUB_SHA` is set to the commit SHA. When you see a W&B run, you can map it directly to a git commit and see exactly what code was running when the accuracy was 87% vs. 92%.

---

## ▶ STOP — do this now: Your First W&B Run

Run the eval with W&B logging:

```bash
python3 evals/run_evals_wandb.py v1
```

Expected:
```
wandb: Currently logged in as: your-username. Use `wandb login --relogin` to force relogin
wandb: Tracking run with wandb version 0.16.x
wandb: Run data is saved locally in wandb/run-20260424_100000-abc123
wandb: Run `wandb offline` to turn off syncing.
wandb: Syncing run eval-v1 to Weights & Biases (docs)
wandb: ⭐️ View project at https://wandb.ai/your-username/aois-agent-evals

...

AOIS AGENT EVAL REPORT
============================================================
Total incidents evaluated: 20
Severity accuracy: 90.0%  (SLO: ≥90%)   ✓ PASS
Safety rate:       100.0% (SLO: =100%)   ✓ PASS
Avg latency:       450ms
Total cost:        $0.001800

wandb: Waiting for W&B process to finish... (success).
wandb: Run history:
wandb:   severity_accuracy  0.90
wandb:   safety_rate        1.00
wandb:   avg_latency_ms   450.00
wandb:   total_cost_usd     0.0018
wandb: View run eval-v1 at: https://wandb.ai/your-username/aois-agent-evals/runs/abc123
```

Open the W&B URL. You will see:
- A metrics panel with accuracy, latency, cost
- A `predictions` table with all 20 incidents, expected vs. actual, color-coded by `correct`

Look at the misclassified incidents in the table. These are your improvement targets — what is the model getting wrong, and what do those logs have in common?

Now run a second eval with a slightly different prompt. Change one line in the detect-node system prompt (add "Focus especially on database and memory errors" at the end). Then run:

```bash
python3 evals/run_evals_wandb.py v2
```

Expected (similar output with a different run URL).

In W&B: navigate to the project, select both runs (`eval-v1` and `eval-v2`), click "Compare". You will see a side-by-side table of all metrics and a diff for each. If accuracy improved for some categories and degraded for others, you can see it immediately.

---

## Part 4: A/B Model Comparison

The A/B test answers the most important question in AI system design: **what is the cost-accuracy-latency tradeoff between models?**

The intuition: Claude Haiku is cheap and fast but less accurate. Claude Sonnet is more accurate but costs more and is slower. Claude Sonnet with extended thinking is the most accurate but costs 10-50× more than Sonnet. Which model is right for which incident tier?

```python
# evals/ab_test_models.py
"""Compare model configurations on the golden dataset."""
import asyncio
import json
import os
import re
import time
import wandb
import anthropic
from pathlib import Path

_dataset = json.loads(
    (Path(__file__).parent / "golden_dataset.json").read_text()
)
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Three configurations to compare
MODELS = [
    {
        "name": "haiku-4-5",
        "model": "claude-haiku-4-5-20251001",
        "thinking": False,
        "description": "Fast, cheap — current P3/P4 tier",
    },
    {
        "name": "sonnet-4-6",
        "model": "claude-sonnet-4-6",
        "thinking": False,
        "description": "Balanced — current P1/P2 tier",
    },
    {
        "name": "sonnet-4-6-thinking",
        "model": "claude-sonnet-4-6",
        "thinking": True,
        "description": "Extended thinking — premium accuracy",
    },
]


def classify_incident(incident: str, model: str, thinking: bool) -> tuple[str, float, float]:
    """Classify one incident. Returns (severity, latency_ms, cost_usd)."""
    t0 = time.perf_counter()

    kwargs = {
        "model": model,
        "max_tokens": 1024 if thinking else 256,
        "messages": [{
            "role": "user",
            "content": (
                f"Classify the severity (P1-P4) of this infrastructure incident. "
                f"P1=critical (production down), P2=high (degraded), "
                f"P3=medium (non-critical affected), P4=low (cosmetic/informational).\n\n"
                f"Incident: {incident}\n\n"
                f"Return JSON only: {{\"severity\": \"P1\"|\"P2\"|\"P3\"|\"P4\"}}"
            ),
        }],
    }

    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 512}

    resp = _client.messages.create(**kwargs)
    latency_ms = (time.perf_counter() - t0) * 1000

    text = next((b.text for b in resp.content if hasattr(b, "text")), "{}")
    try:
        match = re.search(r'\{"severity":\s*"(P[1-4])"\}', text)
        severity = match.group(1) if match else "P3"
    except Exception:
        severity = "P3"

    # Cost calculation per model pricing
    if "haiku" in model:
        cost = (resp.usage.input_tokens * 0.25 + resp.usage.output_tokens * 1.25) / 1_000_000
    elif thinking:
        cost = (resp.usage.input_tokens * 3.0 + resp.usage.output_tokens * 15.0) / 1_000_000
    else:
        cost = (resp.usage.input_tokens * 3.0 + resp.usage.output_tokens * 15.0) / 1_000_000

    return severity, latency_ms, cost


async def ab_test():
    """Run all three model configurations and log results to W&B."""
    print(f"Running A/B test on {len(_dataset)} incidents across {len(MODELS)} model configurations...")
    print("This will take ~2-5 minutes and cost approximately $0.05.\n")

    for cfg in MODELS:
        print(f"Testing {cfg['name']}...")
        wandb.init(
            project="aois-model-ab",
            name=cfg["name"],
            config=cfg,
        )

        try:
            correct = 0
            total = 0
            total_cost = 0.0
            total_latency = 0.0

            table = wandb.Table(columns=[
                "incident_id", "incident", "expected", "actual",
                "correct", "latency_ms", "cost_usd",
            ])

            for entry in _dataset:
                severity, latency, cost = classify_incident(
                    entry["incident_description"],
                    cfg["model"],
                    cfg["thinking"],
                )

                is_correct = severity == entry["expected_severity"]
                if is_correct:
                    correct += 1
                total += 1
                total_cost += cost
                total_latency += latency

                table.add_data(
                    entry["incident_id"],
                    entry["incident_description"][:80],
                    entry["expected_severity"],
                    severity,
                    is_correct,
                    round(latency, 1),
                    round(cost, 8),
                )

            accuracy = correct / total
            avg_latency = total_latency / total
            cost_per_incident = total_cost / total

            wandb.log({
                "severity_accuracy": accuracy,
                "avg_latency_ms": avg_latency,
                "total_cost_usd": total_cost,
                "cost_per_incident": cost_per_incident,
                "predictions": table,
            })

            print(
                f"  {cfg['name']:25s}: acc={accuracy:.1%}  "
                f"latency={avg_latency:.0f}ms  "
                f"cost/incident=${cost_per_incident:.6f}"
            )

        finally:
            wandb.finish()

    print("\nA/B test complete. View results at https://wandb.ai/your-username/aois-model-ab")


if __name__ == "__main__":
    asyncio.run(ab_test())
```

---

## ▶ STOP — do this now: Run the A/B Model Comparison

This costs approximately $0.05 and takes 3–5 minutes:

```bash
python3 evals/ab_test_models.py
```

Expected output:
```
Running A/B test on 20 incidents across 3 model configurations...
This will take ~2-5 minutes and cost approximately $0.05.

Testing haiku-4-5...
  haiku-4-5                : acc=90.0%  latency=380ms   cost/incident=$0.000009
Testing sonnet-4-6...
  sonnet-4-6               : acc=95.0%  latency=720ms   cost/incident=$0.000042
Testing sonnet-4-6-thinking...
  sonnet-4-6-thinking      : acc=100.0% latency=4200ms  cost/incident=$0.000420

A/B test complete. View results at https://wandb.ai/your-username/aois-model-ab
```

Open W&B and navigate to the `aois-model-ab` project. Select all three runs and use "Compare":

**Parallel Coordinates plot**: select `severity_accuracy`, `avg_latency_ms`, and `cost_per_incident` as axes. Each line is one model configuration. You can see the tradeoff visually: extended thinking has a vertical line near the top of accuracy but also near the top of cost and latency.

**Decision framework** (what this analysis produces):

| Incident Tier | Model | Justification |
|---|---|---|
| P3/P4 volume | Haiku | $0.000009/incident, 380ms, 90% accuracy — good enough, cheap |
| P1/P2 critical | Sonnet | $0.000042/incident, 720ms, 95% accuracy — better accuracy, still fast |
| P1 with ambiguity | Sonnet + thinking | $0.000420/incident, 4.2s, 100% — when it absolutely cannot be wrong |

This is the routing logic already implemented in AOIS (v2 LiteLLM tiers). The A/B test gives you the numbers to defend it.

---

## Part 5: CI Integration — Auto-Log on Every Merge

Add W&B logging to the GitHub Actions pipeline so every merge to `main` creates a W&B run:

```yaml
# In .github/workflows/ci.yml, in the lint-test job:
      - name: Run agent evals with W&B logging
        run: python3 evals/run_evals_wandb.py ${{ github.sha }}
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          WANDB_API_KEY: ${{ secrets.WANDB_API_KEY }}
          WANDB_PROJECT: aois-agent-evals
```

Using `github.sha` as the `prompt_version` argument means each run is labeled with the commit SHA. The W&B project page becomes a timeline of every merge, with accuracy at each point. When you click on any run, you see `config.git_sha`, which you can look up in git to see exactly what changed.

After pushing this change, verify it works:

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add W&B logging to eval step"
git push

# Watch the CI run
gh run watch

# After it completes, check W&B
# Expected: a new run named "eval-<sha>" appears in the aois-agent-evals project
```

---

## Part 6: Investigating an Accuracy Regression

The scenario: you changed a prompt two weeks ago and accuracy dropped. You need to find which commit caused it.

**Step 1**: In W&B, open the `aois-agent-evals` project. The main chart shows `severity_accuracy` over time (one data point per run, one run per commit). Find the point where accuracy dropped.

**Step 2**: Click the run just before the drop and the run just after. Use "Compare runs." The config shows `git_sha` for both.

**Step 3**: In git:
```bash
git log --oneline <sha_before>..<sha_after>
```

Expected — one or a few commits in this range:
```
abc1234 refactor: update detect_node system prompt for clarity
def5678 fix: add timeout handling in consumer
```

**Step 4**: check which commit touched prompts:
```bash
git show abc1234 -- main.py | grep -A5 "system prompt"
```

**Step 5**: You have identified the change. Now test the fix:
```bash
# Revert or adjust the prompt, run locally
python3 evals/run_evals_wandb.py fix-candidate
# Check W&B — did accuracy recover?
```

This investigation took under 5 minutes. Without W&B, it would have taken hours of reading terminal logs and git blame across multiple files.

---

## Part 7: W&B Sweeps — When They Apply to AOIS

A W&B sweep runs your eval function across multiple configurations automatically, searching for the best combination. Example: find the optimal system prompt + model + temperature combination for P1 accuracy.

```python
# evals/sweep_config.yaml
program: evals/run_evals_wandb.py
method: grid    # exhaustive grid search (vs. random or bayesian)
parameters:
  prompt_version:
    values: [v1, v2, v3]
  model:
    values: ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
```

```bash
wandb sweep evals/sweep_config.yaml
# Expected: wandb: Creating sweep with ID: abc123
wandb agent your-username/aois-agent-evals/abc123
```

The agent runs every combination (3 prompt versions × 2 models = 6 runs) and logs each to W&B. The sweep page shows which combination produced the highest accuracy. This is **eval-driven prompt development**: instead of hand-tweaking prompts and guessing, you enumerate candidates and measure.

**When sweeps apply to AOIS:**
- You have 3+ candidate system prompts and want to find the best one systematically
- You are exploring whether to add few-shot examples and want to measure the accuracy impact
- You are testing different temperature values (0.0 vs 0.3 vs 0.7) for severity classification

**When sweeps do NOT apply:**
- Single prompt iteration (just run `run_evals_wandb.py` directly)
- Model version upgrades (use the A/B test script)
- Cost optimization (that is the LiteLLM routing problem, not a sweep)

---

## ▶ STOP — do this now: Investigate a Regression Using W&B

Simulate a prompt regression and trace it through W&B:

```python
import wandb, os, json
from pathlib import Path
from evals.run_evals import run_evals

# Run 1: current model/prompt (baseline)
run1 = wandb.init(project="aois-evals", name="baseline-check", config={"model": "claude-haiku-4-5-20251001"})
results1 = run_evals(model="claude-haiku-4-5-20251001")
wandb.log({"severity_accuracy": results1.severity_accuracy, "safety_rate": results1.safety_rate})
wandb.finish()

# Run 2: simulate a "regressed" prompt — remove the severity scale from the system prompt
# (edit main.py temporarily, re-run evals, observe the drop)
print(f"Baseline accuracy: {results1.severity_accuracy:.1%}")
print("Now open wandb.ai and look at the two runs side by side.")
print("The Accuracy panel should show the drop. This is how regressions are caught.")
```

Then open your W&B project at `wandb.ai/<your-username>/aois-evals`. You should see:
```
Run: baseline-check    severity_accuracy: 0.90    safety_rate: 1.00
```

In a real regression scenario, the second run would show `severity_accuracy: 0.70` — the visual drop in the W&B chart is what triggers investigation. Without W&B, you would only know something was wrong when an engineer notices wrong severities in production.

This is the exact workflow when a model provider silently changes a model version: you see accuracy drop in W&B before any production alert fires.

---

## Common Mistakes

### 1. Forgetting `wandb.finish()` — Phantom Running Runs

**Symptom**: the W&B project shows a run in "running" state even though your script has exited. The run never shows its final metrics.

**Cause**: `wandb.finish()` was not called, or the script crashed before it was reached.

**Fix**: always use a `try/finally`:
```python
wandb.init(project="...", name="...")
try:
    # ... do work ...
    wandb.log({...})
finally:
    wandb.finish()   # called even if an exception is raised
```

### 2. Logging Mixed Types for the Same Metric Key

**Symptom**: in W&B, the chart for `severity_accuracy` shows some runs on the axis but others missing. Or "Compare runs" shows one run's accuracy but not another's.

**Exact cause**: one run logged `severity_accuracy: 0.90` (float), another logged `severity_accuracy: "90%"` (string). W&B cannot plot mixed types on the same axis.

**Fix**: always log the same Python type for the same key across all runs. For accuracy: always `float` between 0.0 and 1.0. Never a percentage string.

```python
# Wrong
wandb.log({"severity_accuracy": "90.0%"})

# Correct
wandb.log({"severity_accuracy": 0.90})
```

### 3. W&B Runs Appear in Wrong Project

**Symptom**: you expected runs to appear in `aois-agent-evals` but they appear in a different project (or a new project gets created).

**Cause**: `WANDB_PROJECT` environment variable is set to something other than what you passed to `wandb.init()`. The environment variable takes precedence over the argument.

**Fix**: check for conflicting env vars:
```bash
echo $WANDB_PROJECT
```

If it is set, either unset it (`unset WANDB_PROJECT`) or make sure the `wandb.init()` call matches.

### 4. A/B Test Costs More Than Expected — Forgetting Rate Limits

**Symptom**: the A/B test takes much longer than expected, or some requests fail with `RateLimitError`.

**Cause**: extended thinking with Claude Sonnet consumes significantly more tokens than standard mode — each request uses 512 thinking tokens plus the response tokens. At high request rates, you hit the rate limit.

**Fix**: add a small delay between requests for the extended thinking configuration:
```python
if thinking:
    time.sleep(0.5)   # avoid rate limit with extended thinking
```

Or reduce the dataset to a 10-incident subset for the extended thinking run:
```python
if thinking:
    dataset_to_test = _dataset[:10]  # save tokens
else:
    dataset_to_test = _dataset
```

### 5. `wandb.Table` Too Large — Slow UI

**Symptom**: the W&B Table takes 30+ seconds to load in the browser.

**Cause**: the `incident` column contains full log text (sometimes hundreds of characters per row). With 50+ incidents, the table payload is large.

**Fix**: always truncate string columns before logging:
```python
table.add_data(
    r.incident_id,
    r.incident_description[:100],  # ← truncate, not the full string
    ...
)
```

---

## Troubleshooting

### `wandb: ERROR No such file or directory: 'wandb/latest-run'`

W&B has not been initialized in this directory yet. Run `wandb login` (to authenticate) and then `wandb init` (to set up the local directory).

```bash
wandb login
wandb init --project aois-agent-evals
```

Expected:
```
This directory is configured!
Enter the project name (auto-complete enabled):  aois-agent-evals
```

### Runs Not Appearing in the Project

First, check the project name is correct:

```bash
# In the script
wandb.init(project="aois-agent-evals", ...)
# In the W&B UI URL: https://wandb.ai/your-username/aois-agent-evals
```

W&B project names are case-sensitive. `aois-Agent-Evals` is a different project from `aois-agent-evals`.

Second, check whether W&B is in offline mode:

```bash
wandb status
```

If it shows `Offline mode: True`, runs are being saved locally but not synced. Turn off offline mode:

```bash
wandb online
```

Then sync existing offline runs:

```bash
wandb sync wandb/
```

### CI W&B Step Fails With `WANDB_API_KEY not set`

Check that the secret is set in GitHub:

```bash
gh secret list | grep WANDB
```

If missing:
```bash
gh secret set WANDB_API_KEY --body "$(python3 -c "import netrc; print(netrc.netrc().authenticators('api.wandb.ai')[2])")"
```

Or get the key from the W&B UI: Settings → API Keys → copy.

### `anthropic.APIStatusError: 529 Overloaded` During A/B Test

The Claude API is temporarily overloaded. The A/B test has no retry logic by default.

**Fix**: add exponential backoff:
```python
import time
for attempt in range(3):
    try:
        resp = _client.messages.create(**kwargs)
        break
    except anthropic.APIStatusError as e:
        if e.status_code == 529 and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        raise
```

---

## Connection to Later Phases

**v33 (Red-teaming)**: adversarial test results log to a separate W&B project (`aois-redteam`). Every red-team session produces a W&B run with: jailbreak success rate, prompt injection success rate, output safety violations. The trend line shows whether the system is getting more or less robust to attack as you make changes.

**v34.5 (Capstone)**: W&B shows the complete quality history of AOIS from the first eval run in v23.5 through every subsequent change. The trend line of `severity_accuracy` across every commit is the evidence that the system improved systematically, not by luck. The A/B model comparison chart is the evidence that model routing decisions were made based on data, not preference. This is what "production-grade AI" looks like in a portfolio.

---

## Mastery Checkpoint

You have completed v29 when you can do all of the following:

1. **Two-run comparison**: run `run_evals_wandb.py v1` and `run_evals_wandb.py v2` with two slightly different prompts. Open W&B and use "Compare runs" to show the accuracy diff. Identify which incident categories improved and which degraded.

2. **A/B model test**: run `ab_test_models.py`. Produce the W&B parallel coordinates chart showing accuracy vs. latency vs. cost for all three model configurations. State the routing decision the data supports.

3. **CI auto-logging**: with `WANDB_API_KEY` in GitHub Actions secrets, push a commit and confirm a new W&B run appears automatically after the CI job completes. Show the run URL.

4. **Regression investigation**: simulate a regression by changing a prompt to a worse version, running `run_evals_wandb.py v3`, and using W&B to identify which incident categories regressed compared to `v2`. Walk through the investigation steps.

5. **Product manager question**: explain to a product manager why tracking prompt changes in W&B is more valuable than tracking them in git commit messages. What specific question does W&B answer that git cannot? (Expected answer: git tells you what changed; W&B tells you whether the change made things better or worse, and for which specific incidents.)

6. **Senior engineer question**: a senior engineer asks: "We changed the detect prompt 3 weeks ago and accuracy dropped. Can you show me which commit caused it?" Walk through exactly how you would investigate this using W&B — the specific UI features and the correlation back to git.

7. **Sweep design**: design (in words, no code required) a W&B sweep to find the optimal system prompt from three candidates across two model tiers. Define: the sweep parameters, the metric being optimized, the number of runs the sweep produces, and the one question the sweep answers that manual testing cannot.

**The mastery bar:** every prompt change, every model update, every eval run produces a W&B experiment. You can compare any two runs side-by-side and identify accuracy regressions down to the specific incident category. The trend line over time is the evidence that AOIS quality is improving, not degrading. This is the difference between "we think it got better" and "we measured that it got better."

---

## 4-Layer Tool Understanding

---

### Weights & Biases

| Layer | |
|---|---|
| **Plain English** | You changed the AOIS prompt and "it seems better." W&B turns "seems better" into "severity accuracy improved from 90.2% to 94.5%, latency decreased by 80ms, cost increased by $0.000009 per incident." Every change is a measured experiment, not a guess. You can prove any quality claim. |
| **System Role** | Between the eval runner and human decision-making. The eval runner produces numbers; W&B stores them, trends them, and makes them comparable across every code change. Integrated into CI via the `WANDB_API_KEY` secret: every merge creates a W&B run automatically. The W&B project is the quality audit trail for AOIS. |
| **Technical** | An ML experiment tracking platform. `wandb.init()` creates a run. `wandb.log()` records metrics as key-value pairs. `wandb.Table()` records structured tabular data (per-incident predictions). `wandb.finish()` closes the run. Runs are grouped by project. The W&B UI provides: metric time-series plots, run comparison tables, parallel coordinates charts (for multi-dimensional tradeoff visualization), and artifact versioning for datasets and model weights. |
| **Remove it** | Remove W&B → eval results are terminal output and JSON files. To compare two prompt versions: read two JSON files, write a comparison script, or try to remember what you saw last week. After 10 prompt iterations, you have no idea which was best, which categories degraded, or when the last regression was introduced. W&B is the collective memory for every experiment the team has run. Without it, AI system development regresses to guessing. |

**Say it at three levels:**

- *Non-technical:* "W&B is the scoreboard for every experiment we run. When we try a new prompt or a new model, W&B shows us the score — and lets us compare it against every previous score. We always know if we're getting better or worse."

- *Junior engineer:* "`wandb.init(project='aois-agent-evals', name='eval-v2')` starts a run. `wandb.log({'severity_accuracy': 0.92})` records the metric. `wandb.Table(columns=[...])` logs per-row data. `wandb.finish()` closes the run. The run appears at `https://wandb.ai/username/project/runs/id`. Every run is persistent — you can come back to it months later."

- *Senior engineer:* "W&B is the observability layer for the model layer. The same way Grafana makes infrastructure health visible, W&B makes model quality visible. The critical pattern: log `git_sha` in `wandb.init(config=...)` — this creates a bidirectional link between any W&B run and the exact code that produced it. When investigating a regression, the W&B timeline shows when accuracy dropped; the `git_sha` in config shows which commit to look at. Without this link, you are correlation-hunting across two independent systems. With it, the causal chain is one click."
