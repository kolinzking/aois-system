# Start Here

This is the single document you read before anything else. It tells you how this curriculum works, how to use the notes, and what you are actually trying to achieve. Read it once. It will save you hours.

---

## What this curriculum is

A step-by-step build of AOIS — AI Operations Intelligence System — from a blank terminal to a live production system with autonomous agents, full observability, Kubernetes on AWS, and a real-time dashboard.

Every version builds on the previous. Every concept is taught through building something real. By the end you will have operated every tool in the modern AI engineering stack: not read about them, not watched a video about them — built with them, debugged them, deployed them.

This is not a tutorial series. It is an engineering progression. The difference: tutorials show you what works. This curriculum shows you what works, what fails, why it fails, and how to fix it. That is what builds the judgement that makes you dangerous.

---

## How to use the notes

**The rule: do not read ahead of where you have built.**

Each version's notes are structured as:
1. What this builds and why
2. Prerequisites check (run these commands — if any fail, the notes tell you what to do)
3. Concepts explained as you build them, not before
4. The build itself — step by step, with expected output at every step
5. Testing what you built
6. Troubleshooting (for when it does not match expected)
7. Mastery Checkpoint — do every item before moving on
8. Connection to later phases

**The right process:**
- Open the notes
- Run the prerequisite check — fix anything that fails before reading further
- Read a section, then immediately run the commands in it
- Do not batch-read and batch-run — read one section, run it, see the output, understand it, then move on
- When you hit the Mastery Checkpoint, stop. Do every item. Do not skip any. This is where learning becomes understanding.
- Only move to the next version after completing the checkpoint

**The wrong process:**
- Reading the whole notes file before touching the terminal
- Running commands without reading the explanation above them
- Skipping the Mastery Checkpoint because "you understood it while reading"
- Moving to the next version because you read this one

Reading is not learning. Building is learning. The notes are the map. The terminal is the territory.

---

## What "complete" means for each version

A version is complete when:
1. The build ran with no errors and matched expected output
2. Every test command returned the expected response
3. Every Mastery Checkpoint item was completed and understood
4. You can explain to someone else what you built and why, without looking at the notes

If you can pass point 4, you are ready for the next version. If you cannot, re-read the parts that feel uncertain and re-run the commands. The notes will not go stale. Your understanding is the only thing that matters.

---

## How long each phase takes (honest estimates)

These are focused work hours — terminal open, no distractions, actively building.

| Phase | Versions | Focused Hours | What you walk away with |
|-------|----------|---------------|------------------------|
| Phase 0 | v0.1–v0.7 | 20–30 hours | Linux, bash, git, HTTP, Python, FastAPI, raw LLM call |
| Phase 1 | v1–v3 | 12–18 hours | Working AI API with routing, validation, observability |
| Phase 2 | v4–v5 | 10–15 hours | Containerized, hardened, production-safe service |
| Phase 3 | v6–v9 | 15–25 hours | Live cluster on Hetzner, Helm, GitOps, autoscaling |
| Phase 4 | v10–v12 | 15–20 hours | AWS: Bedrock, Lambda, EKS |
| Phase 5 | v13–v15 | 15–20 hours | GPU inference, vLLM, fine-tuning |
| Phase 6 | v16–v19 | 20–25 hours | Full observability stack, Kafka, eBPF, chaos engineering |
| Phase 7 | v20–v25 | 25–35 hours | Autonomous agents, MCP, Temporal, LangGraph, multi-agent |
| Phase 8 | v26–v27 | 12–18 hours | React dashboard, real-time UI, auth |
| Phase 9 | v28–v30 | 15–20 hours | CI/CD pipeline, Dagger, IDP |
| Phase 10 | v31–v34 | 15–20 hours | Multimodal, evals, safety, computer use |

**Total to Phase 4 completion (job-ready AI SRE): ~72–108 focused hours.**
At 2 hours/day: 5–7 weeks.
At 3 hours/day: 4–5 weeks.

Phase 4 completion is the milestone that changes everything. At that point you have: k8s, Claude agents, AWS Bedrock, full observability, CI/CD, and a live system. That alone puts you ahead of 90% of engineers applying for AI/SRE roles.

---

## The phase map

