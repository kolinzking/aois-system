# v15 — Fine-tuning: Teaching a Small Model to Think Like an SRE
⏱ **Estimated time: 4–6 hours**

*Phase 5 — NVIDIA & GPU Inference. See `curriculum/phase5/00-introduction.md` for the phase overview and the v13→v14→v15 build arc.*

---

## What this version builds

v13 gave AOIS its own inference tier (NIM + Groq). v14 deployed vLLM as a self-hosted inference server. v15 answers the deeper question: **can a 1.1B parameter model, trained on your specific domain, outperform a much larger general model on your specific task?**

The answer turns out to be: yes — on format compliance and structural correctness. Partially — on semantic accuracy. The gap with Claude is real but measurable, not a wall.

Here is what actually happens in v15:

1. You generate 500 SRE incident examples using Claude Haiku (high-quality teacher)
2. You LoRA fine-tune TinyLlama-1.1B on those examples on an A10G GPU (63 seconds)
3. You run the fine-tuned model, the base model, and Claude Haiku against a held-out eval set
4. You read the results and understand *exactly* what fine-tuning bought you

At the end of v15:
- **Dataset generated** — 500 (log, analysis) pairs covering the full range of SRE incident types
- **LoRA adapter trained** — 2.25M trainable params out of 1.1B total (0.20%), loss drops from 2.25 → 0.23
- **Eval run** — three-way comparison: base TinyLlama, fine-tuned TinyLlama, Claude Haiku
- **The answer in hand** — where specialization beats general reasoning, and where it doesn't
- **Phase 5 complete** — you can now route by cost, speed, and capability across six inference tiers

---

## Prerequisites

Verify before starting:

```bash
# Modal CLI installed and authenticated
modal --version
# Expected: modal, version X.X.X

# Python packages for dataset generation
pip show anthropic python-dotenv | grep -E "Name|Version"
# Expected:
# Name: anthropic
# Version: 0.x.x
# Name: python-dotenv
# Version: 1.x.x

# ANTHROPIC_API_KEY set
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print('key set' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING')"
# Expected: key set

# Modal volumes from v14 exist (base model weights already downloaded)
modal volume list | grep aois
# Expected: aois-tinyllama-weights  (or similar)
```

If `aois-tinyllama-weights` volume does not exist, the fine-tune script will download TinyLlama-1.1B automatically on first run (~1.1GB, ~2 minutes).

---

## Learning Goals

By the end of v15 you will be able to:

- Explain what LoRA is and why it trains 0.2% of parameters instead of 100%
- Build a fine-tuning dataset from scratch using a stronger model as teacher
- Configure SFTTrainer with the right hyperparameters for a 1B model on a single A10G
- Diagnose and fix the three most common fine-tuning failures (gradient errors, dtype conflicts, wrong model loaded)
- Interpret a training loss curve and eval loss curve — what good convergence looks like
- Run a structured eval comparing a fine-tuned model against a base model and a frontier API
- State with evidence where fine-tuning helps and where it doesn't for your specific task

---

## Part 1: Why Fine-tune at All?

Claude Haiku costs roughly $0.0008 per analysis call. At 100,000 calls/day that's $80/day. At 1,000,000 calls/day it's $800/day — $292,000/year for log analysis.

But cost is the secondary reason. The primary reason is **format compliance**. Production systems don't tolerate `"I think this might be a P2 severity issue based on..."`. They need `{"severity": "P2", ...}`. A general model produces prose when uncertain. A fine-tuned model produces JSON — because that's all it has ever seen in training.

The tradeoff:
- Fine-tuned small model: fast (2-4x inference speed), cheap, format-reliable, domain-adapted
- General large model: slower, expensive, occasionally verbose, but stronger reasoning on novel incidents

v15 builds the evidence base to decide which tier handles which traffic.

---

## The Fine-tuning Landscape

**Full fine-tuning** — update all 1.1B weights. Requires ~10GB VRAM just for the model in FP16, more for optimizer states. For a 7B model, you need 4× A100s. Expensive. Slow. Rarely worth it when LoRA exists.

