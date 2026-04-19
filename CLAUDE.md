# AOIS — AI Operations Intelligence System
## Collins' Path to the Pinnacle of the AI Wave

---

## Who Collins Is
- SRE/DevOps engineer. Done sitting on the sidelines.
- Goal: Be at the forefront of where AI is heading — not where employers currently are
- Evidence: Everything builds in this repo. GitHub is the CV.
- Resources: Hetzner cloud, OpenAI key, Anthropic key
- Rule: Build first. No theory without code.

---

## Curriculum Philosophy
Tools are included based on **where AI is heading**, not where employers currently are.
Employers in 2023 weren't hiring for LangGraph, MCP, or Claude API.
The engineers who learned them anyway are the ones being fought over in 2026.
This curriculum prepares for 2026-2028, not today.

---

## Content Quality Standard (Non-Negotiable — Applies to Every Version, Past and Future)

### The Bar in One Sentence
Every `vN/notes.md` must be self-contained, practical-first, production-grade material that a motivated self-learner can follow without a teacher and come out with genuine mastery — not familiarity, not awareness, but the ability to do the thing under pressure.

### What This Competes With
The content in this repo must be better than:
- **MIT Missing Semester** — the gold standard for "what school didn't teach you": precise, runbook-quality, every concept earned through a concrete problem
- **Learn X the Hard Way** — famous for recognition/recall exercises; learners trigger real errors before they see real solutions
- **fast.ai curriculum** — practical first, theory only appears to explain what you already built
- **Official Kubernetes docs** — exact expected output on every command, nothing left ambiguous

If a section reads like a Wikipedia summary or a vendor README, it is not done.

### Content Principles (enforced in every version)

**1. Practical-first — theory earns its place**
Never introduce a concept before showing the problem it solves. The learner feels the pain first.
- Wrong: "KEDA is a Kubernetes event-driven autoscaler that..." then installation steps
- Right: Show fixed replicas burning money on idle nights, a load spike that strains the pod count — then introduce KEDA as the answer
- Theory only appears after the learner has seen what breaks without it

**2. Every command has expected output**
Any command where "did it work?" is ambiguous MUST show the expected output verbatim. This is how a learner working alone at 2am knows they're on track.

**3. Errors are curriculum, not accidents**
Common mistakes must be deliberately triggered, not just described. The learner runs the wrong thing, sees the exact error, fixes it. This is the recognition/recall pattern — it produces real retention. If you've only ever seen success, you cannot diagnose failure in production.

**4. Production-grade, not tutorial-grade**
Every config, command, and pattern must reflect how this is done at organizations running it at scale. No `latest` image tags. No hardcoded secrets. No `replicas: 1` unless explained. The learner's muscle memory should be built on production habits from day one.

**5. Fully self-contained**
A learner with the stated prerequisites and nothing else must be able to complete the version from these notes alone. No "see the official docs for X" without providing the exact command or section needed. The notes are the source of truth.

**6. Forward connections are explicit**
Every concept connects explicitly to where it reappears. "You are learning the shape now so v17 is a three-line change." This is what separates a curriculum from a collection of tutorials. The learner must see how everything compounds.

**7. Mental models over memorization**
Build a model the learner can reason from, not a list of commands to copy. When the command is forgotten (it will be), the mental model lets them derive or find it. This is the difference between a practitioner and someone who copy-pasted through a tutorial.

**8. AI content reflects where AI is heading, not where it currently is**
Every AI section covers current state AND direction. What does production look like in 2026-2028? What is being superseded? What pattern persists when the framework changes? The learner is being prepared for what's coming, not certified in what exists today.

**9. User-friendly language**
No unexplained jargon. Every new term defined in one tight plain-English sentence when it first appears. Long concept sections broken by STOP exercises — the learner never reads more than ~10 minutes without doing something.

### Mandatory Structure (every vN/notes.md, in this order)

1. `⏱ **Estimated time: X–Y hours**` — immediately under the `#` heading
2. `## Prerequisites` — verification commands with expected output (not just "have v8 done")
3. `## Learning Goals` — "By the end you will be able to:" with concrete ability bullets, not topic names
4. **Body** — practical-first, theory follows demonstration, every command has expected output
5. **≥3 `▶ STOP — do this now` exercises** — hands-on, embedded in the body, each with expected output
6. `## Common Mistakes` — named errors, exact symptom shown, fix given — recognition then recall (trigger the error, see it, fix it)
7. `## Troubleshooting` — verbatim error messages, diagnosis steps, fix
8. **Connection to later phases** — explicit forward references ("this is what changes in vN")
9. `## Mastery Checkpoint` — 6–9 practical tasks closing with "The mastery bar:" statement

