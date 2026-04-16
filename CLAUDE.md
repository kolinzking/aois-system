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
| Claude API (Anthropic) | Primary LLM — tool use, vision, long context | Most capable model for reasoning + agents |
| OpenAI API | GPT-4o, embeddings, fine-tuning | Largest ecosystem, still dominant in enterprise |
| Amazon Bedrock | Managed LLM service on AWS | How enterprises deploy AI without managing infra |
| NVIDIA NIM | Microservices for running any model at scale | NVIDIA's play to own inference infrastructure |
| Ollama | Run any model locally (Llama, Mistral, etc.) | Air-gapped, cost-free inference for testing |
| vLLM | High-throughput LLM serving engine | How production inference actually scales |
| LiteLLM | Universal LLM proxy/gateway | One API to route between Claude, OpenAI, Bedrock, local |
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
| A2A Protocol | Google's Agent-to-Agent communication standard | Agents from different frameworks talking to each other |
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
| AWS EKS | Managed Kubernetes on AWS | Where enterprise k8s actually lives |
| AWS Bedrock | Managed AI on AWS | |
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
| OpenTelemetry | Universal instrumentation standard | Instrument once, send anywhere |
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

### Frontend & Full Stack
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| React + Vite | Modern frontend | Industry standard SPA framework |
| Next.js | React framework with SSR + API routes | Full stack in one framework — frontend + backend together |
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
*You will know: Python, FastAPI, Claude API, prompt engineering, structured outputs, multi-model routing*

**v1 — AOIS Core: Log → Intelligence**
The foundation. One endpoint that is smarter than a junior SRE.
- FastAPI + Anthropic SDK (Claude as primary model)
- Structured prompt returning: `summary`, `severity` (P1-P4), `suggested_action`, `confidence`
- Real test cases: OOMKilled, CrashLoopBackOff, disk pressure, 5xx spike, cert expiry
- OpenAI as fallback (your existing key)
- Git commit #1

**v2 — LiteLLM Gateway**
Stop calling models directly. Build a routing layer.
- LiteLLM as a local proxy
- Route: Claude for analysis, GPT-4o-mini for summarization, local Ollama for testing
- One codebase, any model — swap without code changes
- Cost tracking per request baked in

**v3 — Instructor + DSPy: Reliable Intelligence**
Make the outputs trustworthy, not just plausible.
- Instructor for guaranteed Pydantic-validated LLM responses
- DSPy to optimize prompts scientifically — let the framework find the best prompt
- Eval suite: score AOIS against a ground truth set of 20 real incidents
- Langfuse integration: every LLM call traced, costed, scored

---

### PHASE 2 — Containerize & Secure
*You will know: Docker, Docker Compose, OWASP API security, secrets management, image hardening*

**v4 — Docker**
- Multi-stage Dockerfile, minimal runtime image (distroless)
- Docker Compose: AOIS + Redis + Postgres + Langfuse locally
- Trivy scan in local workflow — zero HIGH/CRITICAL vulns before proceeding
- Cosign: sign your image

**v5 — Security Hardening**
- Prompt injection defense (AOIS accepts untrusted log data — this matters)
- Rate limiting with slowapi
- Input sanitization, max payload size
- Non-root user, read-only filesystem in container
- Vault for secrets (local dev mode)
- OWASP API Top 10 applied to every endpoint

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
*You will know: GPU workloads, NVIDIA NIM, vLLM, running your own models*

**v13 — NVIDIA NIM**
- Deploy a NIM microservice (Llama or Mistral) on GPU-enabled infra
- AOIS routes low-sensitivity logs to local NIM (free inference)
- High-severity incidents → Claude API (best reasoning)
- Cost-aware routing: NVIDIA for volume, Claude for quality

**v14 — vLLM Inference Server**
- Deploy vLLM on Modal (serverless GPU, no hardware needed)
- Serve an open-source model via OpenAI-compatible API
- AOIS can now use: Claude, GPT-4o, Bedrock, NIM, vLLM — all abstracted by LiteLLM
- Understand: throughput, latency, batching, KV cache

**v15 — Fine-tuning with SRE Data**
- Curate a dataset: 500 real log samples + ideal AOIS responses
- LoRA fine-tune a small model (Mistral 7B) on Modal GPU
- Deploy fine-tuned model via vLLM
- Eval: fine-tuned vs base vs Claude — where does specialization win?

---

### PHASE 6 — Full SRE Observability Stack
*You will know: OpenTelemetry, Prometheus, Grafana, Loki, Tempo, eBPF, Kafka*