**LoRA (Low-Rank Adaptation)** — freeze all original weights. Add tiny trainable "adapter" matrices at specific layers. At rank=16, TinyLlama-1.1B has 2.25M trainable params instead of 1.1B. Trains in seconds, not hours. The adapter is 9MB. The base model is unchanged.

How LoRA works mathematically: each weight matrix `W` gets two new matrices `A` (d×r) and `B` (r×d) where r is the rank (16 in our case). During training, only A and B are updated. The effective weight becomes `W + BA`. At r=16 and d=2048 (TinyLlama hidden size), each adapter pair has 2×2048×16 = 65,536 params. Across all targeted layers, that's 2.25M total.

**Target modules**: `q_proj` and `v_proj` — the query and value projection matrices in the attention mechanism. These are the layers most responsible for "what does this token attend to" — which is exactly what changes when you teach a model a new domain.

**Chat fine-tuning format**: the model is trained on complete conversations in the exact format it was originally trained on. TinyLlama was trained on the ChatML format (`<|system|>`, `<|user|>`, `<|assistant|>` tags). SFTTrainer calls `apply_chat_template` to format each example correctly.

---

## Part 2: The Dataset

### Seed log design

The 35 seed logs in `finetune/generate_dataset.py` cover every category AOIS encounters:
- Memory: OOMKilled, heap exhaustion, node pressure
- Crashes: CrashLoopBackOff, migration failures
- Disk: filesystem full, PVC pressure, inode exhaustion
- Network/DNS: resolution failures, connection refused, service mesh timeouts
- TLS: cert expiry, verification failures, ACME challenges
- 5xx spikes: 503 rates, error rate jumps, 504 timeouts
- CPU: throttling, HPA limits, load average
- Kubernetes: NotReady nodes, rollout stuck, ImagePullBackOff, eviction, PDB
- Database: max_connections, slow queries, replication lag, deadlocks, Redis eviction
- Security: brute force, unexpected connections, root containers, stale secrets
- Kafka: consumer lag, broker disk, producer timeouts

Coverage matters. A model trained only on OOMKilled logs will fail on Kafka consumer lag. The breadth of the seed set determines the breadth of the model's competence.

### Variation strategy

`vary_log()` applies two transformations to each seed log:
1. Numeric variation — all numbers shifted ±33% randomly. `512Mi` becomes `482Mi` or `621Mi`. This prevents the model memorising specific thresholds.
2. Pod name variation — randomised hex suffixes. `pod-7d9f` becomes `pod-3c5b`. This prevents memorisation of specific pod names.

70% of training examples use varied logs. 30% use the exact seed. This gives both generalisation and exact-case coverage.

### Teacher model

Claude Haiku generates the ground-truth analysis for each log. This is the **teacher-student** pattern: a weaker model (TinyLlama) learns from a stronger model's outputs (Haiku). The student doesn't need to be better than the teacher — it needs to be faster and cheaper while approximating the teacher on the distribution it was trained on.

### Dataset statistics (what you built)

```
Total examples: 500
Train split: 450 (90%)
Eval split: 50 (10%)
Format: JSONL, one example per line
Example structure:
{
  "messages": [
    {"role": "system", "content": "<SYSTEM_PROMPT>"},
    {"role": "user",   "content": "Log: OOMKilled: container aois-api..."},
    {"role": "assistant", "content": "{\"summary\": \"...\", \"severity\": \"P1\", ...}"}
  ]
}
```

---

## ▶ STOP — do this now

Verify your dataset before spending GPU time:

```bash
# Count examples
wc -l finetune/sre_train.jsonl finetune/sre_eval.jsonl
```

Expected output:
```
 450 finetune/sre_train.jsonl
  50 finetune/sre_eval.jsonl
 500 total
```

```bash
# Inspect one training example
python3 -c "
import json
from pathlib import Path
ex = json.loads(Path('finetune/sre_train.jsonl').read_text().splitlines()[0])
for msg in ex['messages']:
    print(f\"[{msg['role']}] {msg['content'][:120]}\")
"
```

