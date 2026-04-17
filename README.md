# AOIS — AI Operations Intelligence System
### Collins' Path to the Pinnacle of the AI Wave

An SRE-grade AI system that analyzes infrastructure logs, classifies incidents, and autonomously investigates and remediates them. Built across 41 versions and 11 phases — from Linux fundamentals to a fully autonomous, multi-agent, cloud-native platform.

> **The rule:** Build first. No theory without code.

---

## Progress

**Current position: v5 complete — Phase 2 done. Next: v6 (k3s on Hetzner).**

```
Phase 0  ████████████  v0.1–v0.7  ✅ Complete (Foundation)
Phase 1  ████████████  v1–v3      ✅ Complete (Intelligence Core)
Phase 2  ████████████  v4–v5      ✅ Complete (Containerize & Secure)
Phase 3  ░░░░░░░░░░░░  v6–v9      ← You are here
Phase 4  ░░░░░░░░░░░░  v10–v12
Phase 5  ░░░░░░░░░░░░  v13–v15
Phase 6  ░░░░░░░░░░░░  v16–v19
Phase 7  ░░░░░░░░░░░░  v20–v25
Phase 8  ░░░░░░░░░░░░  v26–v27
Phase 9  ░░░░░░░░░░░░  v28–v30
Phase 10 ░░░░░░░░░░░░  v31–v34
```

**Phase 4 (v10) is the milestone that changes everything.**
At that point you have: k8s, Claude agents, AWS Bedrock, full observability, CI/CD, and a live system on Hetzner. That alone puts you ahead of 90% of engineers applying for AI/SRE roles today.

---

## Table of Contents

### Phase 1 — The Intelligence Core
> You will know: Python, FastAPI, Claude API, prompt caching, structured outputs, multi-model routing

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v1 | AOIS Core: Log → Intelligence | FastAPI, Anthropic SDK, Pydantic, OpenAI fallback | ✅ |
| v2 | LiteLLM Gateway | LiteLLM, 4 routing tiers, cost tracking per request | ✅ |
| v3 | Reliable Intelligence | Instructor, DSPy, Langfuse, reasoning models | ✅ |

---

### Phase 2 — Containerize & Secure
> You will know: Docker, OWASP API + LLM security, secrets management, image hardening, AI red-teaming

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v4 | Docker | Multi-stage Dockerfile, Docker Compose, Trivy, Cosign | ✅ |
| v5 | Security Hardening | OWASP LLM Top 10, prompt injection defense, rate limiting, Guardrails AI, PyRIT, Garak | ✅ |

---

### Phase 3 — Kubernetes & GitOps
> You will know: k8s fundamentals, Helm, ArgoCD, GitOps, cert-manager, real cloud deployment

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v6 | k3s on Hetzner | Terraform, k3s, kubectl, cert-manager, HPA | ⬜ |
| v7 | Helm Chart | Helm, values per environment | ⬜ |
| v8 | ArgoCD: GitOps | ArgoCD, git push → auto-deploy, rollback | ⬜ |
| v9 | KEDA: Intelligent Autoscaling | KEDA, Kafka-driven scaling, burst to 20 pods | ⬜ |

---

### Phase 4 — AWS Integration ★ Job-ready milestone
> You will know: EKS, Bedrock, IAM, S3, Lambda, Secrets Manager — the enterprise AI stack

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v10 | Amazon Bedrock + Bedrock Agents | Bedrock, IAM roles, LiteLLM → Bedrock, managed agents | ⬜ |
| v11 | AWS Lambda: Serverless AOIS | Lambda, API Gateway, cost comparison | ⬜ |
| v12 | EKS: Enterprise Kubernetes | EKS, Terraform, Karpenter, IRSA | ⬜ |

---

### Phase 5 — NVIDIA & GPU Inference
> You will know: GPU workloads, NVIDIA NIM, vLLM, inference hardware landscape

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v13 | NVIDIA NIM | NIM microservice, cost-aware routing (NIM vs Claude) | ⬜ |
| v14 | vLLM Inference Server | vLLM on Modal, OpenAI-compatible API, throughput/batching | ⬜ |
| v15 | Fine-tuning with SRE Data | LoRA fine-tune on Modal, eval vs Claude | ⬜ |

---

