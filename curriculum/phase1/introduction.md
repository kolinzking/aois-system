# Phase 1 — The Intelligence Core

## Introduction
Before any infrastructure, any containers, any Kubernetes — there has to be a brain. Phase 1 builds that brain.

The question this phase answers is the most fundamental one in the entire curriculum: can a piece of software look at a raw infrastructure log and reason about it the way a senior SRE would? Can it classify severity correctly, identify what happened, and suggest the right action — every time, reliably, in a structured format a machine can act on?

Everything that comes after — the containers, the clusters, the agents, the dashboards — only matters if the intelligence at the centre actually works. Phase 1 proves it works.

You will learn how to talk to LLMs programmatically, how to force structured output instead of free-form text, how to route between providers based on cost and capability, and how to make that output guaranteed valid so it never crashes your system. These are the skills that sit underneath every AI application in production today.

By the end of Phase 1 you have a working API. It is not deployed, not secured, not observable at scale — but it is correct. That correctness is what Phase 2 through Phase 10 build on.

## What was built
A log analysis API. Send any infrastructure log, get back structured incident data:
severity (P1–P4), summary, suggested action, confidence score.

## Versions
- **v1** — FastAPI + Claude (primary) + OpenAI (fallback). Direct SDK calls. Prompt caching active.
- **v2** — LiteLLM routing layer. Four tiers: premium, standard, fast, local. Cost tracked per call.
- **v3** — Instructor wraps LiteLLM. Output guaranteed valid via Pydantic. Langfuse traces every call.

## State at close
Single endpoint: `POST /analyze`. Runs locally on port 8000.
Routes across Claude, GPT-4o-mini, Groq, Ollama. Output always validated. Observable when Langfuse keys present.

## What Phase 2 picks up
The API works but cannot be deployed. No Dockerfile, no secrets management, no security hardening. Phase 2 fixes that.

## What Phase 2 introduces and builds on top of Phase 1

**v4 — Docker**
Takes the Phase 1 FastAPI app and puts it inside a container. The code does not change — the environment it runs in does. A multi-stage Dockerfile builds a minimal production image. Docker Compose brings up AOIS alongside Redis and Postgres locally so all services run together with one command. Trivy scans the image for vulnerabilities before it goes anywhere. Cosign signs it so you can prove the image is yours.

What Phase 1 contributes: the working FastAPI app, requirements.txt, and the understanding of what the service does — all of that goes into the container unchanged.

**v5 — Security Hardening**
Takes the running container from v4 and makes it production-safe. Every endpoint from Phase 1 gets OWASP API Top 10 applied to it. Every AI interaction gets OWASP LLM Top 10 applied — because AOIS accepts raw log data from untrusted sources, and an attacker can embed instructions inside a log line to manipulate the model (prompt injection). Guardrails AI wraps the output so AOIS can never recommend something destructive. Rate limiting and input size caps go on the API. The container runs as a non-root user with a read-only filesystem. Vault manages the API keys that were in a flat .env file in Phase 1.

What Phase 1 contributes: the `POST /analyze` endpoint is the exact attack surface that gets hardened. The system prompt and tool definitions from v1–v3 are what get red-teamed with PyRIT and Garak.

**The progression:**
Phase 1 answered: can AOIS analyse a log intelligently?
Phase 2 answers: can AOIS run safely in the real world?