Expected output (content will vary):
```
[system] You are an expert SRE at a large technology company. Given an infrastructure log message, provide a concise structured...
[user] Log: OOMKilled: container aois-api exceeded memory limit 512Mi, exit code 137
[assistant] {"summary": "Container aois-api was killed due to exceeding its memory limit of 512Mi", "severity": "P1", "suggested_action": "..."}
```

```bash
# Verify all 450 train examples parse correctly
python3 -c "
import json
from pathlib import Path
lines = [l for l in Path('finetune/sre_train.jsonl').read_text().splitlines() if l.strip()]
valid = sum(1 for l in lines if json.loads(l))
print(f'Valid: {valid}/{len(lines)}')
"
```

Expected: `Valid: 450/450`

If any line fails to parse, the fine-tune will crash with a cryptic error mid-training. Fix the dataset first.

---

## Part 3: LoRA Fine-tuning on Modal

### The compute

A10G GPU: 24GB VRAM, 31.2 TFLOPS (BF16). For TinyLlama-1.1B:
- Model weights in BF16: ~2.2GB
- LoRA adapter params: ~18MB
- Optimizer states (AdamW, only adapter params): ~36MB
- Activations + gradient buffers: ~4GB at batch_size=2
- Total VRAM used: ~7GB of 24GB available

This is why TinyLlama is the right model for learning: the A10G has 3× the headroom needed. You can watch the full training cycle in 63 seconds. A 7B model would take 10–20 minutes and require more careful memory management.

### Key configuration decisions

**`r=16, lora_alpha=32`**: rank 16 gives enough capacity to learn the JSON format + SRE vocabulary. `alpha/r = 2` is the standard scaling that prevents the adapter from overriding the base model's general knowledge. Higher rank = more capacity but more parameters and longer training.

**`target_modules=["q_proj", "v_proj"]`**: targeting only query and value projections is the standard LLaMA recipe. Adding `k_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` would increase capacity but also training time and adapter size. For a narrow-domain task like JSON SRE analysis, q+v is sufficient.

**`num_train_epochs=3`**: three full passes over the 450-example dataset. With batch_size=2 and gradient_accumulation=4, effective batch size is 8. Steps per epoch: 450/8 = 56 steps. Total steps: 168.

**`bf16=True` (not `fp16=True`)**: A10G supports BF16 natively. BF16 has the same dynamic range as FP32 (8-bit exponent) but half the precision. This matters for training stability. FP16 (5-bit exponent) can underflow on gradient values — you'd get `ValueError: Attempting to unscale FP16 gradients`. Always use BF16 on A10G.

**`max_seq_length=256`**: SRE logs + JSON responses fit in 200 tokens. 256 gives headroom. Padding shorter sequences wastes compute; 256 is tight enough to keep batch efficiency high.

**`load_best_model_at_end=True`**: saves the checkpoint with the best eval loss, not the final epoch. If epoch 3 overfits slightly, you still get epoch 2's weights. Essential for small datasets.

### Training results

```
GPU: NVIDIA A10G
VRAM: 23.7 GB
Train samples: 450 | Eval samples: 50
Trainable params: 2,252,800 (0.20% of 1,102,301,184)

Epoch 0.18: train_loss=2.2500
Epoch 1.00: eval_loss=0.3800
Epoch 2.00: eval_loss=0.2900
Epoch 2.84: train_loss=0.2300
Epoch 3.00: eval_loss=0.2400

Runtime: 63s
Train loss: 0.5882
Samples/sec: 21.4
Adapter saved to: /models/tinyllama-sre-lora
```

Loss interpretation:
- **Train loss 2.25 → 0.23**: the model went from random predictions to near-perfect reproduction of the training format
- **Eval loss 0.38 → 0.24**: generalisation held — eval loss did not diverge from train loss, meaning no overfitting
- **Gap between train and eval**: ~0.01 at epoch 3. Healthy. If eval loss had risen while train loss fell, you'd see overfitting.