### Phase 6 — Full SRE Observability Stack
> You will know: OpenTelemetry + LLM conventions, Prometheus, Grafana, Loki, Tempo, eBPF, Kafka

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v16 | OpenTelemetry End-to-End | OTel, Grafana, Loki, Tempo, LLM semantic conventions, VictoriaMetrics | ⬜ |
| v17 | Kafka: Real Log Streaming | Kafka (Strimzi), KEDA consumer lag scaling | ⬜ |
| v18 | eBPF with Cilium + Falco | Cilium, Falco, Tetragon, AI-analyzed security events | ⬜ |
| v19 | Chaos Engineering | Chaos Mesh, game day, SLO: 99.5% P1 alerts in 30s | ⬜ |

---

### Phase 7 — Autonomous Agents
> You will know: Claude tool use, MCP, A2A, Temporal, LangGraph, AutoGen, Mem0, Pydantic AI, Dapr

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v20 | Claude Tool Use + Agent Memory | Tools (get_pod_logs, describe_node), Mem0 short/long-term memory | ⬜ |
| v21 | MCP + A2A | AOIS as MCP server, A2A Protocol, cross-vendor interop | ⬜ |
| v22 | Temporal: Durable Execution | Temporal workflows, crash-resilient agents, replay | ⬜ |
| v23 | LangGraph: Autonomous SRE Loop | Detect → Investigate → Remediate graph, Dapr pub/sub | ⬜ |
| v24 | Multi-Agent Frameworks | CrewAI, AutoGen, Pydantic AI, Google ADK, A2A handoff | ⬜ |
| v25 | E2B: Safe Code Execution | E2B sandbox, AOIS writes + tests kubectl patches before applying | ⬜ |

---

### Phase 8 — Full Stack Dashboard
> You will know: React, Vercel AI SDK, WebSockets, nginx, auth, real-time UI

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v26 | React Dashboard | React + Vite, Vercel AI SDK, WebSocket feed, severity heatmap | ⬜ |
| v27 | Auth & Multi-tenancy | JWT, RBAC, OpenFGA, SPIFFE/SPIRE, Supabase | ⬜ |

---

### Phase 9 — Production CI/CD & Platform Engineering
> You will know: GitHub Actions, Dagger, image signing, zero-downtime deploys, model rollouts, IDP

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v28 | GitHub Actions + Dagger | Full pipeline: lint → test → Trivy → Cosign → ArgoCD, OpenFeature | ⬜ |
| v29 | Weights & Biases: ML Ops | Experiment tracking, A/B prompt testing, cost vs accuracy | ⬜ |
| v30 | Internal Developer Platform | Backstage/Port, Crossplane, Pulumi, Semantic Kernel | ⬜ |

---

### Phase 10 — The Pinnacle
> Multimodal AI, edge inference, AI safety, computer use, governance

| Version | Focus | Key Tech | Status |
|---------|-------|----------|--------|
| v31 | Multimodal AOIS | Claude Vision, Grafana screenshot analysis, topology diagrams | ⬜ |
| v32 | Edge AI with Ollama | Air-gapped inference on Hetzner edge, sync on reconnect | ⬜ |
| v33 | Evals, Red-teaming & AI Safety | PyRIT + Garak in CI, constitutional AI, adversarial test suite | ⬜ |
| v34 | Computer Use + AI Governance | Claude Computer Use, Playwright, EU AI Act compliance | ⬜ |

---

## Stack at a Glance

| Layer | Technologies |
|-------|-------------|
| **AI / LLM** | Claude API, OpenAI, Bedrock, Groq, Ollama, vLLM, NIM, LiteLLM, Instructor, LangGraph, Temporal, Mem0, MCP, A2A |
| **Infrastructure** | Docker, k3s, Kubernetes, Helm, ArgoCD, Terraform, Hetzner, AWS EKS, Lambda |
| **Observability** | OpenTelemetry, Prometheus, Grafana, Loki, Tempo, Langfuse, Kafka, Falco, eBPF |
| **Security** | OWASP LLM Top 10, Vault, Trivy, Cosign, Guardrails AI, PyRIT, Garak, OPA |
| **Frontend** | React, Vite, Vercel AI SDK, WebSockets, nginx |
| **CI/CD** | GitHub Actions, Dagger, GHCR, Weights & Biases, OpenFeature |