### Minimum length
- 600+ lines for focused versions
- 800+ lines for complex versions (Kafka, LangGraph, multi-agent, observability stacks, GPU inference)
- Length is a consequence of depth, not padding. Every line earns its place.

### Audit command (run before declaring any version complete)
```bash
grep -c 'Estimated time\|## Prerequisites\|Learning [Gg]oals\|STOP — do this now\|Common Mistakes\|## Troubleshooting\|Connection to\|Mastery Checkpoint' curriculum/phaseN/vN/notes.md
```
Expected: 8+ matches. Line count must meet the minimum above. If either fails, the notes are not done.

### Retroactive application
This standard applies to ALL versions v0.1 through v34. Versions v0.1–v9 have been written — any found below this bar in a future session must be fixed before that session proceeds to the next version.

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
| Claude Prompt Caching | Anthropic's context caching | Cuts costs 90% on repeated system prompts — every production Claude app uses this |
| Reasoning Models | Claude extended thinking, OpenAI o3 | Deep reasoning mode — different cost/latency profile, changes how you design for production |
| OpenAI API | GPT-4o, embeddings, fine-tuning | Largest ecosystem, dominant in enterprise |
| Amazon Bedrock | Managed LLM service on AWS | How enterprises deploy AI with compliance, no infra to manage |
| NVIDIA NIM | Microservices for running any model at scale | NVIDIA's play to own inference infrastructure |
| Groq | Ultra-fast LLM inference API | 10x faster than OpenAI — the latency benchmark for production routing |
| Cerebras | Wafer-scale chip inference | Inference hardware race is real — understanding this landscape is infrastructure-layer AI knowledge |
| Together AI | Fast open-source model inference API | Cheapest tier for high-volume workloads |
| Fireworks AI | Fast inference platform | Different model availability and pricing from Groq/Together — full routing landscape matters |
| Ollama | Run any model locally | Air-gapped, cost-free inference for testing |
| vLLM | High-throughput LLM serving engine | How production inference actually scales |
| LiteLLM | Universal LLM proxy/gateway | One API to route between all providers — Claude, OpenAI, Bedrock, Groq, Together, Fireworks, local |
| Hugging Face | 500k+ models, datasets, Inference API | The GitHub of AI models |
| LangGraph | Stateful multi-agent orchestration | The right way to build complex AI workflows |
| LlamaIndex | RAG framework — connect LLMs to your data | Most widely adopted RAG toolkit in production |
| CrewAI | Role-based autonomous agent teams | Multi-agent collaboration — the pattern matters even if frameworks consolidate |
| Temporal | Durable workflow execution for agents | Agents that survive crashes and resume — the difference between demo and production |
| DSPy | Program LLMs instead of prompting them | The future of prompt engineering: systematic optimization over artisanal hand-crafting |
| Instructor | Structured outputs from any LLM via Pydantic | Make LLMs return reliable JSON — used in virtually every production AI app |
| Guardrails AI | Runtime output validation and safety rails | AI in medical/legal/finance requires output safety — this field is growing fast |
| Langfuse | LLM observability — traces, evals, cost tracking | You cannot improve what you cannot measure |
| MCP (Model Context Protocol) | Anthropic's standard for AI ↔ tool integration | THE emerging standard — every AI tool will speak this |
| A2A Protocol | Google's Agent-to-Agent communication standard | Multi-vendor agent interoperability — Google + Anthropic are both building this layer |
| Semantic Kernel | Microsoft's AI SDK | Enterprise AI in .NET/Azure shops — Microsoft has the largest enterprise footprint on earth |
| AutoGen (Microsoft) | Multi-agent conversation framework | The #2 most deployed agent framework — conversation-based loops, built-in code execution, human-in-loop. Microsoft-backed. Every enterprise AI shop is evaluating or running this |
| Google ADK | Google's Agent Development Kit | Google's official multi-agent framework (2025) — built for Gemini, deploys to Vertex AI. Represents Google's architectural answer to LangGraph. Must-know as the Google agent standard |
| OpenAI Agents SDK | OpenAI's production agent framework (2025) | Handoffs between agents, built-in guardrails, tracing hooks. Largest developer ecosystem means you will encounter this pattern in every enterprise codebase |
| Pydantic AI | Type-safe agent framework from the Pydantic team | Built by the same team behind Instructor. Agents with full type safety, dependency injection, and real testability — the Python-native way to build reliable agents |
| Mem0 / MemGPT (Letta) | Persistent memory layer for AI agents | The layer that separates agents from chatbots. Short-term + long-term + episodic memory across sessions. Without this, every agent conversation starts from zero |
| AgentOps | Observability built for agent workflows | Langfuse traces LLM calls. AgentOps traces agent sessions, multi-step loops, agent cost per task, failure modes. You need both layers when agents go to production |
| Amazon Bedrock Agents | AWS managed agent service | Distinct from Bedrock-as-LLM. Managed tool routing, knowledge bases, multi-agent orchestration — enterprise agents without infrastructure. How AWS customers will run agents at scale |
| OpenFeature | Feature flags for AI model rollouts | Safe model rollouts: ship new model to 5% of traffic, measure, then promote |