---

## ▶ STOP — do this now

Run the fine-tune (uses ~$0.02 of Modal credits, ~2 minutes including container cold start):

```bash
python3 finetune/generate_dataset.py   # only if you haven't already
modal run finetune/finetune.py
```

Expected output:
```
Loaded 450 train / 50 eval examples
Sending to Modal A10G GPU...

GPU: NVIDIA A10G
VRAM: 23.7 GB
Train samples: 450 | Eval samples: 50
...
Trainable parameters: 2,252,800 || all params: 1,102,301,184 || trainable%: 0.2044

Starting LoRA fine-tuning...
...
Training complete.
  Runtime: 63s
  Train loss: 0.5882
  Samples/sec: 21.4
Adapter saved to: /models/tinyllama-sre-lora

Result: {'status': 'complete', 'runtime_s': 63.0, 'train_loss': 0.5882, 'output_dir': '/models/tinyllama-sre-lora'}
```

If you see `Runtime: 63s` and a train loss below 1.0, the fine-tune succeeded.

---

## Part 4: Evaluation — Where Specialisation Beats General Reasoning

### What the eval measures

`finetune/eval.py` runs all 50 eval samples through three models:

1. **Base TinyLlama** — the model before fine-tuning. No SRE knowledge injected.
2. **Fine-tuned TinyLlama** — same model + LoRA adapter loaded from `aois-lora-weights` volume.
3. **Claude Haiku** — the teacher model. This is the ceiling.

Four metrics per model:
- **json_valid**: did the response parse as JSON?
- **fields_present**: are all four required fields present?
- **severity_match**: does severity match the ground truth (which was Claude-generated)?
- **confidence_valid**: is confidence a float in [0.0, 1.0]?

### Results

```
======================================================================
EVALUATION RESULTS — v15 Fine-tune vs Base vs Claude
======================================================================
Metric                       Base TinyLlama  Fine-tuned LoRA  Claude Haiku
----------------------------------------------------------------------
JSON valid (%)                         0.0%            98.0%         98.0%
Fields present (%)                     0.0%            94.0%         98.0%
Severity match (%)                     0.0%            64.0%         82.0%
Confidence valid (%)                   0.0%            90.0%         96.0%
======================================================================
```

### Reading the results

**Base model: 0% on everything.** This is the baseline that matters. Without fine-tuning, TinyLlama cannot produce valid JSON on demand. It generates prose — "I think this might be related to..." — which is useless for a production system that expects `{"severity": "P2"}`. This is not a failure of TinyLlama. It was trained to be a helpful chat assistant, not a JSON API.

**Fine-tuned: 98% JSON validity.** 63 seconds of training was enough for the model to learn that its job is to output JSON in a specific format. This is the clearest win from fine-tuning.

**Fine-tuned: 64% severity match vs Claude's 82%.** The 18pp gap is the cost of being a 1.1B parameter model. Severity classification requires understanding the *implication* of the log — that "replication lag 4.2GB" is P2 not P3 because it will hit P1 territory within the hour. This kind of reasoning under uncertainty favours scale. Claude has 8–20× more parameters and RLHF alignment.

**The practical decision:**

| Traffic type | Route to | Reasoning |
|---|---|---|
| P3/P4 high-volume | Fine-tuned TinyLlama | 98% JSON valid, fast, cheap. P3/P4 wrong classification has low blast radius. |
| P1/P2 incidents | Claude Haiku/Sonnet | 18pp accuracy gap matters when "production down" is on the line |
| Unknown severity | Claude first, TinyLlama for confirmation | Belt-and-suspenders on critical paths |

---

## ▶ STOP — do this now

Run the full evaluation:

```bash
modal run finetune/eval.py
```

Expected: the results table printed to stdout. Results saved to `finetune/eval_results.json`.

After it completes, inspect the raw per-sample results:

