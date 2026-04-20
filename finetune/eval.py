"""
v15 — Evaluation: fine-tuned TinyLlama vs base TinyLlama vs Claude Haiku.

Runs the 50 held-out eval samples through all three models and scores each on:
  - json_valid: did the model return parseable JSON?
  - fields_present: are all 4 required fields present?
  - severity_match: does severity match the Claude-generated ground truth?
  - confidence_valid: is confidence a float in [0.0, 1.0]?

Usage:
    python3 finetune/eval.py
"""

import json
import os
import time
from pathlib import Path

EVAL_PATH = Path("finetune/sre_eval.jsonl")

SYSTEM_PROMPT = """You are an expert SRE at a large technology company. Given an infrastructure log message, provide a concise structured analysis as valid JSON with exactly these fields:
- summary: one sentence describing what is happening
- severity: exactly one of P1, P2, P3, P4
- suggested_action: specific actionable remediation step
- confidence: number between 0.0 and 1.0

P1 = production down / data loss risk
P2 = degraded / will break within 1 hour without action
P3 = warning / action needed within 24 hours
P4 = informational / preventive maintenance

Respond with only the JSON object, no other text."""


# ---------------------------------------------------------------------------
# Modal side — runs on A10G GPU
# ---------------------------------------------------------------------------
import modal

BASE_DIR = "/models/tinyllama-1b"
LORA_DIR = "/models/tinyllama-sre-lora"
MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"

tinyllama_volume = modal.Volume.from_name("aois-tinyllama-weights", create_if_missing=False)
lora_volume = modal.Volume.from_name("aois-lora-weights", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.3.1",
        "transformers==4.43.4",
        "tokenizers==0.19.1",
        "peft==0.11.1",
        "datasets==2.20.0",
        "accelerate==0.31.0",
        "sentencepiece",
        "huggingface_hub",
    )
)

app = modal.App("aois-eval", image=image)


@app.function(
    gpu="a10g",
    timeout=1800,
    volumes={
        BASE_DIR: tinyllama_volume,
        LORA_DIR: lora_volume,
    },
)
def run_model_eval(eval_data: list[dict]) -> dict:
    """Score fine-tuned vs base TinyLlama on the eval set."""
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Eval samples: {len(eval_data)}")

    tokenizer = AutoTokenizer.from_pretrained(BASE_DIR, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    def load_base():
        return AutoModelForCausalLM.from_pretrained(
            BASE_DIR,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )

    def generate(model, log_text: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Log: {log_text}"},
        ]
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=128,
                do_sample=False,
                temperature=1.0,
                pad_token_id=tokenizer.eos_token_id,
            )
        decoded = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return decoded.strip()

    def score_response(response: str, ground_truth_severity: str) -> dict:
        result = {
            "json_valid": False,
            "fields_present": False,
            "severity_match": False,
            "confidence_valid": False,
            "raw": response[:200],
        }
        # Strip markdown fences
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]).strip()
        try:
            parsed = json.loads(text)
            result["json_valid"] = True
            required = {"summary", "severity", "suggested_action", "confidence"}
            result["fields_present"] = required.issubset(parsed.keys())
            if result["fields_present"]:
                result["severity_match"] = parsed["severity"] == ground_truth_severity
                try:
                    c = float(parsed["confidence"])
                    result["confidence_valid"] = 0.0 <= c <= 1.0
                except (ValueError, TypeError):
                    pass
        except json.JSONDecodeError:
            pass
        return result

    results = {"base": [], "finetuned": []}

    # --- Base model ---
    print("\n=== Base TinyLlama ===")
    base_model = load_base()
    base_model.eval()
    for i, example in enumerate(eval_data):
        msgs = example["messages"]
        log_text = msgs[1]["content"].replace("Log: ", "", 1)
        ground_truth = json.loads(msgs[2]["content"])
        response = generate(base_model, log_text)
        scored = score_response(response, ground_truth["severity"])
        results["base"].append(scored)
        if i % 10 == 0:
            print(f"  [{i+1}/{len(eval_data)}] severity_match={scored['severity_match']} json_valid={scored['json_valid']}")
    del base_model
    torch.cuda.empty_cache()

    # --- Fine-tuned model ---
    print("\n=== Fine-tuned TinyLlama (LoRA) ===")
    base_for_lora = load_base()
    ft_model = PeftModel.from_pretrained(base_for_lora, LORA_DIR)
    ft_model.eval()
    for i, example in enumerate(eval_data):
        msgs = example["messages"]
        log_text = msgs[1]["content"].replace("Log: ", "", 1)
        ground_truth = json.loads(msgs[2]["content"])
        response = generate(ft_model, log_text)
        scored = score_response(response, ground_truth["severity"])
        results["finetuned"].append(scored)
        if i % 10 == 0:
            print(f"  [{i+1}/{len(eval_data)}] severity_match={scored['severity_match']} json_valid={scored['json_valid']}")
    del ft_model
    torch.cuda.empty_cache()

    # Aggregate
    def aggregate(scores: list[dict]) -> dict:
        n = len(scores)
        return {
            "json_valid_pct": sum(s["json_valid"] for s in scores) / n * 100,
            "fields_present_pct": sum(s["fields_present"] for s in scores) / n * 100,
            "severity_match_pct": sum(s["severity_match"] for s in scores) / n * 100,
            "confidence_valid_pct": sum(s["confidence_valid"] for s in scores) / n * 100,
        }

    return {
        "base": aggregate(results["base"]),
        "finetuned": aggregate(results["finetuned"]),
        "raw": results,
    }