### Infrastructure & Cloud
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| Docker | Containerization | Non-negotiable baseline |
| Kubernetes (k8s) | Container orchestration | The OS of the cloud |
| k3s | Lightweight k8s for Hetzner/edge | Real k8s without the overhead |
| Helm | k8s package manager | How production apps are deployed |
| ArgoCD | GitOps — git push = cluster update | Declarative ops, zero manual kubectl |
| Istio | Service mesh — traffic management, mTLS, circuit breaking | How microservices talk to each other securely at scale |
| Crossplane | Provision cloud infra FROM k8s | k8s as the control plane for everything — Platform Engineering core |
| External Secrets Operator | Pull secrets from Vault/AWS into k8s natively | The right pattern for secrets in GitOps |
| KEDA | Event-driven autoscaling | Scale on Kafka messages, queue depth, custom metrics |
| Karpenter | Intelligent node autoscaling (AWS) | AWS's answer to wasted compute |
| Dapr | Distributed Application Runtime | Multi-agent systems need reliable messaging, state, pub/sub — Dapr abstracts all of it |
| AWS EKS | Managed Kubernetes on AWS | Where enterprise k8s actually lives |
| AWS Bedrock | Managed AI on AWS | How enterprises run LLMs with compliance |
| AWS Lambda | Serverless compute | Event-driven AI inference at scale |
| AWS S3 | Object storage | Ubiquitous — logs, models, artifacts |
| AWS IAM | Identity & access management | Every AWS interview asks about this |
| AWS Secrets Manager | Managed secrets | Production secrets handling |
| Cloudflare Workers | Edge compute + CDN + Zero Trust networking | Run AI inference at the edge, closest to the user |
| Terraform | Infrastructure as Code | Provision everything: Hetzner, AWS, k8s |
| Pulumi | IaC with real programming languages | Terraform's HCL is declarative and limited — Pulumi in Python means real logic, loops, abstractions |
| Ansible | Configuration management + automation | Still in 70% of enterprise environments |

### Observability & SRE
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| Prometheus | Metrics collection | Industry standard |
| Grafana | Visualization | Dashboards for everything |
| Loki | Log aggregation | Prometheus but for logs |
| Tempo | Distributed tracing | Trace requests across services |
| OpenTelemetry | Universal instrumentation standard + LLM semantic conventions | Instrument once, send anywhere — LLM conventions standardize token/cost tracing |
| Fluent Bit | Lightweight log shipper/router | The sidecar that moves logs from pods to Loki/Kafka |
| VictoriaMetrics | Prometheus at scale | AI systems generate massive telemetry — Prometheus has limits, VictoriaMetrics solves them |
| k6 | Load and performance testing | Prove AOIS handles 1000 req/s — with a chart to show it |
| Falco | Runtime security & threat detection | Real-time: "pod just ran curl — is that expected?" |
| eBPF (via Cilium/Tetragon) | Kernel-level observability without agents | The future of observability and security |
| PagerDuty / OpsGenie | Incident management | Where SRE meets human alerting |
| Chaos Mesh | Chaos engineering on k8s | Intentionally break things to build resilience |

