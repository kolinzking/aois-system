# AOIS — AI Operations Intelligence System
## Collins' Path to the Pinnacle of the AI Wave

---

## Who Collins Is
- SRE/DevOps engineer. Done sitting on the sidelines.
- Goal: Real mastery of the tools that matter right now and in the next 3 years
- Evidence: Everything builds in this repo. GitHub is the CV.
- Resources: Hetzner cloud, OpenAI key, Anthropic key
- Rule: Build first. No theory without code.

---

## Time Investment (Honest Assessment)

| Commitment | Time to Phase 4 (Job-ready AI SRE) | Time to Full Completion |
|------------|-------------------------------------|------------------------|
| 1 hr/day | 10 months | 2+ years |
| 2 hrs/day | 5 months | ~14 months |
| 3 hrs/day | 3.5 months | ~9 months |
| Full-time (6-8 hrs) | 6 weeks | 3 months |

**Milestone that changes everything:** Phase 4 completion.
At that point you have: k8s, Claude agents, AWS Bedrock, full observability, CI/CD, and a live system on Hetzner.
That alone puts you ahead of 90% of engineers applying for AI/SRE roles today.

---

## The Technology Universe You Will Master

### AI & LLM Layer
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| Claude API (Anthropic) | Primary LLM — tool use, vision, long context, extended thinking | Most capable model for reasoning + agents |
| Claude Prompt Caching | Anthropic's context caching feature | Cuts costs 90% on repeated system prompts — every production Claude app must use this |
| Reasoning Models (Extended Thinking) | Claude extended thinking, OpenAI o3 | Deep reasoning mode — different cost/latency profile, changes how you design prompts |
| OpenAI API | GPT-4o, embeddings, fine-tuning | Largest ecosystem, still dominant in enterprise |
| Amazon Bedrock | Managed LLM service on AWS | How enterprises deploy AI without managing infra |
| NVIDIA NIM | Microservices for running any model at scale | NVIDIA's play to own inference infrastructure |
| Groq | Ultra-fast LLM inference hardware/API | 10x faster than OpenAI — already disrupting on latency for production routing |
| Cerebras | Wafer-scale chip inference | Fastest inference hardware available — the future of real-time AI |
| Together AI | Fast open-source model inference API | Cheapest tier for high-volume, non-sensitive workloads |
| Fireworks AI | Fast inference platform | Production-grade open-source model serving, OpenAI-compatible |
| Ollama | Run any model locally (Llama, Mistral, etc.) | Air-gapped, cost-free inference for testing |
| vLLM | High-throughput LLM serving engine | How production inference actually scales |
| LiteLLM | Universal LLM proxy/gateway | One API to route between Claude, OpenAI, Bedrock, Groq, Together AI, local |
| Hugging Face | 500k+ models, datasets, Inference API | The GitHub of AI models |
| LangGraph | Stateful multi-agent orchestration | The right way to build complex AI workflows |
| LlamaIndex | RAG framework — connect LLMs to your data | The most widely adopted RAG toolkit in production |
| CrewAI | Role-based autonomous agent teams | Multi-agent systems that collaborate |
| Temporal | Durable workflow execution for agents | Agents that survive crashes, resume from where they stopped |
| DSPy | Program LLMs instead of prompting them | Next-gen prompt engineering |
| Instructor | Structured outputs from any LLM via Pydantic | Make LLMs return reliable JSON |
| Guardrails AI | Validate and constrain LLM outputs | Safety rails — what AOIS must never say or do autonomously |
| Langfuse | LLM observability — traces, evals, cost tracking | You cannot improve what you cannot measure |
| MCP (Model Context Protocol) | Anthropic's standard for AI ↔ tool integration | THE emerging standard — every AI tool will speak this |
| A2A Protocol | Google's Agent-to-Agent communication standard | Agents from different frameworks talking to each other — the multi-vendor future |
| Semantic Kernel | Microsoft's AI SDK | Enterprise AI adoption — .NET shops and Azure use this |
| OpenFeature | Feature flags standard for AI model rollouts | Roll out a new model to 5% of traffic before full release |

