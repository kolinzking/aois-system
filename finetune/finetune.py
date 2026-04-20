"""
v15 — LoRA fine-tune TinyLlama-1.1B on SRE dataset via Modal A10G GPU.

Uses PEFT + TRL's SFTTrainer — the standard production pattern for LoRA fine-tuning.
Saves adapter weights to a Modal Volume so they persist after the container exits.

Usage:
    modal run finetune/finetune.py
    modal run finetune/finetune.py --dry-run   # validate setup without training
"""

import json
import modal
from pathlib import Path

MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
MODEL_REVISION = "fe8a4ea1ffedaf415f4da2f062534de366a451e6"
BASE_DIR = "/models/tinyllama-1b"
OUTPUT_DIR = "/models/tinyllama-sre-lora"

# Persistent volumes: base model weights + trained adapter
tinyllama_volume = modal.Volume.from_name("aois-tinyllama-weights", create_if_missing=True)
lora_volume = modal.Volume.from_name("aois-lora-weights", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.3.1",
        "transformers==4.43.4",
        "tokenizers==0.19.1",
        "peft==0.11.1",
        "trl==0.9.4",
        "datasets==2.20.0",
        "accelerate==0.31.0",
        "bitsandbytes==0.43.1",
        "sentencepiece",
        "rich",
        "huggingface_hub",
        "hf_transfer",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App("aois-finetune", image=image)


@app.function(
    gpu="a10g",
    timeout=3600,
    volumes={
        BASE_DIR: model_volume,
        OUTPUT_DIR: lora_volume,
    },
)
def train(train_data: list[dict], eval_data: list[dict], dry_run: bool = False):
    """Run LoRA fine-tuning on the SRE dataset."""
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer, DataCollatorForCompletionOnlyLM
    from datasets import Dataset
    import os

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    print(f"Train samples: {len(train_data)} | Eval samples: {len(eval_data)}")

    # --- Download model if not already in volume ---
    if not os.path.exists(f"{BASE_DIR}/config.json"):
        from huggingface_hub import snapshot_download
        print(f"Downloading {MODEL_ID} to volume...")
        snapshot_download(
            MODEL_ID,
            revision=MODEL_REVISION,
            local_dir=BASE_DIR,
            ignore_patterns=["*.pt", "*.gguf"],
        )
        model_volume.commit()
        print("Download complete.")

    # --- Load tokenizer and model ---
    print(f"\nLoading {MODEL_ID}...")
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_DIR,
        trust_remote_code=True,
    )
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        BASE_DIR,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False
    print("Model loaded.")

    if dry_run:
        print("Dry run — skipping training.")
        return {"status": "dry_run_ok"}

    # --- LoRA config ---
    # Target the attention projection layers — standard for LLaMA-family models
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,                          # rank — higher = more capacity, more params
        lora_alpha=32,                 # scaling factor (alpha/r = 2 is standard)
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.gradient_checkpointing_enable()
    model.print_trainable_parameters()

    # --- Format dataset ---
    def format_example(example):
        """Convert chat messages to a single training string."""
        msgs = example["messages"]
        text = tokenizer.apply_chat_template(
            msgs,
            tokenize=False,
            add_generation_prompt=False,
        )
        return {"text": text}

    train_dataset = Dataset.from_list(train_data).map(format_example)
    eval_dataset = Dataset.from_list(eval_data).map(format_example)

    # --- Training args ---
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        per_device_eval_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=20,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=10,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=256,
        tokenizer=tokenizer,
    )

    print("\nStarting LoRA fine-tuning...")
    result = trainer.train()

    # Save adapter weights to persistent volume
    trainer.model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    lora_volume.commit()

    print(f"\nTraining complete.")
    print(f"  Runtime: {result.metrics['train_runtime']:.0f}s")
    print(f"  Train loss: {result.metrics['train_loss']:.4f}")
    print(f"  Samples/sec: {result.metrics['train_samples_per_second']:.1f}")
    print(f"Adapter saved to: {OUTPUT_DIR}")

    return {
        "status": "complete",
        "runtime_s": result.metrics["train_runtime"],
        "train_loss": result.metrics["train_loss"],
        "output_dir": OUTPUT_DIR,
    }


@app.local_entrypoint()
def main(dry_run: bool = False):
    """Load dataset locally and run training on Modal."""
    train_path = Path("finetune/sre_train.jsonl")
    eval_path = Path("finetune/sre_eval.jsonl")

    if not train_path.exists():
        print("ERROR: finetune/sre_train.jsonl not found. Run generate_dataset.py first.")
        return

    train_data = [json.loads(l) for l in train_path.read_text().splitlines() if l.strip()]
    eval_data = [json.loads(l) for l in eval_path.read_text().splitlines() if l.strip()]

    print(f"Loaded {len(train_data)} train / {len(eval_data)} eval examples")
    print(f"Dry run: {dry_run}")
    print("Sending to Modal A10G GPU...\n")

    result = train.remote(train_data, eval_data, dry_run=dry_run)
    print("\nResult:", result)