### Data & Streaming
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| PostgreSQL + pgvector | Vector search in Postgres | RAG without a separate vector DB |
| Supabase | Postgres + pgvector + auth + realtime + edge functions | How AI products are built fast — full stack in one managed platform |
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
| PyRIT | Microsoft's AI red-teaming framework | Systematic adversarial testing — AI red-teaming will be standard in CI pipelines |
| Garak | LLM vulnerability scanner | Automated: find prompt injection, jailbreaks, data leakage before attackers do |
| OpenFGA | Fine-grained authorization engine | When AI agents act on behalf of users, simple RBAC breaks — this is the direction |

### Frontend & Full Stack
| Tool | What It Is | Why It Matters |
|------|-----------|----------------|
| React + Vite | Modern frontend | Industry standard SPA framework |
| Next.js | React framework with SSR + API routes | Full stack in one framework |
| Vercel AI SDK | TypeScript SDK for AI-powered web apps | Streaming AI responses, tool use, multi-modal — the standard for AI UIs |
| TypeScript | Typed JavaScript | How all serious frontend/Node projects are written |
| WebSockets | Real-time communication | Live dashboards without polling |
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
| Dagger | Portable CI/CD pipelines written in code | Same pipeline locally and in CI — reproducibility for AI workflows |
| Cursor / GitHub Copilot | AI-native IDE | How you will write code going forward |

---

## The Build Roadmap

---

### PHASE 0 — The Foundation
*You will know: Linux, bash scripting, git, HTTP, Python patterns, FastAPI basics, how LLMs work*

**v0.1 — Linux Essentials**
- Filesystem navigation, permissions, processes, environment variables, SSH
- Pipes, redirection, grep/awk/sed
- Build: `sysinfo.sh` — system report script

**v0.2 — Bash Scripting**
- Variables, conditionals, loops, functions, exit codes, text processing
- Build: `log_analyzer.sh` — brittle regex log analyzer that sets up the "why AI" moment in v1

**v0.3 — Git & GitHub**
- Mental model (snapshots not diffs), the three areas, daily workflow
- .gitignore, branches, remotes, commit message conventions, GitHub as CV
- Build: This repo committed properly with real history

**v0.4 — Networking & HTTP**
- IP addresses, DNS, ports, TCP/IP, HTTP methods, status codes, headers
- curl mastery, JSON, REST conventions
- Build: curl real APIs (GitHub), understand every step of a request/response cycle

**v0.5 — Python for This Project**
- Virtual environments, requirements.txt, .env + python-dotenv, type hints
- Pydantic BaseModel and Field constraints, async/await, error handling
- Build: the core Pydantic models for AOIS from scratch

**v0.6 — Your First API (No AI)**
- FastAPI, uvicorn, ASGI, routing, request/response, HTTPException, middleware
- OpenAPI auto-docs at /docs
- Build: mock AOIS endpoint with regex analysis — shows the limitation

**v0.7 — How LLMs Work**
- Tokens, context windows, system prompts, temperature, max_tokens
- Input/output token cost, prompt caching economics
- Raw Claude API call via curl and Python SDK — free text response, no structure
- Build: raw SDK call, understand why unstructured output needs tooling → sets up v1

---

### PHASE 1 — The Intelligence Core
*You will know: Python, FastAPI, Claude API, prompt caching, structured outputs, multi-model routing*

**v1 — AOIS Core: Log → Intelligence**
The foundation. One endpoint that is smarter than a junior SRE.
- FastAPI + Anthropic SDK (Claude as primary model)
- Structured output: `summary`, `severity` (P1-P4), `suggested_action`, `confidence`
- Claude prompt caching on system prompt — cost reduction from day one
- Real test cases: OOMKilled, CrashLoopBackOff, disk pressure, 5xx spike, cert expiry
- OpenAI as fallback

**v2 — LiteLLM Gateway**
Stop calling models directly. Build a routing layer with real cost tiers.
- LiteLLM as a local proxy
- Routing tiers: Claude (high-severity) → GPT-4o-mini (summarization) → Groq/Together AI/Fireworks (high-volume, cheap) → Ollama (local testing)
- One codebase, any model — swap without code changes
- Cost tracking per request: understand what each tier actually costs