### Infrastructure & Cloud
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| Docker | Containerization | Non-negotiable baseline |
| Kubernetes (k8s) | Container orchestration | The OS of the cloud |
| k3s | Lightweight k8s for Hetzner/edge | Real k8s without the overhead |
| Helm | k8s package manager | How production apps are deployed |
| ArgoCD | GitOps — git push = cluster update | Declarative ops, zero manual kubectl |
| Istio | Service mesh — traffic management, mTLS, circuit breaking | How microservices talk to each other securely at scale |
| Crossplane | Provision cloud infra FROM k8s | k8s as the control plane for everything |
| External Secrets Operator | Pull secrets from Vault/AWS into k8s natively | The right pattern for secrets in GitOps |
| KEDA | Event-driven autoscaling | Scale on Kafka messages, queue depth, custom metrics |
| Karpenter | Intelligent node autoscaling (AWS) | AWS's answer to wasted compute |
| Dapr | Distributed Application Runtime | Abstract service-to-service calls, state, pub/sub — microservices without the boilerplate |
| AWS EKS | Managed Kubernetes on AWS | Where enterprise k8s actually lives |
| AWS Bedrock | Managed AI on AWS | How enterprises run LLMs with compliance |
| AWS Lambda | Serverless compute | Event-driven AI inference at scale |
| AWS S3 | Object storage | Ubiquitous — logs, models, artifacts |
| AWS IAM | Identity & access management | You will be asked about this in every interview |
| AWS Secrets Manager | Managed secrets | Production secrets handling |
| Cloudflare Workers | Edge compute + CDN + Zero Trust networking | Run AI inference at the edge, closest to the user |
| Terraform | Infrastructure as Code | Provision everything: Hetzner, AWS, k8s |
| Pulumi | IaC with real programming languages | Terraform but you write Python/TypeScript |
| Ansible | Configuration management + automation | Still in 70% of enterprise environments |

### Observability & SRE
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| Prometheus | Metrics collection | Industry standard |
| Grafana | Visualization | Dashboards for everything |
| Loki | Log aggregation | Prometheus but for logs |
| Tempo | Distributed tracing | Trace requests across services |
| OpenTelemetry | Universal instrumentation standard + LLM semantic conventions | Instrument once, send anywhere — now has LLM-specific conventions for token usage, model calls, costs |
| Jaeger | Tracing backend | Visualize distributed traces |
| Fluent Bit | Lightweight log shipper/router | The sidecar that moves logs from pods to Loki/Kafka |
| VictoriaMetrics | Prometheus at scale | Handles 10x more metrics with less RAM |
| k6 | Load and performance testing | Prove AOIS handles 1000 req/s — with a chart to show it |
| Falco | Runtime security & threat detection | Real-time: "pod just ran curl — is that expected?" |
| eBPF (via Cilium/Tetragon) | Kernel-level observability without agents | The future of observability and security |
| PagerDuty / OpsGenie | Incident management | Where SRE meets human alerting |
| Chaos Mesh | Chaos engineering on k8s | Intentionally break things to build resilience |

### Data & Streaming
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| PostgreSQL + pgvector | Vector search in Postgres | RAG without a separate vector DB |
| Supabase | Postgres + pgvector + auth + realtime + edge functions | How AI startups build backends fast — one platform, everything included |
| Redis | Caching, pub/sub, rate limiting | The Swiss Army knife of data layers |
| Apache Kafka | Distributed event streaming | How logs and events move at scale in every enterprise |
| Qdrant | Purpose-built vector database | Faster than pgvector for large-scale RAG |
| ClickHouse | Columnar DB for analytics | Query billions of log rows in milliseconds |

### Security
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| HashiCorp Vault | Secrets management | Enterprise standard for secrets at scale |
| Trivy | Container + IaC vulnerability scanning | Shift-left security in CI |
| Falco | Runtime threat detection | |
| Cosign / Sigstore | Container image signing | Supply chain security — know your image is authentic |
| SBOM (Syft) | Software Bill of Materials generation | Regulators and enterprises now require this |
| OPA / Gatekeeper | Policy as code for k8s | Enforce: "no container runs as root" cluster-wide |
| Cilium | eBPF networking + zero-trust | Network policy with deep visibility |
| SPIFFE/SPIRE | Workload identity | Service-to-service auth without static secrets |
| Renovate | Automated dependency updates | Never have an unpatched CVE because you forgot to update |
| OWASP LLM Top 10 | AI-specific vulnerability standard | Prompt injection, model DoS, training data poisoning — different from API security |
| PyRIT | Microsoft's AI red-teaming tool | Systematically probe your AI system for vulnerabilities before attackers do |
| Garak | LLM vulnerability scanner | Find prompt injection, jailbreaks, data leakage automatically |
| OpenFGA | Fine-grained authorization engine | Role + attribute-based access control — Auth0's open standard, replacing simple RBAC |

