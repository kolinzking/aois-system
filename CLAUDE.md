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

**10. The 4-Layer Understanding Rule — every tool, every version**
Mastery is not just doing. It is being able to explain the doing. For every tool that enters AOIS, the learner must be able to answer at four levels. If any level is missing, the tool has not been learned — it has been used.

| Layer | Question | Example (Redis) |
|-------|----------|-----------------|
| **Plain English** | What problem does this solve? | "Avoids recomputing things by storing results temporarily." |
| **System Role** | Where does it sit in AOIS? | "Between the API and LLM/database — reduces repeated work and latency." |
| **Technical** | What is it, precisely? | "In-memory key-value store used for caching and fast data access." |
| **Remove it** | What breaks, and how fast? | "Remove Redis → every request hits the LLM directly → latency spikes, cost multiplies." |

Every tool introduced in a version gets a 4-layer entry in a `## 4-Layer Tool Understanding` section at the end of its notes. The Mastery Checkpoint must include at least one prompt asking the learner to explain a tool at each level.

**Explaining at three audience levels** is also a required skill — the same system described to:
- A non-technical person: plain language, outcome-focused
- A junior engineer: what it does, where it sits, what replaces it if removed
- A senior engineer: tradeoffs, failure modes, why this over alternatives

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
10. `## 4-Layer Tool Understanding` — one entry per new tool introduced, all four layers filled in

### Minimum length
- 600+ lines for focused versions
- 800+ lines for complex versions (Kafka, LangGraph, multi-agent, observability stacks, GPU inference)
- Length is a consequence of depth, not padding. Every line earns its place.

### Audit command (run before declaring any version complete)
```bash
grep -c 'Estimated time\|## Prerequisites\|Learning [Gg]oals\|STOP — do this now\|Common Mistakes\|## Troubleshooting\|Connection to\|Mastery Checkpoint\|4-Layer Tool Understanding' curriculum/phaseN/vN/notes.md
```
Expected: 9+ matches. Line count must meet the minimum above. If either fails, the notes are not done.

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

**v0.8 — SQL & PL/pgSQL: The Database Layer Every SRE Lives In**
- SQL fundamentals: SELECT, WHERE, JOINs, GROUP BY, aggregations, CTEs
- EXPLAIN ANALYZE: read query plans, identify Seq Scans, know when to index
- Transactions: BEGIN/COMMIT/ROLLBACK/SAVEPOINT — how database consistency works
- PL/pgSQL functions and procedures — same concepts as Oracle PL/SQL, different syntax
- Oracle PL/SQL ↔ PL/pgSQL full translation cheat sheet (NVL→COALESCE, ROWNUM→LIMIT, DBMS_OUTPUT→RAISE NOTICE, etc.)
- SRE operational queries: pg_stat_activity, pg_locks, kill blocking queries, vacuum stats
- Python + psycopg2: parameterised queries, cursor patterns — the same code AOIS uses internally
- Build: spin up local Postgres, create the AOIS incidents + remediations schema, query it like a production incident

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

**v2.5 — AI Gateway: Production LLM Proxy**
LiteLLM routes models. This version builds the control plane around that routing.
- Per-user and per-team cost budgets enforced at the gateway — agent workflows that exceed budget are halted, not just logged
- PII redaction before any prompt leaves your network — regex + ML-based detection, configurable per-route
- Semantic caching: identical or near-identical prompts return cached responses — cost reduction without touching model code
- Full request/response audit log: every prompt, every response, every token count, every model — immutable, queryable
- Rate limiting per API key, per team, per model tier
- This is the layer enterprises build before they let any team call an LLM directly