**v3 — Instructor + DSPy: Reliable Intelligence**
Make the outputs trustworthy and systematically optimal.
- Instructor for guaranteed Pydantic-validated LLM responses
- DSPy: define what good output looks like, let the framework find the best prompt — the future of prompt engineering
- Reasoning models: when to use Claude extended thinking vs. standard — measure cost/latency tradeoff on real incidents
- Eval suite: score AOIS against a ground truth set of 20 real incidents
- Langfuse: every LLM call traced, costed, scored

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
- OWASP LLM Top 10 applied to every AI interaction — prompt injection, model DoS, training data leakage
- Prompt injection defense: AOIS accepts untrusted log data — an attacker can embed instructions in a log line
- Guardrails AI: runtime output validation — AOIS should never recommend "delete the cluster"
- PyRIT + Garak: systematic red-team session — automated adversarial testing before production
- Rate limiting with slowapi, input sanitization, max payload size
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

**v10 — Amazon Bedrock + Bedrock Agents**
- AOIS routes to Claude on Bedrock (enterprise deployment pattern)
- IAM roles, not API keys — the right way to authenticate in AWS
- Compare: Anthropic direct vs Bedrock — latency, cost, compliance posture
- LiteLLM routes to Bedrock seamlessly
- Bedrock Agents: expose AOIS analysis as a managed agent with automatic tool routing and knowledge base — the fully managed AWS agent pattern. This is what enterprises mean when they say "we're deploying agents on AWS"

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
*You will know: GPU workloads, NVIDIA NIM, vLLM, inference hardware landscape, running your own models*

**v13 — NVIDIA NIM**
- Deploy a NIM microservice (Llama or Mistral) on GPU-enabled infra
- AOIS routes low-sensitivity logs to local NIM (free inference)
- High-severity incidents → Claude API (best reasoning)
- Cost-aware routing: NVIDIA for volume, Claude for quality

**v14 — vLLM Inference Server**
- Deploy vLLM on Modal (serverless GPU, no hardware needed)
- Serve an open-source model via OpenAI-compatible API
- AOIS can now use: Claude, OpenAI, Bedrock, Groq, Together AI, Fireworks, NIM, vLLM — all via LiteLLM
- Understand: throughput, latency, batching, KV cache
- Inference hardware comparison: NVIDIA GPU vs Groq LPU vs Cerebras WSE — why they exist, what each wins at

**v15 — Fine-tuning with SRE Data**
- Curate a dataset: 500 real log samples + ideal AOIS responses
- LoRA fine-tune a small model (Mistral 7B) on Modal GPU
- Deploy fine-tuned model via vLLM
- Eval: fine-tuned vs base vs Claude vs Claude extended thinking — where does specialization beat general reasoning?

---

### PHASE 6 — Full SRE Observability Stack
*You will know: OpenTelemetry + LLM conventions, Prometheus, Grafana, Loki, Tempo, eBPF, Kafka*

**v16 — OpenTelemetry End-to-End**
- Instrument every service: FastAPI, LiteLLM proxy, Redis, Postgres
- Trace: HTTP request → prompt build → LLM call → cache → response
- Metrics, logs, traces unified in Grafana (Loki + Tempo + Prometheus)
- OTel LLM semantic conventions: standardized spans for model, tokens, cost, cache hits
- VictoriaMetrics: drop-in Prometheus replacement for when AI telemetry volume gets serious

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
*You will know: Claude tool use, MCP, A2A, Temporal, LangGraph, AutoGen, Mem0, Pydantic AI, Dapr, multi-agent systems, autonomous remediation*

**v20 — Claude Tool Use + Agent Memory: AOIS Sees and Remembers**
- Give AOIS tools: `get_pod_logs`, `describe_node`, `list_events`, `get_metrics`
- AOIS goes from read-only to investigative
- Ask: "Why is the auth service slow?" — AOIS pulls its own evidence
- Mem0: persistent memory layer — AOIS remembers past incidents, recurring failures, resolved root causes
- Without memory: every investigation starts cold. With memory: AOIS says "this auth service had the same spike last Tuesday — here's what fixed it"
- Short-term memory (current session) + long-term memory (across sessions) — understand both layers

**v21 — MCP + A2A: AOIS as an Interoperable Platform**
- Build AOIS as an MCP server — any MCP client (Claude.ai, Cursor) can use AOIS
- Implement A2A Protocol alongside: AOIS can now communicate with agents from other frameworks
- MCP = how tools connect to AI. A2A = how AI agents talk to each other across vendors
- This is the emerging multi-vendor agent standard — understand both sides

