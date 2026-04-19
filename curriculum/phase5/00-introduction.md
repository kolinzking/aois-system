# Phase 5 — NVIDIA & GPU Inference

## What this phase covers

Phase 4 put AOIS in the cloud: Bedrock, Lambda, EKS. Every call still goes to an external API — you are renting someone else's GPU.

Phase 5 changes that. You bring your own inference hardware (or as close to it as possible without owning physical servers). NVIDIA NIM packages models into containers. vLLM serves them at scale. Modal gives you serverless GPU compute billed by the second. By the end of Phase 5, AOIS has a routing tier that costs you $0.000008/call instead of $0.015.

## Why this matters

The engineers who understand inference hardware are not the ones calling `litellm.completion("claude...")` and hoping the bill stays low. They are the ones who can answer:
- At what request volume does a dedicated GPU beat per-token API pricing?
- What is PagedAttention and why does it matter for throughput?
- When does TensorRT-LLM (NIM) outperform vLLM, and when does it not?
- How does Groq's LPU differ from NVIDIA's CUDA cores at the silicon level?

These are the questions that distinguish AI infrastructure engineers from API consumers.

## The build in Phase 5

- **v13**: NVIDIA NIM — connect to NGC-hosted NIM, add severity-based routing, cost benchmark
- **v14**: vLLM — deploy on Modal GPU, serve any HuggingFace model, understand throughput and batching
- **v15**: Fine-tuning — curate 500 AOIS incident labels, LoRA fine-tune on Modal, deploy via vLLM, eval against Claude

After Phase 5, AOIS has its own inference layer. High-severity incidents still go to Claude for reasoning quality. Volume inference runs on your own hardware at a fraction of the cost.