**v3 — Instructor + DSPy: Reliable Intelligence**
Make the outputs trustworthy and systematically optimal.
- Instructor for guaranteed Pydantic-validated LLM responses
- DSPy: dedicated full section — treat prompts like code, write the eval first, let DSPy optimize the prompt automatically (eval-driven prompt development, not artisanal hand-crafting)
- Prompt versioning: prompts checked into git, diffs reviewed like code, rollback like a deployment
- Reasoning models: when to use Claude extended thinking vs. standard — measure cost/latency tradeoff on real incidents
- Eval suite: score AOIS against a ground truth set of 20 real incidents
- Langfuse: every LLM call traced, costed, scored

**v3.5 — RAG: Retrieval-Augmented Generation**
The pattern behind half of all production AI applications — AOIS needs it for incident history retrieval.
- pgvector vs Qdrant: build the same RAG pipeline on both, benchmark query latency and recall at 10k/100k documents
- Chunking strategies: fixed-size vs semantic vs document-structure-aware — measure the difference in retrieval quality
- Hybrid search: vector similarity + BM25 keyword search combined — the production standard, not pure vector
- Reranking: cross-encoder reranker scores candidate chunks, top-k sent to the LLM — precision over recall
- RAGAS evaluation: faithfulness, answer relevance, context precision — RAG quality is measurable, not vibes
- AOIS application: retrieve similar past incidents during investigation — "seen this before, here's what fixed it"

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
- OWASP Agentic AI Top 10 (2025) applied to the agent design — excessive agency, unsafe tool invocation, uncontrolled memory manipulation, identity spoofing across agent boundaries
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

**v13.5 — NVIDIA Triton Inference Server**
- Triton is the production inference server NIM is built on — understand the layer underneath
- Backends: TensorRT (NVIDIA optimised), ONNX Runtime, PyTorch, Python — one server, any framework
- Dynamic batching: Triton groups concurrent requests and processes them together — how throughput scales
- Model ensemble: chain a preprocessing model → LLM → postprocessor as a single inference pipeline
- Perf Analyzer: measure throughput and latency under load before production
- Compare: NIM (abstracted, API-ready) vs Triton (full control, requires configuration) — when to use each
- Deploy the fine-tuned TinyLlama from v15 on Triton instead of vLLM — same model, different server

**v14 — vLLM Inference Server**
- Deploy vLLM on Modal (serverless GPU, no hardware needed)
- Serve an open-source model via OpenAI-compatible API
- AOIS can now use: Claude, OpenAI, Bedrock, Groq, Together AI, Fireworks, NIM, Triton, vLLM — all via LiteLLM
- KV cache: what it is, why it matters, how vLLM's PagedAttention manages it
- Quantization: INT8 and INT4 — how much quality you lose for how much speed you gain
- Speculative decoding: draft model proposes tokens, main model verifies — latency trick for large models
- Cost tracking: GPU-hours vs API calls — build the break-even model for self-hosted vs managed
- Inference hardware comparison: NVIDIA GPU vs Groq LPU vs Cerebras WSE — why they exist, what each wins at

**v15 — Fine-tuning with SRE Data**
- Curate a dataset: 500 real log samples + ideal AOIS responses
- Synthetic data pipeline: distilabel for programmatic dataset generation, data quality scoring, deduplication — dataset versioned in git alongside model code
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

**v16.5 — ClickHouse: Analytics at Scale**
Prometheus has limits. When AOIS is processing thousands of incidents per hour, you need a columnar database.
- ClickHouse deployed on k8s — query 100 million AOIS incident rows in under a second
- AOIS writes every incident analysis to ClickHouse: timestamp, severity, tier, model, latency, cost, tokens, resolution
- Replace Prometheus/Grafana for analytics queries: "which incident type costs most per month?" — PromQL cannot answer this
- Materialized views: pre-aggregate cost-by-tier, accuracy-by-severity, latency percentiles — live dashboards without scan overhead
- Retention tiers: hot data in memory, warm on SSD, cold on object storage — the production ClickHouse pattern
- Compare: Prometheus for real-time alerting (keep it), ClickHouse for analytics and audit (new layer) — they coexist

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
- **Memory poisoning protection**: agent memory is an attack surface — a crafted log event can cause AOIS to store a false memory ("deleting the namespace fixed this last time") that poisons every future investigation. Detect and reject poisoned writes at the Mem0 layer before they persist.

