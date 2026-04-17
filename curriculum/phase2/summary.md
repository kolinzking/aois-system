# Phase 2 — Containerise & Secure

## Introduction
Phase 1 proved the intelligence works. Phase 2 asks a harder question: can it survive contact with the real world?

A service that only runs on a developer's laptop is not a service — it is a prototype. To be real, it must run anywhere identically, it must not be exploitable, and it must not leak secrets. Phase 2 delivers all three.

The first half (v4) is about portability — packaging AOIS into a container so it runs the same way in development, CI, staging, and production. The second half (v5) is about trust — hardening every surface an attacker could reach, from the API endpoints to the AI layer itself.

AI systems have a threat model that pure API services do not. AOIS accepts raw log data from infrastructure it monitors. An attacker who controls a log source can embed instructions inside a log line and attempt to manipulate the model's output. This is prompt injection — and it is the OWASP LLM Top 10's most prominent risk. Phase 2 teaches you to defend against it before the system is ever deployed.

By the end of Phase 2 you have a containerised, scanned, signed, rate-limited, injection-defended, secrets-managed service. That is what production AI readiness looks like.

## Versions
- **v4** — Multi-stage Dockerfile, Docker Compose (AOIS + Redis + Postgres), Trivy scan to zero HIGH/CRITICAL, Cosign image signing.
- **v5** — OWASP API Top 10 hardening, OWASP LLM Top 10 hardening, prompt injection defence, Guardrails AI output validation, PyRIT + Garak red-teaming, rate limiting, Vault for secrets.

## State at close
AOIS runs in a signed, scanned container alongside Redis and Postgres.
Rate limited, input sanitised, prompt-injection defended, output validated.
Secrets managed through Vault, not a flat file.

## What Phase 3 picks up
The service is containerised and secured but still runs only locally. Phase 3 takes it to a real cluster — k3s on a Hetzner VPS — and introduces Kubernetes, Helm packaging, and ArgoCD GitOps so a git push deploys the service automatically.