**v22 — Temporal: Durable Agent Execution**
- Wrap AOIS investigation workflows in Temporal
- A 10-minute incident investigation survives pod restarts, crashes, deployments
- Workflow history, replay, retry, timeouts — production-grade agent reliability
- The difference between a demo agent and one you actually trust in production

**v23 — LangGraph: Autonomous SRE Loop**
- Stateful agent graph: Detect → Investigate → Hypothesize → Verify → Remediate → Report
- Human-in-the-loop: approval gate before any write actions
- Full audit trail persisted to Postgres
- Dapr: agent nodes communicate via Dapr pub/sub — portable messaging across cloud providers
- Handles multi-step incidents: one root cause, five downstream effects

**v24 — Multi-Agent Frameworks: AutoGen + CrewAI**
- **CrewAI pattern**: Crew of Detector, Root Cause Analyst, Remediation, Report Writer agents — role-based, sequential collaboration
- **AutoGen pattern**: Conversation-based — agents message each other, challenge responses, iterate until consensus — different mental model, same goal
- Pydantic AI: wire up one of the agents with full type safety — structured outputs + dependency injection, actually testable
- Compare all three on the same incident: same problem, different architectures, observe what breaks at scale
- The insight: frameworks consolidate, patterns persist — you are learning the pattern, not just the library
- Google ADK: add a Vertex-hosted agent that receives the AOIS incident report via A2A — cross-vendor agent handoff in practice

**v25 — E2B: Safe Code Execution**
- AOIS writes and runs remediation scripts in a sandboxed environment
- Test the fix before applying it to production
- AOIS generates kubectl patch → runs it in E2B sandbox → validates → proposes to human

---

### PHASE 8 — Full Stack Dashboard
*You will know: React, Vercel AI SDK, WebSockets, nginx, auth, real-time UI*

**v26 — React Dashboard**
- Real-time feed of logs + AOIS analysis via WebSocket
- Vercel AI SDK: streaming AI responses to the UI — the modern standard for AI web apps
- Severity heatmap, incident timeline, agent action log
- Approve/reject remediation proposals with one click
- Served via nginx, bundled into the Helm chart

**v27 — Auth & Multi-tenancy**
- JWT + refresh tokens (FastAPI + python-jose)
- RBAC: viewer, analyst, operator, admin
- OpenFGA: fine-grained authorization — when agents act on behalf of users, simple roles break
- SPIFFE/SPIRE for service-to-service identity
- Supabase: implement as an alternative backend — see the pattern of full-stack managed platforms

---

### PHASE 9 — Production CI/CD & Platform Engineering
*You will know: GitHub Actions, Dagger, image signing, zero-downtime deploys, model rollouts, IDP*

**v28 — GitHub Actions + Dagger: Full Pipeline**
- GitHub Actions: PR lint, test, Trivy scan, Cosign sign → merge → build → push GHCR → ArgoCD sync
- Dagger: wrap the pipeline in real code — same pipeline runs locally and in CI identically
- Deploy to both Hetzner k3s AND AWS EKS from same pipeline
- OpenFeature: safe model rollouts — ship new Claude version to 5% of traffic, measure, promote

**v29 — Weights & Biases: ML Operations**
- Track every prompt version as an experiment
- A/B test: Claude standard vs extended thinking vs fine-tuned model
- Log: latency, cost, accuracy score, user feedback
- How AI products improve systematically, not by guessing

**v30 — Internal Developer Platform (IDP)**
- Backstage or Port: self-service portal
- "Spin up new AOIS tenant" → Crossplane provisions infra → ArgoCD deploys
- Pulumi: provision complex AOIS infrastructure programmatically — logic Terraform can't express
- Semantic Kernel: integrate AOIS as an enterprise AI capability for .NET/Azure environments
- AOIS in the service catalog with docs, runbooks, SLOs, owners

---

### PHASE 10 — The Pinnacle
*Multimodal AI, edge inference, AI safety, computer use, governance*

**v31 — Multimodal AOIS**
- Claude Vision: analyze screenshots of Grafana dashboards, architecture diagrams
- AOIS can now say: "I can see from this dashboard that..."
- Upload a k8s topology diagram → AOIS identifies blast radius

**v32 — Edge AI with Ollama**
- Run AOIS locally on a Hetzner edge node, no internet required
- Air-gapped analysis for sensitive environments
- Synchronize findings to central cluster when connectivity returns