### Frontend & Full Stack
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| React + Vite | Modern frontend | Industry standard SPA framework |
| Next.js | React framework with SSR + API routes | Full stack in one framework — frontend + backend together |
| Vercel AI SDK | TypeScript SDK for AI-powered web apps | Streaming AI responses, tool use, multi-modal in web — becoming the standard for AI UIs |
| TypeScript | Typed JavaScript | How all serious frontend/Node projects are written |
| WebSockets | Real-time communication | Live dashboards without polling |
| HTMX | HTML-driven interactivity | Backend devs can build reactive UIs without React |
| gRPC + Protocol Buffers | High-performance service communication | How microservices talk at scale (faster than REST) |
| FastAPI | Python async backend | Best Python API framework for AI workloads |
| SQLAlchemy + Alembic | Python ORM + database migrations | How you interact with Postgres from Python properly |
| nginx | Reverse proxy + static serving | Every production deployment goes through this |

### Linux & Systems Fundamentals
| Topic | What It Is | Why It Matters |
|-------|-----------|----------------|
| systemd | Service management | How every Linux service starts, stops, restarts |
| Linux networking | ip, iptables, tc, netstat, ss | Troubleshoot anything — pods, nodes, VMs |
| cgroups + namespaces | Resource isolation primitives | What Docker and k8s are built on underneath |
| File systems + disk | lsblk, df, du, mount, fstab | Storage issues are SRE bread and butter |
| SSH + tunneling | Secure remote access | How you get into every server you'll ever manage |
| Bash scripting | Shell automation | Glue for every DevOps workflow |
| Linux performance | top, htop, vmstat, iostat, perf | Diagnose CPU, memory, I/O, network issues |

### AI-Native Development
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| GitHub Actions | CI/CD | Automated test/build/deploy on every push |
| GHCR | GitHub Container Registry | Where your Docker images live |
| Weights & Biases | ML experiment tracking | Track every model run, diff prompts scientifically |
| Modal | Serverless GPU compute | Run GPU workloads without managing infrastructure |
| E2B | Secure code sandboxes for AI agents | Let your agent run code safely |
| Dagger | Portable CI/CD pipelines written in code | CI pipelines that run identically locally and in GitHub Actions |
| Cursor / GitHub Copilot | AI-native IDE | How you will write code going forward |

---

## The Build Roadmap

---

### PHASE 1 — The Intelligence Core
*You will know: Python, FastAPI, Claude API, prompt caching, prompt engineering, structured outputs, multi-model routing*

**v1 — AOIS Core: Log → Intelligence**
The foundation. One endpoint that is smarter than a junior SRE.
- FastAPI + Anthropic SDK (Claude as primary model)
- Structured prompt returning: `summary`, `severity` (P1-P4), `suggested_action`, `confidence`
- Claude prompt caching on system prompt — cost reduction from day one
- Real test cases: OOMKilled, CrashLoopBackOff, disk pressure, 5xx spike, cert expiry
- OpenAI as fallback (your existing key)

**v2 — LiteLLM Gateway**
Stop calling models directly. Build a routing layer with real tiers.
- LiteLLM as a local proxy
- Routing tiers: Claude (high-severity analysis) → GPT-4o-mini (summarization) → Groq/Together AI (high-volume, low-cost) → Ollama (local testing)
- One codebase, any model — swap without code changes
- Cost tracking per request: Groq is 10x cheaper than OpenAI for simple tasks
- This is how production AI systems avoid vendor lock-in and runaway costs