```bash
python3 -c "
import json
from pathlib import Path
r = json.loads(Path('finetune/eval_results.json').read_text())
ft = r['raw']['finetuned']
# Show the cases where fine-tuned got severity wrong
wrong = [i for i, s in enumerate(ft) if not s['severity_match'] and s['json_valid']]
print(f'Fine-tuned wrong on severity: {len(wrong)}/50 samples')
print(f'Indices: {wrong[:10]}')
"
```

Then look at what those samples actually were:

```bash
python3 -c "
import json
from pathlib import Path

eval_data = [json.loads(l) for l in Path('finetune/sre_eval.jsonl').read_text().splitlines() if l.strip()]
r = json.loads(Path('finetune/eval_results.json').read_text())
ft = r['raw']['finetuned']
wrong = [i for i, s in enumerate(ft) if not s['severity_match'] and s['json_valid']]

for i in wrong[:3]:
    ex = eval_data[i]
    log = ex['messages'][1]['content']
    gt_sev = json.loads(ex['messages'][2]['content'])['severity']
    ft_raw = ft[i]['raw']
    print(f'Sample {i}:')
    print(f'  Log: {log[:80]}')
    print(f'  GT severity: {gt_sev}')
    print(f'  FT output: {ft_raw[:100]}')
    print()
"
```

This tells you *which* incident types the fine-tuned model struggles with — that informs whether more training data, higher rank, or more epochs would close the gap.

---

## Part 5: What the LoRA Adapter Actually Is

After training, the adapter lives in `aois-lora-weights` Modal volume at `/models/tinyllama-sre-lora`. It's small:

```
adapter_config.json     — LoRA hyperparameters (r, alpha, target_modules, etc.)
adapter_model.safetensors — the actual trained weights (~9MB)
tokenizer_config.json   — copied from base model
tokenizer.model         — SentencePiece tokenizer
special_tokens_map.json — special token definitions
```

To use the adapter elsewhere — on a different machine, with a different inference server — you need both the base model and this adapter directory. vLLM, text-generation-inference, and Ollama all support LoRA adapters via different mechanisms.

The adapter is not the model. It is a diff. Loading `PeftModel.from_pretrained(base_model, adapter_dir)` merges the adapter into the base model's attention layers at inference time.

---

## Common Mistakes

### 1. `RuntimeError: element 0 of tensors does not require grad`

**Symptom:** training crashes immediately on first backward pass.

**Cause:** calling `model.gradient_checkpointing_enable()` after `get_peft_model()`. Gradient checkpointing recomputes activations during backward pass instead of storing them, saving VRAM. But it interferes with PEFT's gradient hooks when called in the wrong order.

**Fix:** remove `gradient_checkpointing_enable()` entirely. With a 1.1B model on an A10G, you have 17GB of headroom — you don't need it.

```python
# WRONG
model = get_peft_model(model, lora_config)
model.gradient_checkpointing_enable()   # breaks gradient flow

# RIGHT
model = get_peft_model(model, lora_config)
# no gradient checkpointing — VRAM is not the constraint here
```

### 2. `ValueError: Attempting to unscale FP16 gradients`

**Symptom:** crashes mid-training, usually at the first gradient update.

**Cause:** model loaded as `torch.float16` + `fp16=True` in TrainingArguments. FP16 has a 5-bit exponent — gradient values in the range 1e-8 to 1e-7 silently underflow to zero. The AMP scaler tries to unscale them and finds zeros. This causes the error.

**Fix:** use BF16 throughout. BF16 has the same dynamic range as FP32.

```python
# WRONG
model = AutoModelForCausalLM.from_pretrained(..., torch_dtype=torch.float16)
training_args = TrainingArguments(..., fp16=True)

# RIGHT
model = AutoModelForCausalLM.from_pretrained(..., torch_dtype=torch.bfloat16)
training_args = TrainingArguments(..., bf16=True)
```

### 3. Wrong model loaded from volume (7B instead of 1.1B)

**Symptom:** training logs show `7,241,732,096 total parameters` instead of `1,102,301,184`.

**Cause:** a previous run stored a different model (Mistral-7B) in the same Modal volume, at a different path. When you mount the same volume and point to a new path, Modal serves the existing content.