**v16 — OpenTelemetry End-to-End**
- Instrument every service: FastAPI, LiteLLM proxy, Redis, Postgres
- Trace: HTTP request → prompt build → LLM call → cache → response
- Metrics, logs, traces in Grafana (Loki + Tempo + Prometheus unified)
- Custom metric: LLM tokens/request, cost/incident, cache hit rate

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
*You will know: Claude tool use, MCP, LangGraph, multi-agent systems, autonomous remediation*

**v20 — Claude Tool Use: AOIS Sees the Cluster**
- Give AOIS tools: `get_pod_logs`, `describe_node`, `list_events`, `get_metrics`
- AOIS goes from read-only to investigative
- Ask: "Why is the auth service slow?" — AOIS pulls its own evidence

**v21 — MCP Server: AOIS as a Platform**
- Build AOIS as an MCP server
- Any MCP-compatible client (Claude.ai, Cursor, custom tools) can use AOIS capabilities
- This is the emerging standard — you will be ahead of most engineers on this

**v22 — LangGraph: Autonomous SRE Loop**
- Stateful agent graph: Detect → Investigate → Hypothesize → Verify → Remediate → Report
- Human-in-the-loop: approval gate before any write actions
- Full audit trail persisted to Postgres
- Handles multi-step incidents: one root cause, five downstream effects

**v23 — CrewAI: Multi-Agent Operations Team**
- Crew: Detector agent, Root Cause Analyst agent, Remediation agent, Report Writer agent
- Each agent has different tools and context
- They collaborate, challenge each other, produce better output than any single agent
- The future of SRE: AI teams, not AI assistants

**v24 — E2B: Safe Code Execution**
- AOIS can write and run remediation scripts in a sandboxed environment
- Test the fix before applying it to production
- AOIS generates kubectl patch → runs it in E2B sandbox → validates → proposes to human

---

### PHASE 8 — Full Stack Dashboard
*You will know: React, WebSockets, HTMX, nginx, auth, real-time UI*

**v25 — React Dashboard**
- Real-time feed of logs + AOIS analysis via WebSocket
- Severity heatmap, incident timeline, agent action log
- Approve/reject remediation proposals with one click
- Served via nginx, bundled into the Helm chart

**v26 — Auth & Multi-tenancy**
- JWT + refresh tokens (FastAPI + python-jose)
- RBAC: viewer, analyst, operator, admin
- SPIFFE/SPIRE for service-to-service identity (no static service account tokens)

---

### PHASE 9 — Production CI/CD & Platform Engineering
*You will know: GitHub Actions, image signing, zero-downtime deploys, Internal Developer Platform*

**v27 — GitHub Actions: Full Pipeline**
- PR: lint, test, Trivy scan, Cosign sign
- Merge to main: build → push GHCR → update Helm values → ArgoCD sync
- Deploy to both Hetzner k3s AND AWS EKS from same pipeline
- Slack notification with deploy summary

**v28 — Weights & Biases: ML Operations**
- Track every prompt version as an experiment
- A/B test: Claude 3.5 Sonnet vs Opus vs fine-tuned model
- Log: latency, cost, accuracy score, user feedback
- This is how AI products improve systematically, not by guessing

**v29 — Internal Developer Platform (IDP)**
- Backstage or Port: self-service portal for the team
- Developers request: "spin up new AOIS tenant" → Crossplane provisions infra → ArgoCD deploys
- This is Platform Engineering — the hottest role in DevOps right now
- AOIS is a service in the catalog, with docs, runbooks, SLOs, owners

---

### PHASE 10 — The Pinnacle
*Multimodal AI, edge inference, AI safety, the things coming next*

**v30 — Multimodal AOIS**
- Claude Vision: analyze screenshots of Grafana dashboards, architecture diagrams
- AOIS can now say: "I can see from this dashboard screenshot that..."
- Upload a k8s topology diagram → AOIS identifies blast radius

**v31 — Edge AI with Ollama**
- Run AOIS locally on a Hetzner edge node, no internet required
- Air-gapped analysis for sensitive environments
- Synchronize findings to central cluster when connectivity returns

**v32 — Weights, Evals & Red-teaming**
- Systematic evaluation framework for AOIS output quality
- Red team: try to make AOIS give wrong severity, hallucinate solutions
- Constitutional AI principles applied to AOIS: what should it never do autonomously?
- This is AI safety applied to a real product you built

---

## Current State

### Preserved
- OpenAI API key in `.env` — used when needed (v2 LiteLLM routing, v1 fallback, v15 comparison)

### Everything else
- Starting fresh — clean slate

### What v1 builds
- `main.py` — rewritten from scratch with Claude API
- `requirements.txt` — proper dependency file
- `.gitignore` — secrets never committed
- First real commit to GitHub

---

## Session Rules
1. Every session builds something real
2. Every session ends with a git commit
3. CLAUDE.md updated at session end: what was done, what is next
4. Explanations happen during building
5. When a tool is introduced, we use it on AOIS — never a toy example