**v3 — Instructor + DSPy: Reliable Intelligence**
Make the outputs trustworthy, not just plausible.
- Instructor for guaranteed Pydantic-validated LLM responses
- DSPy to optimize prompts scientifically — let the framework find the best prompt
- Reasoning models: when to use Claude extended thinking vs. standard — test on real incidents
- Eval suite: score AOIS against a ground truth set of 20 real incidents
- Langfuse integration: every LLM call traced, costed, scored

---

### PHASE 2 — Containerize & Secure
*You will know: Docker, Docker Compose, OWASP API + LLM security, secrets management, image hardening, AI red-teaming*

**v4 — Docker**
- Multi-stage Dockerfile, minimal runtime image (distroless)
- Docker Compose: AOIS + Redis + Postgres + Langfuse locally
- Trivy scan in local workflow — zero HIGH/CRITICAL vulns before proceeding
- Cosign: sign your image

**v5 — Security Hardening**
- OWASP API Top 10 applied to every endpoint
- OWASP LLM Top 10 applied to every AI interaction — prompt injection, model DoS, data leakage
- Prompt injection defense: AOIS accepts untrusted log data — an attacker can embed instructions in a log line
- Garak: automated LLM vulnerability scan against AOIS
- PyRIT: structured red-team session — try to break AOIS before production
- Rate limiting with slowapi
- Input sanitization, max payload size
- Non-root user, read-only filesystem in container
- Vault for secrets (local dev mode)

---

### PHASE 3 — Kubernetes & GitOps
*You will know: k8s fundamentals, Helm, ArgoCD, GitOps, cert-manager, real cloud deployment*

**v6 — k3s on Hetzner: Your First Real Cluster**
- Provision Hetzner VPS with Terraform
- k3s install, kubeconfig, kubectl
- Raw k8s manifests: Deployment, Service, Ingress, ConfigMap, Secret
- cert-manager + Let's Encrypt: AOIS on HTTPS
- Liveness/readiness probes, resource limits, HPA

**v7 — Helm Chart**
- Package AOIS as a Helm chart
- Values per environment
- `helm install aois ./charts/aois -f values.prod.yaml`

**v8 — ArgoCD: GitOps**
- ArgoCD installed on cluster
- Push to main → AOIS deploys itself
- Rollback in one command
- Sync policies, diff detection

**v9 — KEDA: Intelligent Autoscaling**
- Scale AOIS pods based on Kafka topic lag (incoming log volume)
- Zero pods when idle, burst to 20 under load
- This is how production AI services handle traffic spikes

---

### PHASE 4 — AWS Integration
*You will know: EKS, Bedrock, IAM, S3, Lambda, Secrets Manager — the enterprise AI stack*

**v10 — Amazon Bedrock**
- AOIS routes to Claude on Bedrock (enterprise deployment pattern)
- IAM roles, not API keys — the right way to authenticate in AWS
- Compare: Anthropic direct vs Bedrock — latency, cost, compliance posture
- LiteLLM routes to Bedrock seamlessly

**v11 — AWS Lambda: Serverless AOIS**
- Deploy /analyze as a Lambda function
- API Gateway → Lambda → Bedrock
- Cost: $0 when not in use vs always-on Hetzner
- When to use each: decision framework

**v12 — EKS: Enterprise Kubernetes**
- Spin up EKS cluster with Terraform + Karpenter
- Deploy AOIS to EKS — same Helm chart, different values
- Karpenter: nodes provision in 60 seconds when load spikes
- ECR for image storage
- IRSA: IAM Roles for Service Accounts (zero static credentials)
- Compare Hetzner k3s vs EKS: cost, complexity, when to choose each

---

### PHASE 5 — NVIDIA & GPU Inference
*You will know: GPU workloads, NVIDIA NIM, vLLM, Groq, running your own models*

**v13 — NVIDIA NIM**
- Deploy a NIM microservice (Llama or Mistral) on GPU-enabled infra
- AOIS routes low-sensitivity logs to local NIM (free inference)
- High-severity incidents → Claude API (best reasoning)
- Cost-aware routing: NVIDIA for volume, Claude for quality

**v14 — vLLM Inference Server**
- Deploy vLLM on Modal (serverless GPU, no hardware needed)
- Serve an open-source model via OpenAI-compatible API
- AOIS can now use: Claude, GPT-4o, Bedrock, Groq, Together AI, NIM, vLLM — all abstracted by LiteLLM
- Understand: throughput, latency, batching, KV cache