**v21 — MCP + A2A: AOIS as an Interoperable Platform**
- Build AOIS as an MCP server — any MCP client (Claude.ai, Cursor) can use AOIS
- Implement A2A Protocol alongside: AOIS can now communicate with agents from other frameworks
- MCP = how tools connect to AI. A2A = how AI agents talk to each other across vendors
- This is the emerging multi-vendor agent standard — understand both sides

**v21.5 — MCP Security + Production Deployment**
MCP without security is a new attack surface. This version hardens the MCP server built in v21.
- OAuth 2.0 authorization on every MCP tool — AOIS tools require explicit user consent before execution
- Tool sandboxing: each MCP tool runs in an isolated context — one compromised tool cannot access another's state
- Input validation at the MCP layer: malformed tool arguments rejected before reaching AOIS logic
- Multi-server orchestration: AOIS MCP server communicates with a second MCP server (Kubernetes tools) — agent delegates to specialist
- MCP observability: every tool call traced via OTel — who called what, when, with what arguments, what was returned
- Rate limiting per MCP client — Claude.ai, Cursor, and custom agents each get independent quotas
- This is the difference between an MCP demo and an MCP server you'd expose to real users

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

**v23.5 — Agent Evaluation (CRITICAL)**
- Unit evals: given a known incident input, assert the correct severity, tool calls, and remediation step — agents must be testable like functions
- LLM-as-judge: use Claude to score agent outputs against a rubric (correctness, safety, conciseness) — automated quality gate before any agent update ships
- Eval-driven development: write the eval before changing the agent — same discipline as TDD, applied to agents
- Production scoring: track accuracy, false positive rate, escalation rate, and mean time to correct remediation over real traffic
- Regression testing: every change to the agent graph runs the full eval suite — no silent degradation
- Dataset curation: build a golden set of 50 labeled incidents with ground-truth actions — versioned in git, the benchmark everything is measured against
- **Agent SLOs (enforced, not aspirational)**: accuracy ≥ 90% on severity classification, hallucination rate ≤ 5% (suggested actions that are factually wrong), safety rate = 100% (no destructive action recommended without human approval). No agent ships without all three met.
- Without this version, agents go to production unscored. You cannot improve what you cannot measure, and you cannot trust what you haven't measured.

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

**v34.5 — AI SRE Capstone: Everything Tied Together**
The curriculum ends here. This version does not introduce new tools — it forces mastery of everything built.
- AI-specific SLOs as first-class engineering: model accuracy SLO, hallucination rate SLO, latency SLO, cost SLO — monitored, alerted on, owned by an on-call rotation
- Incident playbooks for AI-specific failures: model degradation (accuracy drops without error), embedding drift (RAG quality declines over time), prompt injection in production (attacker manipulates live traffic), cost runaway (agent loop burns budget in minutes)
- On-call runbook for AOIS itself: what breaks first under load, how to diagnose it, how to recover — written from the experience of having built and run the system
- Game day: simulate a full AI system failure — model API outage, Kafka lag spike, agent runaway, security alert flood — AOIS must detect, respond, and recover within SLO
- The portfolio artifact: a documented, live system with measurable SLOs, real incident history, a security posture, and a cost model — the evidence that you have done this, not just studied it
- **The mastery bar:** you can walk into any AI infrastructure conversation — engineering, product, security, finance — and answer every question from first principles, with evidence from a system you built and ran.

---

## Current State

### Preserved
- OpenAI API key in `.env` — used when needed (v2 LiteLLM routing, v1 fallback, v15 comparison)
- `.gitignore` committed — `.env` is protected

### Auto-Save Setup (Active)
- PostToolUse hook: commits after every file write/edit
- Stop hook: commits at session end
- Both in `~/.claude/settings.json`

