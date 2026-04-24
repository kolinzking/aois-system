# Phase 7 — Autonomous Agents

## What This Phase Builds

Phase 7 takes AOIS from a read-only analysis engine to an autonomous SRE agent. By the end of this phase, AOIS can:

- **Investigate** incidents by pulling its own evidence (pod logs, node state, metrics) rather than waiting for a human to provide them
- **Remember** past incidents and apply historical knowledge to current investigations
- **Communicate** with other AI systems via MCP and A2A protocols
- **Execute durably** — survive pod restarts, cluster failures, and network partitions mid-investigation
- **Orchestrate** multi-step reasoning via a stateful agent graph with human approval gates
- **Coordinate** with specialist agents running in other frameworks (AutoGen, Google ADK, CrewAI)
- **Execute safely** in sandboxed environments before proposing production changes

This is the phase that transforms AOIS from a smart alert summarizer into an AI system you would actually trust in a production on-call rotation.

## What Must Be True Before Any Agent Gets Tools

The instinct is to jump straight to `get_pod_logs` and watch the agent investigate. Resist it.

An agent with tools and no governance is not more capable — it is more dangerous. The difference between a demo agent and a production agent is not the tools. It is the boundary around what the tools can do.

The first thing you build in Phase 7 is not a tool. It is the gate.

**Phase 7 gate** (this document's companion): agent capability boundary, circuit breaker, and kill switch. AOIS does not touch a tool until this is in place.

## The Phase 7 Build Order

| Version | What | Gate |
|---|---|---|
| Phase 7 gate | Capability boundary, circuit breaker, kill switch | Required before v20 |
| v20 | Claude tool use + Mem0 persistent memory | Needs gate |
| v21 | MCP server + A2A protocol | Needs v20 |
| v21.5 | MCP security hardening | Needs v21 |
| v22 | Temporal durable execution | Needs v20 |
| v23 | LangGraph autonomous SRE loop | Needs v22 |
| v23.5 | Agent evaluation — evals before anything ships | Needs v23 |
| v24 | AutoGen + CrewAI + Google ADK | Needs v23.5 |
| v25 | E2B sandboxed code execution | Needs v24 |

## What Phase 7 Produces

A running autonomous SRE agent that:
- Detects an OOMKilled alert from Kafka
- Retrieves the pod logs, node state, and relevant past incidents from memory
- Hypothesizes the root cause with evidence
- Waits for human approval before executing any fix
- Executes the approved fix in a sandbox first
- Reports the resolution with full audit trail

That is the system. Phase 7 is where it comes alive.