**v15 — Fine-tuning with SRE Data**
- Curate a dataset: 500 real log samples + ideal AOIS responses
- LoRA fine-tune a small model (Mistral 7B) on Modal GPU
- Deploy fine-tuned model via vLLM
- Eval: fine-tuned vs base vs Claude vs reasoning model (extended thinking) — where does each win?

---

### PHASE 6 — Full SRE Observability Stack
*You will know: OpenTelemetry + LLM conventions, Prometheus, Grafana, Loki, Tempo, eBPF, Kafka*

**v16 — OpenTelemetry End-to-End**
- Instrument every service: FastAPI, LiteLLM proxy, Redis, Postgres
- Trace: HTTP request → prompt build → LLM call → cache → response
- Metrics, logs, traces in Grafana (Loki + Tempo + Prometheus unified)
- OTel LLM semantic conventions: standardized spans for model name, token usage, cost, prompt/response
- Custom metric: LLM tokens/request, cost/incident, cache hit rate, prompt cache savings

**v17 — Kafka: Real Log Streaming**
- Kafka on k8s (Strimzi operator)
- Applications publish logs to Kafka topic
- AOIS consumes in real-time, analyzes, publishes results to another topic
- KEDA scales AOIS pods based on Kafka consumer lag
- This is how SRE log pipelines work at Netflix, Uber, Cloudflare

**v18 — eBPF with Cilium + Falco**
- Cilium replaces kube-proxy: L7 network policy, encryption, deep observability
- Falco: runtime rules — "alert if any container makes an unexpected syscall"
- Tetragon: trace every process, network connection, file access at kernel level
- AOIS ingests Falco alerts — AI-analyzed security events

**v19 — Chaos Engineering**
- Chaos Mesh: kill random pods, inject latency, corrupt network packets
- Does AOIS detect and alert on the chaos it's subjected to?
- Game day: 1 hour of chaos, measure MTTR with and without AOIS
- SLO definition: 99.5% of P1 alerts analyzed within 30 seconds

---

### PHASE 7 — Autonomous Agents
*You will know: Claude tool use, MCP, A2A, Temporal, LangGraph, multi-agent systems, autonomous remediation*

**v20 — Claude Tool Use: AOIS Sees the Cluster**
- Give AOIS tools: `get_pod_logs`, `describe_node`, `list_events`, `get_metrics`
- AOIS goes from read-only to investigative
- Ask: "Why is the auth service slow?" — AOIS pulls its own evidence

**v21 — MCP Server: AOIS as a Platform**
- Build AOIS as an MCP server
- Any MCP-compatible client (Claude.ai, Cursor, custom tools) can use AOIS capabilities
- This is the emerging standard — you will be ahead of most engineers on this

**v22 — A2A Protocol + Temporal: Durable Cross-Framework Agents**
- Implement Google's A2A protocol: AOIS can now communicate with agents built on other frameworks
- MCP (v21) = how tools connect to Claude. A2A = how agents from different vendors talk to each other
- Temporal: wrap AOIS agent workflows in durable execution — survives crashes, resumes mid-task
- An incident investigation that takes 10 minutes won't lose state if a pod restarts at minute 7
- This is the multi-vendor agent future: Claude agents + LangGraph agents + CrewAI agents collaborating

**v23 — LangGraph: Autonomous SRE Loop**
- Stateful agent graph: Detect → Investigate → Hypothesize → Verify → Remediate → Report
- Human-in-the-loop: approval gate before any write actions
- Full audit trail persisted to Postgres
- Handles multi-step incidents: one root cause, five downstream effects
- Dapr: abstract service-to-service calls between agent nodes — portable across cloud providers

**v24 — CrewAI: Multi-Agent Operations Team**
- Crew: Detector agent, Root Cause Analyst agent, Remediation agent, Report Writer agent
- Each agent has different tools and context
- They collaborate, challenge each other, produce better output than any single agent
- The future of SRE: AI teams, not AI assistants

**v25 — E2B: Safe Code Execution**
- AOIS can write and run remediation scripts in a sandboxed environment
- Test the fix before applying it to production
- AOIS generates kubectl patch → runs it in E2B sandbox → validates → proposes to human

---