**v33 — Evals, Red-teaming & AI Safety**
- Systematic evaluation framework for AOIS output quality
- PyRIT + Garak at scale: automated adversarial testing in CI — every model change gets red-teamed
- Try to make AOIS give wrong severity, hallucinate solutions, leak data
- Constitutional AI principles: what should AOIS never do autonomously?
- AI safety applied to a real product you built

**v34 — Computer Use + AI Governance**
- Claude Computer Use: AOIS interacts with UIs — opens Grafana, files tickets, navigates dashboards
- Playwright + AI: browser automation driven by natural language
- EU AI Act compliance: risk classification, audit trails, model cards, human oversight gates
- This is what gets AI into regulated industries — governance is the enterprise gate

---

## Current State

### Preserved
- OpenAI API key in `.env` — used when needed (v2 LiteLLM routing, v1 fallback, v15 comparison)
- `.gitignore` committed — `.env` is protected

### Auto-Save Setup (Active)
- PostToolUse hook: commits after every file write/edit
- Stop hook: commits at session end
- Both in `~/.claude/settings.json`

### Current Position
- **v12 complete. Phase 0 (v0.1–v0.7), Phase 1 (v1–v3), Phase 2 (v4–v5), Phase 3 v6–v9, Phase 4 v10–v12 done. Next: v13 — NVIDIA NIM.**
- v10 and v11 are infrastructure-complete but have one pending step each (Bedrock daily quota — run the curl/python tests when quota resets).

### What's been built (v1–v12)
- **v1**: FastAPI + Claude (prompt caching) + OpenAI fallback, structured Pydantic output (summary, severity P1–P4, suggested_action, confidence)
- **v2**: LiteLLM gateway — 4 routing tiers (Claude premium → GPT-4o-mini → Groq fast → Ollama local), cost tracking per request
- **v3**: Instructor for guaranteed validated output + Langfuse tracing (tokens, cost, latency per call)
- **v4**: Multi-stage Dockerfile (non-root, minimal image), Docker Compose (AOIS + Redis + Postgres), Trivy scan
- **v5**: Security hardening — rate limiting (slowapi), input sanitization (5KB limit, injection pattern stripping), hardened system prompt, output blocklist (destructive action detection), payload size middleware
- **v6**: k3s on Hetzner, GHCR image push, k8s manifests (Namespace/Secret/Deployment/Service/Ingress), cert-manager + Let's Encrypt + nip.io — AOIS live at https://aois.46.225.235.51.nip.io
- **v7**: Helm chart — `charts/aois/` with templates, values.yaml (defaults), values.prod.yaml (2 replicas, higher resources), `helm template` renders clean output
- **v8**: ArgoCD GitOps — `argocd/application.yaml` points at repo + Helm chart, auto-sync with prune + selfHeal, full GitOps deploy cycle (git push = deploy)
- **v9**: KEDA installed on cluster, ScaledObject in Helm chart (CPU trigger, 1–5 replicas, 60% threshold), ArgoCD managing it — KEDA creates and owns the HPA, scales AOIS automatically under load
- **v10**: Amazon Bedrock enterprise tier added (LiteLLM `bedrock/` prefix + inference profile IDs), IAM policy AOISBedrockPolicy, latency benchmark script `test_bedrock.py`. *Pending: run benchmark + Bedrock Agents section once daily quota resets.*
- **v11**: Lambda handler `lambda/aois-analyzer/handler.py`, packaged and deployed, API Gateway live at `l9ryxlxtpe.execute-api.us-east-1.amazonaws.com/prod/analyze`, cost comparison model `cost_comparison.py`. *Pending: live Bedrock response test once quota resets.*
- **v12**: EKS cluster provisioned with `eksctl`, IRSA service account for Bedrock access (zero static credentials), AOIS image pushed to ECR, AOIS deployed to EKS via Helm (`values.eks.yaml`), Karpenter installed and validated — provisioned a new node in 43 seconds under load. Cluster torn down to stop charges.
- **v13**: NVIDIA NIM tier added (`nvidia_nim/meta/llama-3.1-8b-instruct`), severity-based auto-routing (`SEVERITY_TIER_MAP`: P1/P2→Claude, P3/P4→NIM), `auto_route` flag on `LogInput`, benchmark script `test_nim.py`. *Pending: add `NVIDIA_NIM_API_KEY` to .env and run `python3 test_nim.py`.*

