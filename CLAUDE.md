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

## Technology Universe + Build Roadmap
Full tool tables (AI/LLM, infra, observability, data, security, frontend, Linux) and per-version roadmap descriptions (v0.1–v34.5) are in `curriculum/CLAUDE.md` — loaded automatically when working in that directory.

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
- v14 COMPLETE (2026-04-26). Notes + hands-on done: SGLang on Vast.ai 2x RTX 3090, Qwen3-8B served, RadixAttention benchmark 3.3x speedup (cold 1.10s → warm 0.34s), AOIS JSON analysis validated. v15 complete.
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
- **v14**: COMPLETE (2026-04-26). SGLang 0.5.10 on Vast.ai 2x RTX 3090 (48GB VRAM), Qwen3-8B served via tensor parallelism. RadixAttention benchmark: 3.3x speedup on 400-token shared prefix (1.10s cold → 0.34s warm avg). AOIS incident analysis via OpenAI-compatible API: valid JSON in 1.29s. LiteLLM wiring pattern validated. Dynamo architecture covered in notes.

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

### v14 — COMPLETE (2026-04-26)

SGLang 0.5.10 on Vast.ai 2x RTX 3090 (48GB VRAM), Qwen3-8B served via tensor parallelism. RadixAttention benchmark: 3.3x speedup on 400-token shared prefix (1.10s cold → 0.34s warm avg). AOIS incident analysis via OpenAI-compatible API: valid JSON in 1.29s. LiteLLM wiring pattern validated. Dynamo architecture covered in notes.

**History note:** Modal vLLM attempt failed — $7.71 burned on cold starts + dependency hell. Lesson: Modal = one-shot GPU jobs; Vast.ai = persistent inference servers. `vllm_modal/serve.py` stays in repo as reference.

**Vast.ai GPU pricing (reference for future GPU work):**
- RTX 3090 (24GB VRAM) from $0.13/hr — same VRAM as Modal A10G, 15× cheaper
- RTX 4090 (24GB VRAM, faster Ada) from $0.29/hr — ~7× cheaper than Modal A10G
- No cold starts — GPU always warm while rented

**What Dynamo adds (single-GPU demo in notes; full benefit at 4+ GPU workers):**
- Disaggregated prefill/decode routing across multi-GPU fleet
- KV cache-aware routing — routes turn 2 to the worker holding turn 1's KV state
- NIXL KV migration between nodes (requires NVLink — not on single Vast.ai node)
- Single-node demo shows the router architecture; full benefit at 4+ GPU workers

### Curriculum Additions (April 2026 Audit) — ALL COMPLETE

**1. Per-incident cost attribution — ✅ COMPLETE (Phase 7 / v20)**
`incident_id` threading through every LLM call implemented in `agent/investigator.py`. Goal metric achieved: per-investigation cost tracked across all tool calls.

**2. Agent capability boundary + circuit breaker + kill switch — ✅ COMPLETE (Phase 7 gate)**
OPA Rego policy, Redis circuit breaker, kill switch implemented in `agent_gate/`. `@gated_tool` decorator enforces boundaries at invocation layer before v20 tools run.

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
- **v32**: Edge AOIS on Ollama — VALIDATED ON HETZNER 2026-04-26. llama3.2:3b (2.0GB Q4_K_M) running CPU-only. Inference: 3–10s. edge_aois.py: analyze_local + analyze_local_with_retry (3-attempt escalating JSON pressure) + queue + sync. Offline queue confirmed: 3 incidents written, JSONL format, atomic append. Model hot after first call. JSON compliance ~85% with format=json — `edge/edge_aois.py`
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