### PHASE 8 — Full Stack Dashboard
*You will know: React, Vercel AI SDK, WebSockets, HTMX, nginx, auth, real-time UI*

**v26 — React Dashboard**
- Real-time feed of logs + AOIS analysis via WebSocket
- Vercel AI SDK: streaming AI responses directly to the UI — the modern pattern for AI web apps
- Severity heatmap, incident timeline, agent action log
- Approve/reject remediation proposals with one click
- Served via nginx, bundled into the Helm chart

**v27 — Auth & Multi-tenancy**
- JWT + refresh tokens (FastAPI + python-jose)
- RBAC: viewer, analyst, operator, admin
- OpenFGA: fine-grained authorization — "analyst can approve P3 remediations but not P1"
- SPIFFE/SPIRE for service-to-service identity (no static service account tokens)
- Supabase: explore as an alternative backend — Postgres + pgvector + auth + realtime in one

---

### PHASE 9 — Production CI/CD & Platform Engineering
*You will know: GitHub Actions, image signing, zero-downtime deploys, Internal Developer Platform*

**v28 — GitHub Actions: Full Pipeline**
- PR: lint, test, Trivy scan, Cosign sign
- Merge to main: build → push GHCR → update Helm values → ArgoCD sync
- Deploy to both Hetzner k3s AND AWS EKS from same pipeline
- Slack notification with deploy summary

**v29 — Weights & Biases: ML Operations**
- Track every prompt version as an experiment
- A/B test: Claude standard vs extended thinking vs fine-tuned model
- Log: latency, cost, accuracy score, user feedback
- This is how AI products improve systematically, not by guessing

**v30 — Internal Developer Platform (IDP)**
- Backstage or Port: self-service portal for the team
- Developers request: "spin up new AOIS tenant" → Crossplane provisions infra → ArgoCD deploys
- This is Platform Engineering — the hottest role in DevOps right now
- AOIS is a service in the catalog, with docs, runbooks, SLOs, owners

---

### PHASE 10 — The Pinnacle
*Multimodal AI, edge inference, AI safety, computer use, governance — the things coming next*

**v31 — Multimodal AOIS**
- Claude Vision: analyze screenshots of Grafana dashboards, architecture diagrams
- AOIS can now say: "I can see from this dashboard screenshot that..."
- Upload a k8s topology diagram → AOIS identifies blast radius

**v32 — Edge AI with Ollama**
- Run AOIS locally on a Hetzner edge node, no internet required
- Air-gapped analysis for sensitive environments
- Synchronize findings to central cluster when connectivity returns

**v33 — Weights, Evals & Red-teaming**
- Systematic evaluation framework for AOIS output quality
- Red team with PyRIT + Garak at scale — automated adversarial testing
- Try to make AOIS give wrong severity, hallucinate solutions, leak data
- Constitutional AI principles applied to AOIS: what should it never do autonomously?
- This is AI safety applied to a real product you built

**v34 — Computer Use + AI Governance**
- Claude Computer Use: AOIS can interact with UIs — open Grafana, click through dashboards, file tickets
- Playwright + AI: browser automation driven by natural language instructions
- EU AI Act compliance layer: risk classification, audit trails, model cards, human oversight gates
- This is where AOIS becomes enterprise-deployable — governance is what gets AI into regulated industries

---

## Current State

### Preserved
- OpenAI API key in `.env` — used when needed (v2 LiteLLM routing, v1 fallback, v15 comparison)
- `.gitignore` committed — `.env` is protected

### Auto-Save Setup (Active)
- PostToolUse hook: commits after every file write/edit
- Stop hook: commits at session end
- Both in `~/.claude/settings.json` — activate on next session restart

### Current Position
- Pre-v1. Baseline committed (d1d7773). Roadmap finalized.

### What v1 builds next
- `main.py` — rewritten with Anthropic SDK, structured Pydantic output, prompt caching, OpenAI fallback
- `requirements.txt` — proper dependency file

---

## Session Rules
1. Every session builds something real
2. Every session ends with a git commit
3. CLAUDE.md updated at session end: what was done, what is next
4. Explanations happen during building
5. When a tool is introduced, we use it on AOIS — never a toy example
6. Any decision or preference agreed on is saved to memory immediately