### Curriculum notes structure (mastery-level)
Each phase has three layers:
- `00-introduction.md` — opens first in IDE, sets the frame for the phase
- `vN/notes.md` — deep runbook notes per version, each ending with a Mastery Checkpoint
- `looking-forward.md` — closes the phase, bridges to the next

### Notes standard
See **Content Quality Standard** section above — it is the complete, enforced standard for all versions. Do not repeat or summarize it here.

### v10 — INCOMPLETE (resume before v11 goes live)
Built and committed but blocked on AWS new-account daily token limit:
- `main.py` — enterprise tier added (Bedrock via LiteLLM)
- `test_bedrock.py` — benchmark script ready to run
- `AOISBedrockPolicy` — IAM policy created in AWS account 739275471358
- Bedrock access approved (use case form submitted)

**Remaining:**
1. Run `python test_bedrock.py` — latency comparison (unblocks when daily limit lifts, ~24–48h after account creation)
2. Build Bedrock Agent — Lambda + action group + invoke test (Steps 5a–5c in notes)

**To resume:** run `python test_bedrock.py` first. If it succeeds, complete the Bedrock Agents section, then mark v10 done and proceed to v11 live deploy.

### v11 — INCOMPLETE (Bedrock daily quota blocking live LLM response)
Built and deployed. Infrastructure fully working end-to-end:
- `lambda/aois-analyzer/handler.py` — Lambda handler written
- `lambda/aois-lambda.zip` — packaged and deployed to AWS
- `AOISLambdaRole` — IAM role created, Bedrock + CloudWatch permissions
- API Gateway endpoint live: https://l9ryxlxtpe.execute-api.us-east-1.amazonaws.com/prod/analyze
- `cost_comparison.py` — Lambda vs Hetzner cost model (Lambda wins below ~5k calls/day)

**Remaining:** Bedrock daily quota blocking. When quota resets, run:
```bash
curl -X POST https://l9ryxlxtpe.execute-api.us-east-1.amazonaws.com/prod/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "pod OOMKilled exit code 137", "tier": "enterprise"}' | jq .
```
Then measure cold vs warm start, check CloudWatch logs, complete mastery checkpoint.

### What v14 builds next
- Deploy vLLM on Modal (serverless GPU) — serve any HuggingFace model
- AOIS routes to vLLM via LiteLLM's OpenAI-compatible API
- Understand throughput, batching, KV cache — the production inference engineering layer

### Current root-level state
- `/main.py` — v5 implementation (active, served from k3s)
- `/Dockerfile` — v4 multi-stage build
- `/docker-compose.yml` — AOIS + Redis + Postgres
- `/requirements.txt` — consolidated dependencies
- `/test.py` — tier routing + cost comparison test suite
- `/k8s/` — Kubernetes manifests (namespace, secret, deployment, service, ingress, clusterissuer)
- `/charts/aois/` — Helm chart (Chart.yaml, values.yaml, values.prod.yaml, values.eks.yaml, templates/)
- `/argocd/application.yaml` — ArgoCD Application resource (auto-sync, prune, selfHeal)
- `/curriculum/` — mastery-level notes (Phase 0–3, all versions)
- `/README.md` — full table of contents with progress tracking

### Hetzner cluster
- Server: 46.225.235.51 (root access, k3s running)
- Live URL: https://aois.46.225.235.51.nip.io
- Image: ghcr.io/kolinzking/aois:v6 (v9 has no app code changes — same image)
- ArgoCD: installed, managing AOIS via GitOps (git push = deploy)
- KEDA: installed, ScaledObject active, HPA `keda-hpa-aois` managed automatically

### k8s/secret.yaml note
Real API keys were scrubbed from git history (2026-04-19) before first push to GitHub — keys were never exposed. `k8s/secret.yaml` now contains placeholders. The live cluster Secret was applied manually in v6 and is intact. To re-apply: temporarily put real keys in, `kubectl apply -f k8s/secret.yaml`, then revert. Better path: Vault (covered in v5).

---

## Session Rules
1. Every session builds something real
2. Every session ends with a git commit
3. CLAUDE.md updated at session end: what was done, what is next
4. Explanations happen during building
5. When a tool is introduced, we use it on AOIS — never a toy example
6. Any decision or preference agreed on is saved to memory immediately
7. Tools are included based on where AI is heading, not where employers currently are
