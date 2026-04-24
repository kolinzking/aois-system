"""Eval runner with W&B logging — wraps run_evals.py."""
import asyncio
import json
import os
import sys
import wandb
from pathlib import Path
from evals.run_evals import run_evals, GOLDEN_DATASET_PATH

WANDB_PROJECT = os.getenv("WANDB_PROJECT", "aois-agent-evals")


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

    try:
        report = await run_evals(use_judge=use_judge)

        wandb.log({
            "severity_accuracy": report.severity_accuracy,
            "safety_rate": report.safety_rate,
            "avg_latency_ms": report.avg_latency_ms,
            "total_cost_usd": report.total_cost_usd,
            "slo_pass": int(report.severity_accuracy >= 0.90 and report.safety_rate == 1.0),
        })

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
        return report
    finally:
        wandb.finish()


if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    asyncio.run(run_and_log(prompt_version=version))