### Retroactive Build Queue
✅ **All three retroactive versions COMPLETE.**

| Version | What | Notes status | Code status |
|---|---|---|---|
| `v2.5` | AI Gateway — cost budgets, PII redaction, semantic caching, audit log | ✅ written | ✅ built |
| `v3.5` | RAG — pgvector vs Qdrant, hybrid search, reranking, RAGAS eval | ✅ written | ✅ built |
| `v16.5` | ClickHouse — analytics at scale, materialized views, retention tiers | ✅ written | ✅ built |

---

### Current Position
- **ALL PHASES COMPLETE — v0.1 through v34.5 DONE.** Curriculum complete.
- v10/v11 blocked on AWS Bedrock daily quota (infrastructure built, live Bedrock call pending quota).
- v14 closed (Modal GPU cost). v15 complete.
- Phase 10 (v31–v34.5) complete: multimodal vision, edge AI (Ollama), red-teaming (PyRIT+Garak), computer use (Playwright+Claude), EU AI Act compliance, capstone game day runbook.

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
- **v13**: COMPLETE. NVIDIA NIM + Groq tiers working. NGC API key in .env. Groq (0.22s, $0.000001) beats NIM (1.07s) for P3/P4 volume. SEVERITY_TIER_MAP: P1/P2→Claude, P3/P4→Groq (fast). LiteLLM 1.83.x bug worked around: groq_client and _nim_openai bypass LiteLLM with direct OpenAI-compatible calls.
- **v14**: INCOMPLETE. vllm tier added to ROUTING_TIERS; _call_nim() handles structured output for NIM (tool_choice forced by name). Benchmark ran (vllm NIM fallback: 1,075ms avg, $0.000010/call vs Claude: 10,849ms, $0.016/call). **Blocker: vllm_modal/serve.py broken** — @modal.fastapi_endpoint can't handle vLLM async engine. Needs rewrite with @modal.asgi_app() pattern. VLLM_MODAL_URL commented out in .env. Currently using NIM Llama-3.1 as fallback when Modal URL absent.

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

### v14 — CLOSED (Modal GPU blocked; Groq serves as fast tier)
vLLM deployment attempted extensively. GPU cold starts consumed $7.71 of Modal credits across debugging sessions. Closing v14 without live Modal endpoint.

**What was built and learned:**
- `@modal.asgi_app()` subprocess/proxy pattern — correct architecture, committed
- vLLM dependency chain: 0.4.3 (NumPy/outlines), 0.6.6/0.7.3/0.8.4 (TokenizersBackend tokenizer bug)
- GPU inference cost model: A10G at $1.10/hr vs Claude at $0.016/call
- Real-world ML infra dependency hell — this is curriculum, not failure

**Why this is fine:** Groq already covers the fast/cheap tier: 0.22s latency, $0.000001/call. The vLLM tier adds self-hosted knowledge but not a new capability. The architecture is sound — the endpoint just isn't live.

**If resuming Modal later:** `modal deploy vllm_modal/serve.py` + `python3 test_vllm.py`. Budget at least $5 clean credits.

### Pending Curriculum Additions (April 2026 Audit)
Two gaps identified from external curriculum audit — not yet in any version, must be added at the right phase:

**1. Per-incident cost attribution — add at v20**
AOIS currently tracks cost per API call (v2 LiteLLM). Not enough for agentic workflows.
When AOIS gets tools in v20, a single incident investigation will span 10-15 LLM calls.
Need an `incident_id` threading through every call from detection to resolution.
Goal metric: "investigating this OOMKilled cost $0.04 across 12 LLM calls."
Without this, agents never get approved for production — cost spiral kills them.
**Trigger: add this as the first task when starting v20.**