```
Phase 0 ─── Foundation
│           Linux · Bash · Git · HTTP · Python · FastAPI · Raw LLMs
│
Phase 1 ─── Intelligence
│           Claude API · LiteLLM routing · Instructor · Langfuse
│
Phase 2 ─── Production Safety
│           Docker · OWASP API/LLM · Prompt injection defense
│
Phase 3 ─── Real Infrastructure
│           k3s/Hetzner · Helm · ArgoCD GitOps · KEDA autoscaling
│
Phase 4 ─── Enterprise Cloud
│           AWS Bedrock · Lambda · EKS · Karpenter · IRSA
│
Phase 5 ─── GPU & Inference
│           NVIDIA NIM · vLLM · Fine-tuning · Inference hardware
│
Phase 6 ─── Full Observability
│           OTel · Prometheus · Grafana · Kafka · eBPF · Chaos
│
Phase 7 ─── Autonomous Agents  ← THE PINNACLE BEGINS HERE
│           Tool use · MCP · A2A · Temporal · LangGraph · AutoGen
│           Pydantic AI · Mem0 · CrewAI · E2B
│
Phase 8 ─── Full Stack
│           React · Vercel AI SDK · WebSockets · Auth · OpenFGA
│
Phase 9 ─── Production CI/CD
│           GitHub Actions · Dagger · Image signing · Model rollouts
│
Phase 10 ── The Pinnacle
            Multimodal · Edge AI · Evals · Red-teaming · Governance
```

Each phase is a complete capability unlock. You can stop at any phase and be productive. Every phase builds on all the previous ones — nothing is throwaway.

---

## The mindset that separates mastery from familiarity

**Run every command.** Not most. Not the ones you are unsure about. Every single one. Even the ones that seem obvious. The expected output is there for a reason — seeing your output match it is confirmation that your environment, your understanding, and the command are all aligned.

**When something does not match expected output: stop.** Do not skip and continue. The troubleshooting section exists for this. Unexplained errors accumulate and compound. One unresolved error makes the next section harder. Fix each one before proceeding.

**The Mastery Checkpoint is not optional.** It is the difference between having read the notes and having learned the material. Every item in the checkpoint was chosen because it targets a specific understanding gap that bites engineers later. Skip one, pay for it in a future version.

**Struggle is productive.** When a command does not work and you have to think about why, that is where the deepest learning happens. The troubleshooting section is a scaffold — use it if you are stuck, but try to diagnose the problem yourself first. The ability to debug unfamiliar errors is the most valuable skill this curriculum builds.

**Compare your output to expected output analytically.** If your output is different, do not just re-run the command. Read both outputs. Identify exactly where they diverge. That divergence is the thing to investigate. This is how engineers think.

---

## Common mistakes in self-paced technical learning

**Reading ahead** — If you read v3 notes before completing v1, you will "understand" v3 conceptually but not be able to build it. Understanding and building are different. Build in order.

**Treating errors as blockers instead of teachers** — Every error message contains information. Read it. The error is not an obstacle; it is the system telling you exactly what is wrong.

**Skipping the "why" sections** — The command works, so you move on. Six versions later, you cannot remember why you made a certain architectural choice. The "why" sections are what build judgement. Read them even when you are tempted to skip to the command.

**Counting hours instead of checkpoints** — "I spent 3 hours on v0.1" is not progress. "I completed the Mastery Checkpoint" is progress. Measure by checkpoints completed, not time spent.

**Not committing after each version** — The git history is your progress log and your CV. Every completed version gets a commit with a meaningful message. When a recruiter looks at this repository in six months, they should see 34 versions of progressive complexity. That history is more credible than any resume line.

---

## How each version's notes are structured

At the top of every version's notes:

```
# vX — Title
⏱ Estimated time: X–Y hours
```

Then:
- **What this builds** — the goal, in one paragraph
- **Prerequisites** — commands to verify the environment is ready
- **Learning goals** — what you will understand by the end
- **The build** — section by section, concepts + commands interleaved
- **Stop points** — mid-notes exercises marked `▶ STOP — do this now`
- **Testing** — verify what you built works correctly
- **Troubleshooting** — for when things do not match expected
- **Mastery Checkpoint** — do all of these before moving on
- **Connection to later phases** — where each concept reappears

---

## The first thing you do right now

Open `phase0/00-introduction.md`.

Read it. Then open `phase0/v0.1/notes.md`. Run the prerequisite check. Start building.

Do not skip Phase 0 because you "already know Linux" or "already know Python." The specific patterns, the specific tools, and the specific mental models in Phase 0 are exactly what Phase 1 builds on. Gaps in Phase 0 become confusion in Phase 1 and bugs in Phase 2.

The curriculum starts with `uname -a`. Run it.