**Fix:** use a dedicated volume per model. Never share volumes between different base models.

```python
# WRONG — same volume, new path, still has old model
volume = modal.Volume.from_name("aois-model-weights")
volumes = {"/models/tinyllama-1b": volume}  # still has Mistral here

# RIGHT — separate volume for TinyLlama
tinyllama_volume = modal.Volume.from_name("aois-tinyllama-weights", create_if_missing=True)
volumes = {"/models/tinyllama-1b": tinyllama_volume}
```

### 4. Dataset generates `ValueError: empty range in randrange(1, 1)`

**Symptom:** `generate_dataset.py` crashes when varying logs with `0` in them.

**Cause:** `vary_log()` tries to vary all numbers, including `0`. `randint(max(1, 0 - 0), max(2, 0 + 0))` = `randint(1, 0)` which is invalid.

**Fix:** special-case zero.

```python
def replace_num(m):
    n = int(m.group())
    if n == 0:
        return str(n)  # don't vary zero
    lo = max(1, n - n // 3)
    hi = max(lo + 1, n + n // 3)
    return str(random.randint(lo, hi))
```

### 5. `ModuleNotFoundError: No module named 'dotenv'` in Modal container

**Symptom:** Modal container crashes on import.

**Cause:** `from dotenv import load_dotenv` at the top of the file. Modal uploads the file and imports it inside the container, which only has the packages you specified in `pip_install()`. `python-dotenv` is a local dev dependency, not a training dependency.

**Fix:** move `load_dotenv()` into the `@app.local_entrypoint()` function only. Everything inside `@app.function()` runs in the container; the entrypoint runs locally.

```python
# WRONG — runs in container
from dotenv import load_dotenv
load_dotenv()

# RIGHT — runs locally only
@app.local_entrypoint()
def main():
    from dotenv import load_dotenv
    load_dotenv()
    ...
```

---

## Troubleshooting

### `modal run finetune/finetune.py` hangs after "Sending to Modal A10G GPU..."

Modal is cold-starting the container. The image includes PyTorch (~2GB) and the pip installs take 2–4 minutes on first run. After the image is built and cached, subsequent runs start in ~20 seconds.

Check Modal dashboard: `https://modal.com/apps` — look for `aois-finetune`. If the function is in `PENDING` state, it's waiting for GPU allocation (usually 10–60 seconds).

### `snapshot_download` fails with 401

Your HuggingFace token is not set or expired. TinyLlama-1.1B is a public model — no token needed. If you're on a network that blocks HuggingFace, set `HF_ENDPOINT` to a mirror.

```bash
# Verify the model is public
python3 -c "from huggingface_hub import model_info; print(model_info('TinyLlama/TinyLlama-1.1B-Chat-v1.0').private)"
# Expected: False
```

### Train loss not decreasing after epoch 1

If train loss stays above 1.5 after the first epoch, something is wrong with the data or the chat template.

```bash
# Check one formatted example
python3 -c "
import json
from pathlib import Path
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained('TinyLlama/TinyLlama-1.1B-Chat-v1.0')
ex = json.loads(Path('finetune/sre_train.jsonl').read_text().splitlines()[0])
text = tokenizer.apply_chat_template(ex['messages'], tokenize=False, add_generation_prompt=False)
print(text[:500])
"
```

You should see the `<|system|>`, `<|user|>`, `<|assistant|>` tags around the correct content. If the format looks wrong, the model cannot learn from it.

### Eval shows fine-tuned worse than base on severity

This means the eval ground truth (Claude-generated severities) had high variance in the training set — the model learned conflicting patterns. Solutions:
1. Increase training data (1000+ examples reduces noise)
2. Use a more consistent teacher — replace Haiku with Sonnet for ground truth
3. Increase rank to `r=32` for more adapter capacity

---

## Connection to Later Phases