# ---------------------------------------------------------------------------
# Local side — Claude Haiku eval (runs on your machine, API calls)
# ---------------------------------------------------------------------------
def eval_claude(eval_data: list[dict]) -> dict:
    client = Anthropic()
    scores = []
    print("\n=== Claude Haiku ===")
    for i, example in enumerate(eval_data):
        msgs = example["messages"]
        log_text = msgs[1]["content"].replace("Log: ", "", 1)
        ground_truth = json.loads(msgs[2]["content"])

        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Log: {log_text}"}],
            )
            response = msg.content[0].text.strip()
            text = response
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]).strip()
            parsed = json.loads(text)
            json_valid = True
            required = {"summary", "severity", "suggested_action", "confidence"}
            fields_present = required.issubset(parsed.keys())
            severity_match = fields_present and parsed["severity"] == ground_truth["severity"]
            confidence_valid = False
            if fields_present:
                try:
                    c = float(parsed["confidence"])
                    confidence_valid = 0.0 <= c <= 1.0
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            print(f"  Error on sample {i}: {e}")
            json_valid = fields_present = severity_match = confidence_valid = False

        scores.append({
            "json_valid": json_valid,
            "fields_present": fields_present,
            "severity_match": severity_match,
            "confidence_valid": confidence_valid,
        })

        if i % 10 == 0:
            print(f"  [{i+1}/{len(eval_data)}] severity_match={severity_match} json_valid={json_valid}")

        # Gentle rate limiting
        if (i + 1) % 20 == 0:
            time.sleep(1)

    n = len(scores)
    return {
        "json_valid_pct": sum(s["json_valid"] for s in scores) / n * 100,
        "fields_present_pct": sum(s["fields_present"] for s in scores) / n * 100,
        "severity_match_pct": sum(s["severity_match"] for s in scores) / n * 100,
        "confidence_valid_pct": sum(s["confidence_valid"] for s in scores) / n * 100,
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
@app.local_entrypoint()
def main():
    if not EVAL_PATH.exists():
        print("ERROR: finetune/sre_eval.jsonl not found. Run generate_dataset.py first.")
        return

    eval_data = [json.loads(l) for l in EVAL_PATH.read_text().splitlines() if l.strip()]
    print(f"Eval set: {len(eval_data)} samples")
    print("Sending to Modal A10G for base + fine-tuned inference...")

    t0 = time.time()
    gpu_results = run_model_eval.remote(eval_data)
    gpu_time = time.time() - t0
    print(f"GPU eval done in {gpu_time:.0f}s")

    print("Running Claude Haiku eval locally...")
    claude_scores = eval_claude(eval_data)

    # ---------------------------------------------------------------------------
    # Print comparison table
    # ---------------------------------------------------------------------------
    print("\n" + "="*70)
    print("EVALUATION RESULTS — v15 Fine-tune vs Base vs Claude")
    print("="*70)
    print(f"{'Metric':<28} {'Base TinyLlama':>16} {'Fine-tuned LoRA':>16} {'Claude Haiku':>14}")
    print("-"*70)

    metrics = [
        ("JSON valid (%)", "json_valid_pct"),
        ("Fields present (%)", "fields_present_pct"),
        ("Severity match (%)", "severity_match_pct"),
        ("Confidence valid (%)", "confidence_valid_pct"),
    ]
    for label, key in metrics:
        base_v = gpu_results["base"][key]
        ft_v = gpu_results["finetuned"][key]
        cl_v = claude_scores[key]
        print(f"{label:<28} {base_v:>15.1f}% {ft_v:>15.1f}% {cl_v:>13.1f}%")

    print("="*70)

    # Verdict
    ft_sev = gpu_results["finetuned"]["severity_match_pct"]
    base_sev = gpu_results["base"]["severity_match_pct"]
    cl_sev = claude_scores["severity_match_pct"]

    print("\nVerdict:")
    if ft_sev > base_sev + 10:
        print(f"  LoRA fine-tuning improved severity accuracy by {ft_sev - base_sev:.1f}pp over base.")
    elif ft_sev > base_sev:
        print(f"  LoRA fine-tuning improved severity accuracy by {ft_sev - base_sev:.1f}pp (marginal).")
    else:
        print(f"  Fine-tuning did not improve severity accuracy vs base ({ft_sev:.1f}% vs {base_sev:.1f}%).")

    gap = cl_sev - ft_sev
    if gap < 5:
        print(f"  Fine-tuned TinyLlama matches Claude Haiku on severity (gap: {gap:.1f}pp).")
    elif gap < 15:
        print(f"  Claude Haiku leads by {gap:.1f}pp — general reasoning still edges specialization.")
    else:
        print(f"  Claude Haiku leads by {gap:.1f}pp — larger model / RLHF gives significant advantage.")

    # Save results
    out = {
        "base": gpu_results["base"],
        "finetuned": gpu_results["finetuned"],
        "claude_haiku": claude_scores,
        "eval_samples": len(eval_data),
        "gpu_time_s": gpu_time,
    }
    Path("finetune/eval_results.json").write_text(json.dumps(out, indent=2))
    print("\nFull results saved to finetune/eval_results.json")