**2. Agent capability boundary + circuit breaker + kill switch — add before v20, as Phase 7 gate**
v5 has an output blocklist (reactive — blocks a bad recommendation after the LLM returns it). That is not governance.
Before AOIS gets any tools (kubectl, metrics, logs), define what it is structurally prevented from doing regardless of LLM output — enforced at invocation layer, auditable.
Tools: OPA or Cedar as the policy engine.
**Circuit breaker**: if AOIS makes more than N tool calls in one investigation, or cost exceeds a threshold, or tool call sequence looks anomalous — halt the agent mid-execution before it does more. This is different from the output blocklist (which only fires at response time).
**Kill switch**: a hard stop that halts the agent entirely and requires human restart — for runaway agents, unexpected escalation, or any time the circuit breaker fires repeatedly.
**Trigger: build this as the opening section of Phase 7, before v20 hands AOIS any tools.**

**3. SPIFFE/SPIRE workload identity — ✅ COMPLETE (2026-04-24)**
Deployed SPIRE Server + Agent to live Hetzner k3s cluster.
Node attestor: k8s_psat (Projected Service Account Tokens) — correct for self-managed VPS.
Workload attestor: use_new_container_locator=true (k3s disables kubelet read-only port 10255;
new locator reads cgroups + queries k8s API instead).
SVID confirmed: spiffe://aois.local/ns/aois/sa/aois issued to pods in aois namespace.
v6 notes updated with Part 10 (SPIFFE/SPIRE) + 4-layer entry.
k8s/spire/ manifests committed and pushed.

---

### v15 — COMPLETE
- **Dataset**: 500 SRE log→analysis pairs generated via Claude Haiku, split 450 train / 50 eval
- **Fine-tune**: TinyLlama-1.1B LoRA (r=16, q+v proj), 63s on A10G, loss 2.25→0.23
- **Eval results**: Base: 2% JSON valid. Fine-tuned: 94% JSON valid, 44% severity match. Claude Haiku: 100% JSON valid, 80% severity match.
- **Verdict**: Fine-tuning bought 42pp severity improvement over base; Claude leads by 36pp — scale gap is real. P3/P4 volume → fine-tuned TinyLlama. P1/P2 → Claude.
- Adapter saved: `aois-lora-weights` Modal volume at `/models/tinyllama-sre-lora`

### v16 — COMPLETE
- OTel SDK + GenAI semantic convention spans on every LLM call (model, tier, severity, cost, duration)
- FastAPI auto-instrumentation + httpx instrumentation
- Prometheus counters/histograms at `/metrics/`: `aois_incidents_total`, `aois_llm_duration_ms`, `aois_llm_cost_usd_total`, `aois_llm_token_usage_total`
- Docker Compose: +OTel Collector, Prometheus, Grafana, Loki, Tempo (7-container stack)
- Grafana pre-provisioned: Prometheus + Loki + Tempo datasources, AOIS LLM dashboard
- Pipeline validated: request → Prometheus query confirms `aois_incidents_total` scraped

### v17 — COMPLETE
- Local: `apache/kafka:3.7.0` in Docker Compose (KRaft, dual-listener for host+container access)
- `kafka/producer.py` — load generator publishing SRE log events to `aois-logs` at configurable rate
- `kafka/consumer.py` — long-lived worker: read `aois-logs` → `analyze()` → publish to `aois-results`
- k8s: Strimzi operator + Kafka 4.1.0 cluster on Hetzner — `aois-logs` and `aois-results` topics
- KEDA ScaledObject switched from CPU trigger to Kafka consumer lag trigger (`lagThreshold=50`)
- Full pipeline validated: producer → Kafka → consumer → analysis → `aois-results`