**v16 (OpenTelemetry)**: every LLM call — fine-tuned, base, Claude — should emit the same OTel spans. `model.name`, `tokens.prompt`, `tokens.completion`, `cost`, `latency`. When you have six inference tiers, unified telemetry is what lets you compare them.

**v20 (tool use + memory)**: a fine-tuned model can be specialised for a sub-task in an agent pipeline. The orchestrator (Claude) reasons; a fine-tuned specialist handles the high-volume classification step. This is the production multi-model agent pattern.

**v29 (Weights & Biases)**: the eval results in `finetune/eval_results.json` are the baseline for v29's experiment tracking. Every prompt change, dataset change, or hyperparameter change gets logged as a W&B run. You have the baseline now — v29 builds the tracking around it.

---

## Mastery Checkpoint

You have completed v15 when you can do all of the following:

1. **Explain the LoRA math** to someone who knows linear algebra: why `W + BA` trains faster than `W` alone, what rank controls, why `alpha/r=2` is the standard ratio.

2. **Reproduce the fine-tune from scratch**: `python3 finetune/generate_dataset.py` → `modal run finetune/finetune.py`. You understand every argument in `LoraConfig` and `TrainingArguments`.

3. **Read the loss curve and make a diagnosis**: given train_loss=0.8 at epoch 3 and eval_loss=1.4 at epoch 3, state what happened (overfitting) and what to try (reduce epochs, reduce rank, add dropout).

4. **Explain the eval results honestly**: not "fine-tuning worked" or "fine-tuning failed" — "fine-tuning gave 98% JSON validity vs 0% base, closed 18pp of Claude's 82% severity accuracy, and the remaining gap is explained by model scale."

5. **Identify the volume scoping bug** if you see "7.25B params" in a TinyLlama fine-tune run, and fix it without looking at the notes.

6. **State the routing decision**: which traffic goes to the fine-tuned model, which goes to Claude, and why — backed by the eval numbers, not intuition.

7. **Fix the three common fine-tuning errors** from symptoms alone: gradient checkpointing crash, FP16/BF16 mismatch, dotenv in container.

8. **Describe what the adapter files are**: which file holds the trained weights, what other files are needed, and how PeftModel loads them at inference time.

9. **Connect to v16 and v20**: explain specifically what changes when OpenTelemetry is added and when the fine-tuned model is placed inside an agent pipeline.

**The mastery bar:** you can take a new domain (e.g., security alert triage instead of SRE logs), generate a dataset, fine-tune a small model, evaluate it, and make a defensible decision about where it replaces the frontier API and where it doesn't. That is a production ML skill.

---

*Phase 5 complete. You now have six inference tiers: Claude (premium), GPT-4o-mini (general), Groq (fast), NIM (self-hosted), vLLM (open-source server), fine-tuned TinyLlama (domain-specialised). Phase 6 is the observability stack that makes all six tiers visible, measurable, and comparable.*

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### LoRA Fine-tuning

| Layer | |
|---|---|
| **Plain English** | A technique to teach a pre-trained AI model new specialised skills — like SRE log analysis — without retraining the entire model from scratch. It adds a small set of new weights and only trains those, leaving the original model untouched. |
| **System Role** | LoRA is how AOIS's domain-specialised TinyLlama was created. The base model had general language ability but poor SRE log understanding. LoRA training on 450 log→analysis pairs brought JSON validity from 2% to 94%. The resulting adapter is a ~50MB file layered on top of the 1.1B base model — used for P3/P4 volume where Claude's cost is not justified. |
| **Technical** | LoRA (Low-Rank Adaptation) decomposes the weight update matrix into two low-rank matrices: `W' = W + BA` where `B ∈ R^{d×r}` and `A ∈ R^{r×k}`, with rank `r << d,k`. Only `A` and `B` are trained — typically 0.1–1% of original parameter count. `r=16` was used for AOIS. After training, the adapter weights (`.safetensors`) can be merged with the base model or loaded dynamically via PEFT. Training ran in 63 seconds on a Modal A10G. |
| **Remove it** | Without fine-tuning, AOIS uses the base model for P3/P4 logs — which produces 2% valid JSON. The only alternative for reliable structured output from a small model is prompt engineering, which fails at the token budget of a 1B model. Fine-tuning is the only path to production-quality behaviour from a model small enough to run cheaply at scale. The eval result — 94% vs 2% — is the case for fine-tuning in one number. |

