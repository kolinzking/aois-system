# Phase 8 — Full Stack Dashboard

Phase 7 built the autonomous agent. Now you make it visible.

The AOIS agent can investigate incidents, propose remediations, and route through approval gates. None of this is accessible to an operator who is not running Python scripts in a terminal. Phase 8 builds the dashboard that makes AOIS a product: a real-time web UI where logs flow in, analyses appear, and humans approve or reject remediation proposals with one click.

## What Phase 8 Builds

**v26 — React Dashboard**
Real-time incident feed via WebSocket. Streaming AI responses as they generate. Severity heatmap, agent action log, approve/reject controls.

**v27 — Auth & Multi-tenancy**
JWT authentication, RBAC (viewer/analyst/operator/admin), OpenFGA fine-grained authorization, SPIFFE/SPIRE workload identity.

## Why This Matters

The best agent in the world is useless if no one can interact with it. The dashboard is the operator interface:
- Real-time: incidents appear as they are detected, analyses stream in as they generate
- Actionable: one-click approve/reject for remediation proposals
- Auditable: full agent action log with timestamps, tool calls, costs

This is also where the Vercel AI SDK enters — the modern standard for AI-powered web interfaces. Streaming responses, tool call visibility, and multi-modal support are all built into the SDK.