### v18 — COMPLETE
- Falco installed on Hetzner cluster (modern eBPF driver, kernel 6.8 BTF, no kernel headers needed)
- Falco Sidekick configured → `aois-security` Kafka topic (minimumpriority=warning)
- 5 custom AOIS rules: shell in container, /etc writes, unexpected outbound, privilege escalation, package manager at runtime
- `aois-security` KafkaTopic created via Strimzi (3 partitions, 7-day retention)
- `kafka/consumer.py` updated: subscribes to both `aois-logs` + `aois-security`; detects Falco format by `rule`+`priority` fields; ERROR/CRITICAL → Claude, WARNING → Groq
- Pipeline validated end-to-end: `kubectl exec` → Falco fires → Sidekick publishes → `Kafka - Publish OK`
- Cilium: full fresh-cluster recipe documented in notes (not deployed live — CNI swap requires k3s rebuild)

### v19 — COMPLETE
- Chaos Mesh installed on k3s (containerd socket path: `/run/k3s/containerd/containerd.sock`)
- 5 chaos experiments: pod-kill, network-delay, Kafka-kill, packet-loss, CPU-stress
- 3 SLOs defined with Prometheus expressions (p99 latency <30s, heartbeat, error rate <5%)
- 60-minute game day runbook, docs/gameday-v19.md template

### Phase 7 — COMPLETE (session 2026-04-23 + continuation)
- **Phase 7 gate**: OPA Rego policy, Redis circuit breaker, kill switch — `agent_gate/`
- **v20**: Claude tool use + Mem0 memory + per-incident cost attribution — `agent/`
- **v21**: MCP server + A2A protocol — `mcp_server/`
- **v21.5**: MCP security — OAuth, sandboxing, OTel tracing per tool call
- **v22**: Temporal durable workflow — `temporal_workflows/`
- **v23**: LangGraph 6-node SRE loop — `langgraph_agent/`
- **v23.5**: Agent eval suite — 20-entry golden dataset, LLM-as-judge, CI gate — `evals/`
- **v24**: CrewAI crew, AutoGen group, Pydantic AI typed agent, Google ADK pattern — `multi_agent/`
- **v25**: E2B sandboxed kubectl validation — `sandbox/`

### Phase 8 — COMPLETE
- **v26**: React+Vite dashboard, WebSocket incident feed, severity heatmap, approve/reject UI — `dashboard/`
- **v27**: JWT auth (15m access + 7d refresh), RBAC 4-role hierarchy, OpenFGA namespace auth — `auth/`

### Phase 9 — COMPLETE
- **v28**: GitHub Actions CI (lint→test→evals→Trivy→Cosign→push→ArgoCD sync), Dagger pipeline, OpenFeature 5% canary — `dagger_pipeline.py`, `flags/`
- **v29**: W&B experiment tracking, per-incident Table logging, A/B eval framework — `evals/run_evals_wandb.py`
- **v30**: Backstage/Port IDP pattern, Crossplane XRD for self-service tenant provisioning, Pulumi conditional infra, Semantic Kernel plugin — `pulumi/`, `k8s/crossplane/`, `semantic_kernel_plugin.py`

### Phase 10 — COMPLETE
- **v31**: Claude Vision for Grafana screenshots + architecture diagrams, `/analyze/image` endpoint — `multimodal/vision.py`
- **v32**: Edge AOIS on Ollama, air-gapped operation, offline queue at `/var/aois/offline_queue.jsonl`, sync_to_central() — `edge/edge_aois.py`
- **v33**: PyRIT injection tests, Garak vulnerability scan, constitutional AI constraints, red-team CI pipeline — `redteam/`
- **v34**: Claude Computer Use + Playwright Grafana agent, EU AI Act compliance layer (RiskCategory, AuditEntry, model card) — `computer_use/`, `governance/`
- **v34.5**: Capstone — AI-specific SLO enforcement, 5 game day scenarios, 4 AI incident playbooks, on-call runbook, portfolio artifact description