**Say it at three levels:**
- *Non-technical:* "Fine-tuning is like a specialist training program. The base model knows language generally. LoRA gives it 500 worked examples of exactly the job you need done — and it learns the job without forgetting everything else it knows."
- *Junior engineer:* "LoRA adds two small matrices to specific layers (`target_modules=['q_proj','v_proj']`). Training updates only those matrices. `peft.LoraConfig(r=16, lora_alpha=32, task_type='CAUSAL_LM')`. After training, `model.save_pretrained()` saves the adapter separately from the base. Load with `PeftModel.from_pretrained(base_model, adapter_path)`. The AOIS training loop: `transformers.Trainer` with the 450-sample dataset, 3 epochs, loss 2.25→0.23."
- *Senior engineer:* "LoRA's rank `r` controls the adaptation capacity. Low `r` (4–8): fewer parameters, faster training, risks underfitting on complex tasks. High `r` (32–64): more capacity, risk of overfitting on small datasets. r=16 is the standard starting point. The AOIS eval result (44% severity match vs Claude's 80%) reflects the model scale gap, not a LoRA limitation — TinyLlama at 1.1B cannot match Claude's reasoning regardless of fine-tuning. The production decision: fine-tuned small model for format compliance and P3/P4 volume; frontier model for reasoning-intensive P1/P2. Fine-tuning and API routing are complementary, not competing strategies."

---

### Hugging Face (Model Hub + Transformers)

| Layer | |
|---|---|
| **Plain English** | The GitHub of AI models — a platform where anyone can publish, download, and run pre-trained models. Also the library (`transformers`) that makes loading and running those models a few lines of Python. |
| **System Role** | HuggingFace is where AOIS's fine-tuning base model (TinyLlama-1.1B) was downloaded from, and where the `transformers` + `datasets` + `peft` libraries come from. Every version of AOIS that runs open-source models starts at HuggingFace — it is the source layer of the open-source model stack. |
| **Technical** | `AutoModelForCausalLM.from_pretrained("TinyLlama/TinyLlama-1.1B-Chat-v1.0")` downloads the model weights from the HuggingFace Hub and loads them into memory. `datasets.Dataset` handles the training data format. `peft.get_peft_model()` wraps the model with LoRA adapters. `AutoTokenizer` handles tokenisation. The Hub stores model weights as `.safetensors` files with model cards documenting training data and intended use. |
| **Remove it** | Without HuggingFace, accessing open-source models requires finding weights elsewhere (often unofficial mirrors), writing custom loading code, and managing tokeniser configs manually. The `transformers` library alone is the reason open-source model research is accessible — it abstracts CUDA, quantization, tokenization, and generation across 500k+ model architectures with a single consistent interface. |

**Say it at three levels:**
- *Non-technical:* "HuggingFace is the app store for AI models. You search for a model, download it with one command, and the `transformers` library makes it work in your code immediately."
- *Junior engineer:* "`from transformers import AutoModelForCausalLM, AutoTokenizer` then `.from_pretrained('model-name')`. This downloads and caches the weights locally. `model.generate()` runs inference. For fine-tuning: load the model, wrap with PEFT, pass to `Trainer` with a `datasets.Dataset`. All three libraries (transformers, peft, datasets) are HuggingFace projects."
- *Senior engineer:* "HuggingFace Hub models are versioned by git commit hash — `from_pretrained('model', revision='abc123')` pins to an exact version. Important for production reproducibility. Model cards are a dual concern: marketing copy AND the only place base training data is documented, which matters for compliance (GDPR, copyright). `safetensors` format vs legacy `.bin`: safetensors is faster to load (memory-mapped, no Python unpickling) and safer (no arbitrary code execution). Always prefer safetensors when available."