### Current root-level state
- `/main.py` — v16 implementation (OTel instrumented, Prometheus metrics, GenAI spans)
- `/Dockerfile` — v4 multi-stage build
- `/docker-compose.yml` — v16: AOIS + Redis + Postgres + OTel Collector + Prometheus + Grafana + Loki + Tempo
- `/otel/` — OTel Collector config, Prometheus scrape config, Loki config, Tempo config, Grafana provisioning
- `/requirements.txt` — consolidated dependencies (OTel SDK added)
- `/agent/` — tool implementations (k8s.py, rag_tool.py, memory.py, investigator.py, definitions.py)
- `/agent_gate/` — OPA policy, circuit breaker, kill switch, @gated_tool decorator
- `/langgraph_agent/` — LangGraph SRE graph (state, nodes, graph, dapr_events)
- `/temporal_workflows/` — Temporal investigation workflow + activities + worker
- `/mcp_server/` — MCP server + A2A protocol implementation
- `/multi_agent/` — CrewAI, AutoGen, Pydantic AI, compare.py
- `/sandbox/` — E2B executor + kubectl generator
- `/evals/` — golden_dataset.json (20 entries), run_evals.py, run_evals_wandb.py, CI workflow
- `/clickhouse/` — schema.sql, views.sql, writer.py
- `/gateway/` — PII redaction, budget tracking, gateway.py
- `/rag/` — pgvector store, hybrid search, reranker, aois_rag.py
- `/kafka/` — producer.py, consumer.py
- `/multimodal/` — vision.py (Claude Vision, Grafana/architecture analysis)
- `/edge/` — edge_aois.py (Ollama, offline queue, sync)
- `/redteam/` — run_pyrit.py, parse_garak.py, constitution.py
- `/computer_use/` — grafana_agent.py (Claude Computer Use + Playwright)
- `/governance/` — eu_ai_act.py (compliance layer, audit log, model card)
- `/dashboard/` — React+Vite frontend, WebSocket incident feed, auth
- `/auth/` — JWT handler, RBAC, OpenFGA client
- `/pulumi/` — Pulumi Python stack for conditional AOIS infra
- `/flags/` — OpenFeature flagd config for model canary rollouts
- `/k8s/` — Kubernetes manifests + Crossplane XRD
- `/charts/aois/` — Helm chart (Chart.yaml, values.yaml, values.prod.yaml, values.eks.yaml, templates/)
- `/argocd/application.yaml` — ArgoCD Application resource (auto-sync, prune, selfHeal)
- `/curriculum/` — mastery-level notes (Phase 0–10, v0.1–v34.5) — COMPLETE
- `/README.md` — full table of contents with progress tracking

### Hetzner cluster
- Server: 46.225.235.51 (root access, k3s running)
- **Hostname**: `ubuntu-16gb` (renamed from `aois` on 2026-04-24)
- **Upgraded 2026-04-23**: 8 vCPU / 16GB RAM / 150GB disk (was 4GB RAM — old OOM kills no longer possible)
- Live URL: https://aois.46.225.235.51.nip.io
- Image: ghcr.io/kolinzking/aois:v6 (v9 has no app code changes — same image)
- ArgoCD: installed, managing AOIS via GitOps (git push = deploy)
- KEDA: installed, ScaledObject active, HPA `keda-hpa-aois` managed automatically

### Resource management (applied 2026-04-23)
System-level controls to prevent OOM kills and disk exhaustion:
- **journald**: capped at 200MB (`/etc/systemd/journald.conf.d/size-limit.conf`), 2-week retention
- **Kafka JVM**: heap `-Xms256m -Xmx512m`, container limit 768Mi — captured in `k8s/kafka/kafka-cluster.yaml`
- **AOIS pod**: 512Mi request / 1Gi limit (prod via `values.prod.yaml`)
- **Docker cleanup**: weekly cron at `/etc/cron.weekly/docker-cleanup` — prunes stopped containers + old images
- **Memory alert**: `/usr/local/bin/memory-check.sh` runs every 5 min — logs to `/var/log/aois-alerts.log` when available < 2GB
- **SSH root access**: `ssh hetzner-root` uses `~/.ssh/hetzner_nopass` (configured in `~/.ssh/config`)

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
