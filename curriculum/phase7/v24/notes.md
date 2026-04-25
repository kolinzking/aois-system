# v24 — Multi-Agent Frameworks: AutoGen, CrewAI, Google ADK, Pydantic AI

⏱ **Estimated time: 8–10 hours**

---

## Prerequisites

v23.5 eval suite passes. Python 3.11+.

```bash
# Eval suite passes
python3 evals/run_evals.py
# SLO STATUS: ✓ PASS

# Python 3.11+
python3 --version
# Python 3.11.x

# Anthropic SDK available
python3 -c "import anthropic; print(anthropic.__version__)"
# 0.x.x
```

---

## Learning Goals

By the end you will be able to:

- Explain the mental model behind CrewAI (role-based sequential collaboration) and how it differs from AutoGen (conversation-based iteration)
- Build a CrewAI crew: Detector, Root Cause Analyst, Remediation, Report Writer — four agents, one incident
- Build an AutoGen conversational group: agents challenge each other's reasoning until consensus
- Wire a Pydantic AI agent with full type safety, dependency injection, and a testable interface
- Describe where Google ADK fits (Vertex AI, cross-vendor via A2A) without deploying it
- Run all three frameworks against the same incident and observe what each produces
- Explain which framework to reach for and why, given a specific production use case

---

## The Core Insight

You are not learning three frameworks. You are learning **one pattern expressed three different ways**:

```
Multiple agents with different specializations collaborate on a task.
Each agent has a role. Roles constrain what the agent does and how it reasons.
Agents hand off work between each other.
The whole is more capable than any single agent.
```

CrewAI makes roles explicit: a Detector agent, a Root Cause Analyst agent. Each has a system prompt that defines its role, its goal, and its backstory.

AutoGen makes conversation explicit: agents send messages to each other in a group chat. They challenge wrong answers, request clarification, and iterate until all agents agree the result is correct.

Pydantic AI makes type safety explicit: agents return typed objects (not strings), dependencies are injected (testable), and the framework enforces structure.

The insight: frameworks consolidate, patterns persist. You are learning the pattern. When AutoGen 3.0 ships with a different API, the conversation-iteration pattern is the same. When CrewAI merges with LangGraph, the role-based delegation pattern is the same.

---

## Framework 1: CrewAI — Role-Based Sequential Collaboration

### Mental Model

A crew is a team. Each team member has a role (job title), a goal (what they are trying to achieve), and a backstory (why they reason the way they do). Tasks are assigned to roles. The crew orchestrates sequential execution: one role's output becomes the next role's input.

```
Detector → Root Cause Analyst → Remediation Planner → Report Writer
    ↑ output fed as context to next agent ↑
```

CrewAI is useful when:
- The work has clear sequential stages (detect → analyze → fix → report)
- Each stage requires a different kind of reasoning (classification vs deep analysis vs remediation planning)
- You want role-based prompting without building the orchestration yourself

---

### Installation

```bash
pip install crewai crewai-tools
```

---

### The AOIS Crew

```python
# multi_agent/crewai_crew.py
"""AOIS incident response as a CrewAI crew."""
from crewai import Agent, Task, Crew, Process
from langchain_anthropic import ChatAnthropic
import os

_llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_tokens=1024,
)


def build_crew(incident: str) -> Crew:
    # --- Agents ---
    detector = Agent(
        role="Alert Detector",
        goal="Classify incoming alerts by severity (P1-P4) and determine if investigation is needed",
        backstory=(
            "You are a senior SRE who has seen thousands of production incidents. "
            "You know exactly which alerts are critical and which are noise. "
            "You never escalate P3 incidents as P1, and you never miss a real P1."
        ),
        llm=_llm,
        verbose=False,
    )

    analyst = Agent(
        role="Root Cause Analyst",
        goal="Determine the precise root cause of an incident from the available evidence",
        backstory=(
            "You are a distributed systems expert. Given logs, events, and metrics, "
            "you identify the exact root cause — not symptoms. You ask: what changed? "
            "What is the single underlying failure that explains all symptoms?"
        ),
        llm=_llm,
        verbose=False,
    )

    remediator = Agent(
        role="Remediation Planner",
        goal="Propose a specific, safe, and reversible remediation action for the identified root cause",
        backstory=(
            "You are a cautious operations engineer. You never recommend irreversible actions. "
            "Every remediation you propose can be rolled back. "
            "You prefer surgical fixes over broad changes."
        ),
        llm=_llm,
        verbose=False,
    )

    reporter = Agent(
        role="Incident Report Writer",
        goal="Write a clear, structured postmortem entry that non-technical stakeholders can read",
        backstory=(
            "You write incident reports that executives can read in 60 seconds. "
            "You translate technical root causes into business impact. "
            "You always include: what happened, why, and what prevents recurrence."
        ),
        llm=_llm,
        verbose=False,
    )

    # --- Tasks ---
    detect_task = Task(
        description=f"Classify this alert: '{incident}'. Return severity (P1-P4) and whether investigation is needed.",
        expected_output="Severity classification with brief justification",
        agent=detector,
    )

    analyze_task = Task(
        description=(
            f"Incident: '{incident}'\n"
            f"Based on the detection output, determine the most likely root cause. "
            f"Identify the single underlying failure that explains the symptoms."
        ),
        expected_output="Root cause statement with supporting reasoning",
        agent=analyst,
        context=[detect_task],
    )

    remediate_task = Task(
        description=(
            f"Incident: '{incident}'\n"
            f"Based on the root cause analysis, propose a specific, reversible remediation action. "
            f"Include the exact command or configuration change needed."
        ),
        expected_output="Specific remediation action with rollback instructions",
        agent=remediator,
        context=[analyze_task],
    )

    report_task = Task(
        description=(
            f"Write a structured incident report for: '{incident}'\n"
            f"Include: Severity, Summary (1 sentence), Root Cause, Impact, Remediation, Prevention."
        ),
        expected_output="Structured incident report in plain English",
        agent=reporter,
        context=[detect_task, analyze_task, remediate_task],
    )

    return Crew(
        agents=[detector, analyst, remediator, reporter],
        tasks=[detect_task, analyze_task, remediate_task, report_task],
        process=Process.sequential,
        verbose=False,
    )


def run_crew(incident: str) -> str:
    """Run the full AOIS crew and return the final report."""
    crew = build_crew(incident)
    result = crew.kickoff()
    return str(result)
```

---

## ▶ STOP — do this now

Run the CrewAI crew against a real incident and observe each agent's output:

```bash
pip install crewai langchain-anthropic

python3 - << 'EOF'
from multi_agent.crewai_crew import run_crew
result = run_crew("auth-service pod OOMKilled exit code 137 — memory limit 256Mi, third time this week")
print(result)
EOF
```

Expected: four agents execute sequentially. Detector outputs "P1 — OOMKill on auth-service is critical." Analyst traces root cause to undersized memory limit. Remediator proposes `kubectl set resources`. Reporter produces a readable postmortem.

Observe: the output from each agent becomes context for the next. This is the key mechanism — sequential context threading.

---

## Framework 2: AutoGen — Conversation-Based Iteration

### Mental Model

AutoGen agents talk to each other in a group chat. There is no predetermined sequence. Agents respond to each other, challenge wrong answers, ask for more detail, and iterate until a human proxy or termination condition says "done."

```
GroupChat:
  SRE-Analyst: "This looks like an OOMKill. Memory limit is too low."
  Security-Reviewer: "Before recommending memory increase — is there a memory leak? Increasing limit on a leaking service just delays the failure."
  SRE-Analyst: "Good point. Let me check — the increase has been happening for 3 days, which matches the deployment on Monday."
  Security-Reviewer: "That suggests the deployment introduced a memory regression, not a baseline limit issue. The fix is to revert or patch the deployment."
  Manager: "Agreed. Proposed action: rollback the Monday deployment and investigate the memory regression."
```

AutoGen is useful when:
- The problem is ambiguous and requires iteration
- Multiple perspectives are needed (SRE + security + database expert)
- You want agents to challenge each other rather than follow a fixed sequence

---

### Installation

```bash
pip install pyautogen
```

---

### The AOIS AutoGen Group

```python
# multi_agent/autogen_group.py
"""AOIS incident analysis as an AutoGen conversational group."""
import os
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager

_llm_config = {
    "config_list": [
        {
            "model": "claude-haiku-4-5-20251001",
            "api_key": os.getenv("ANTHROPIC_API_KEY"),
            "api_type": "anthropic",
        }
    ],
    "temperature": 0.1,
    "max_tokens": 512,
}


def run_autogen_analysis(incident: str) -> str:
    """
    Run a multi-agent AutoGen group to analyze an incident.
    Agents challenge each other until they reach consensus.
    """
    sre_analyst = AssistantAgent(
        name="SRE_Analyst",
        system_message=(
            "You are a senior SRE. Analyze the incident, propose root cause and remediation. "
            "Be specific. When another agent challenges your analysis, engage with their objection — "
            "either defend your position with evidence or revise it."
        ),
        llm_config=_llm_config,
    )

    security_reviewer = AssistantAgent(
        name="Security_Reviewer",
        system_message=(
            "You are a security engineer reviewing SRE recommendations. "
            "Challenge any recommendation that could create a security risk. "
            "Approve actions that are safe. If you agree with the SRE's analysis, say 'APPROVED'. "
            "If not, explain the specific security concern."
        ),
        llm_config=_llm_config,
    )

    human_proxy = UserProxyAgent(
        name="Manager",
        human_input_mode="NEVER",  # automated — no human input during eval
        max_consecutive_auto_reply=1,
        is_termination_msg=lambda x: "FINAL RECOMMENDATION:" in x.get("content", ""),
        code_execution_config=False,
        system_message=(
            "You are the on-call manager. When the SRE and Security reviewer have reached consensus, "
            "summarize the agreed-upon action as: 'FINAL RECOMMENDATION: <action>'"
        ),
    )

    groupchat = GroupChat(
        agents=[sre_analyst, security_reviewer, human_proxy],
        messages=[],
        max_round=6,
    )

    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=_llm_config,
    )

    human_proxy.initiate_chat(
        manager,
        message=f"Incident requiring analysis: {incident}\nProvide root cause and recommended action.",
    )

    # Extract the final recommendation from conversation history
    messages = groupchat.messages
    for msg in reversed(messages):
        if "FINAL RECOMMENDATION:" in msg.get("content", ""):
            return msg["content"]

    # If no explicit final, return the last SRE message
    for msg in reversed(messages):
        if msg.get("name") == "SRE_Analyst":
            return msg["content"]

    return "No consensus reached"
```

---

## ▶ STOP — do this now

Run the AutoGen group against the same incident:

```bash
python3 - << 'EOF'
from multi_agent.autogen_group import run_autogen_analysis
result = run_autogen_analysis(
    "auth-service pod OOMKilled exit code 137 — memory limit 256Mi, third time this week"
)
print("\n--- AutoGen Final Output ---")
print(result)
EOF
```

Compare with the CrewAI output. Key differences to observe:
- **Sequence**: CrewAI executes in a fixed order; AutoGen agents respond dynamically
- **Challenge**: AutoGen allows Security_Reviewer to push back on SRE_Analyst's recommendation; CrewAI does not
- **Verbosity**: AutoGen generates a full conversation; CrewAI generates only the task outputs

---

## Framework 3: Pydantic AI — Type-Safe, Testable Agents

### Mental Model

Pydantic AI is built by the Pydantic team (the same team behind `instructor`). It makes agents fully type-safe: they return Pydantic models, not strings. Dependencies are injected — the agent does not reach for `os.getenv("DATABASE_URL")` directly. This makes agents testable: you swap the real DB for a mock in tests.

This is what a production-grade agent library looks like when it is built by software engineers first, AI researchers second.

---

### Installation

```bash
pip install pydantic-ai
```

---

### The AOIS Pydantic AI Agent

```python
# multi_agent/pydantic_agent.py
"""AOIS incident analysis with Pydantic AI — type-safe, dependency-injected, testable."""
from dataclasses import dataclass
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
import os


class IncidentAnalysis(BaseModel):
    """Structured output — the agent MUST return this, validated by Pydantic."""
    severity: str
    root_cause: str
    proposed_action: str
    confidence: float
    requires_human_approval: bool


@dataclass
class AoisDeps:
    """Dependencies injected at runtime. Swap for mocks in tests."""
    incident_history_summary: str  # pre-fetched from RAG layer
    cluster_name: str


_agent = Agent(
    model=AnthropicModel(
        "claude-haiku-4-5-20251001",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    ),
    result_type=IncidentAnalysis,
    deps_type=AoisDeps,
    system_prompt=(
        "You are AOIS, an SRE investigation agent. "
        "Analyze the incident using the provided context and return a structured analysis. "
        "Set requires_human_approval=true for any action that modifies production state. "
        "Severity thresholds: P1=outage/breach, P2=degraded/approaching limits, "
        "P3=warning/no current impact, P4=informational."
    ),
)


async def analyze_incident(incident: str, deps: AoisDeps) -> IncidentAnalysis:
    """Run the typed agent. Returns a validated IncidentAnalysis — never a raw string."""
    prompt = (
        f"Incident: {incident}\n\n"
        f"Cluster: {deps.cluster_name}\n"
        f"Relevant history: {deps.incident_history_summary}\n\n"
        f"Provide your structured analysis."
    )
    result = await _agent.run(prompt, deps=deps)
    return result.data  # always an IncidentAnalysis — Pydantic validates it
```

---

## ▶ STOP — do this now

Run the Pydantic AI agent. Observe the type-safe return value:

```bash
python3 - << 'EOF'
import asyncio
from multi_agent.pydantic_agent import analyze_incident, AoisDeps

async def main():
    deps = AoisDeps(
        incident_history_summary="auth-service OOMKilled twice last month — fixed both times by increasing memory limit to 512Mi",
        cluster_name="hetzner-k3s-prod"
    )
    result = await analyze_incident(
        "auth-service pod OOMKilled exit code 137 — memory limit 256Mi, third time this week",
        deps=deps,
    )
    print(f"Severity: {result.severity}")
    print(f"Root cause: {result.root_cause}")
    print(f"Proposed action: {result.proposed_action}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Human approval required: {result.requires_human_approval}")
    print(f"\nType: {type(result)}")  # <class 'multi_agent.pydantic_agent.IncidentAnalysis'>

asyncio.run(main())
EOF
```

The key: `result` is always a validated `IncidentAnalysis`. Pydantic AI retries the LLM call if it returns something that cannot be validated. The agent cannot return a string where `confidence` should be a float.

---

## Comparing All Three on the Same Incident

Run all three against the same incident and compare:

```python
# multi_agent/compare.py
"""Run all three frameworks against the same incident and compare outputs."""
import asyncio
import time
from multi_agent.crewai_crew import run_crew
from multi_agent.autogen_group import run_autogen_analysis
from multi_agent.pydantic_agent import analyze_incident, AoisDeps


async def compare(incident: str):
    print(f"Incident: {incident}\n")
    print("=" * 60)

    # CrewAI
    t0 = time.perf_counter()
    crewai_result = run_crew(incident)
    crewai_time = time.perf_counter() - t0
    print(f"CrewAI ({crewai_time:.1f}s):")
    print(crewai_result[:400])
    print()

    # AutoGen
    t0 = time.perf_counter()
    autogen_result = run_autogen_analysis(incident)
    autogen_time = time.perf_counter() - t0
    print(f"AutoGen ({autogen_time:.1f}s):")
    print(autogen_result[:400])
    print()

    # Pydantic AI
    t0 = time.perf_counter()
    deps = AoisDeps(incident_history_summary="No prior incidents found", cluster_name="hetzner-k3s-prod")
    pydantic_result = await analyze_incident(incident, deps)
    pydantic_time = time.perf_counter() - t0
    print(f"Pydantic AI ({pydantic_time:.1f}s):")
    print(f"  severity={pydantic_result.severity}")
    print(f"  root_cause={pydantic_result.root_cause[:200]}")
    print(f"  action={pydantic_result.proposed_action[:200]}")
    print(f"  confidence={pydantic_result.confidence:.0%}")

    print("\n" + "=" * 60)
    print("Comparison:")
    print(f"  CrewAI:     {crewai_time:.1f}s — role-based, sequential, narrative output")
    print(f"  AutoGen:    {autogen_time:.1f}s — conversation-based, agents challenge each other")
    print(f"  Pydantic AI:{pydantic_time:.1f}s — type-safe, validated structured output")


if __name__ == "__main__":
    asyncio.run(compare(
        "auth-service pod OOMKilled exit code 137 — memory limit 256Mi, third time this week"
    ))
```

---

## Google ADK: Cross-Vendor Agent Handoff

Google ADK (Agent Development Kit) is Google's official multi-agent framework (2025). It deploys to Vertex AI and uses A2A Protocol for agent-to-agent communication.

For AOIS, the integration pattern: AOIS produces a structured incident report → sends it via A2A to a Google ADK agent hosted on Vertex AI → the ADK agent handles enterprise notification (Google Chat, Gmail, incident ticketing in a Google Workspace environment).

This is not about learning ADK deeply — it is about recognizing the cross-vendor pattern:

```
AOIS (Anthropic ecosystem)     ←A2A→     Google ADK agent (Google ecosystem)
         ↑                                           ↑
   Claude models                              Gemini models
   Hetzner k3s                               Vertex AI
   Python SDK                                ADK SDK
```

The A2A handoff was built in v21. The same `POST /tasks/send` endpoint that handles any A2A call handles ADK calls. The ADK agent reads the incident report from the A2A task payload and acts on it in the Google ecosystem.

```python
# Simulated ADK cross-vendor handoff — A2A call to a hypothetical Google ADK endpoint
import httpx

async def send_to_adk_agent(incident_report: str, session_id: str):
    """Send completed AOIS report to Google ADK agent via A2A protocol."""
    payload = {
        "id": session_id,
        "message": {
            "role": "user",
            "parts": [{"text": incident_report}],
        },
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://your-adk-agent.run.app/tasks/send",  # ADK endpoint
            json=payload,
            timeout=30,
        )
        return response.json()
```

The actual ADK deployment uses `google-adk` Python package and `adk deploy` to Vertex AI. The architectural point: the A2A protocol makes this cross-vendor handoff possible without either side knowing the other's internal implementation.

---

## OpenAI Agents SDK: Handoffs and Guardrails

The OpenAI Agents SDK (released 2025) is OpenAI's production agent framework — and you will encounter it in every enterprise codebase you work in. Not because it is architecturally superior to LangGraph or Pydantic AI, but because OpenAI has the largest developer ecosystem and enterprises adopt what their largest model vendor supports.

Three primitives that define its architecture:

**Handoffs** — an agent can transfer control to a more specialised agent mid-conversation, passing the full context:

```python
from agents import Agent, handoff

senior_agent = Agent(
    name="SeniorSRE",
    instructions="You handle P1/P2 incidents. Investigate thoroughly, propose remediation with rollback steps.",
)

triage_agent = Agent(
    name="Triage",
    instructions="Classify incident severity. For P1/P2, hand off to senior_agent immediately.",
    tools=[handoff(senior_agent, tool_description="Escalate critical incidents to senior SRE")]
)
```

The difference from CrewAI's sequential output-passing: a handoff transfers the full conversation context, not just the last output. The senior agent sees the complete incident history.

**Guardrails** — input and output validation that runs as a separate LLM call before the response is returned. This is structurally different from v5's output blocklist (which is a regex scan). A guardrail is a separate agent that reviews the proposed action:

```python
from agents import Agent, output_guardrail, GuardrailFunctionOutput
from pydantic import BaseModel

class SafetyCheck(BaseModel):
    is_safe: bool
    reason: str

@output_guardrail
async def aois_safety_guardrail(ctx, agent, output):
    check = await Runner.run(safety_checker_agent, f"Is this action safe? {output}", context=ctx.context)
    return GuardrailFunctionOutput(
        output_info=check.final_output,
        tripwire_triggered=not check.final_output.is_safe
    )

aois_agent = Agent(
    name="AOIS",
    instructions="Analyze incidents and propose remediation.",
    output_guardrails=[aois_safety_guardrail],
)
```

**Built-in tracing** — every agent invocation, handoff, and tool call is structured and traceable without additional OTel instrumentation. The SDK emits to OpenAI's platform dashboard by default, configurable to any trace backend.

### The Architectural Point

LangGraph expresses control flow as explicit edges in a state graph. AutoGen expresses it as a conversation. OpenAI Agents SDK expresses it as handoffs — an agent decides to transfer based on its system prompt instructions. Same pattern, different mechanism.

When you encounter OpenAI Agents SDK in an enterprise codebase, you will recognise: the triage-then-handoff structure is the same as LangGraph's detect→investigate nodes, the guardrails are the same concern as v5's output blocklist but applied at the agent boundary rather than as a regex filter.

---

## Framework Selection Guide

| Use case | Best framework |
|---|---|
| Sequential stages with clear roles (detect → analyze → fix → report) | CrewAI |
| Ambiguous problem requiring iteration and challenge | AutoGen |
| Production system requiring type safety and testability | Pydantic AI |
| Vertex AI deployment or Google Workspace integration | Google ADK |
| Multi-step investigation with state persistence | LangGraph (v23) |
| Durable execution across crashes | Temporal (v22) |
| Handoff-based routing with output guardrails (OpenAI ecosystem) | OpenAI Agents SDK |

The rule: reach for the simplest thing that works. A flat loop (v20) beats all of these for a well-defined, single-stage task. LangGraph is right when you need explicit state machine stages. CrewAI is right when you need role-based sequential delegation. AutoGen is right when you need iterative challenge and refinement. Pydantic AI is right when you need type safety at the agent boundary.

Do not use multi-agent frameworks for tasks that a single well-prompted agent handles reliably.

---

## Common Mistakes

### 1. Agent role prompts that are too similar

If all four CrewAI agents have similar backstories ("I am an expert SRE..."), they produce similar outputs. The role differentiation is in the backstory. A Detector and a Root Cause Analyst must reason differently.

```python
# Wrong — both are generic SREs
analyst = Agent(role="SRE Analyst", backstory="You are an SRE expert who analyzes incidents...")
detector = Agent(role="SRE Detector", backstory="You are an SRE expert who detects incidents...")

# Correct — different thinking styles
analyst = Agent(
    role="Root Cause Analyst",
    backstory="You are a distributed systems expert. You ask: what changed? What single failure explains all symptoms? You never stop at the symptom."
)
detector = Agent(
    role="Alert Classifier",
    backstory="You have seen 10,000 production alerts. You know exactly which ones are noise. Your job is to classify, not to investigate."
)
```

---

### 2. AutoGen `max_round` too low — agents stop before consensus

```
# Wrong — agents are cut off mid-analysis
GroupChat(max_round=2)

# Correct — allow enough rounds for meaningful challenge
GroupChat(max_round=6)
```

If agents are producing "I agree" after one round, they are not actually challenging each other. Increase max_round and check whether the Security_Reviewer is actually pushing back.

---

### 3. Pydantic AI: model returns invalid JSON → validation loop

Pydantic AI retries on validation failure. If the model consistently fails to return a valid `IncidentAnalysis`, check:
1. The system prompt tells the model to return a structured analysis matching the schema
2. The result_type fields have clear types (float, not `Union[float, str]`)
3. `confidence` should be described as "a number between 0.0 and 1.0" — not "confidence level"

---

## Troubleshooting

### CrewAI: `LangChain` not finding Anthropic model

```
ValueError: Could not load Anthropic model — check ANTHROPIC_API_KEY
```

Set the key in environment: `export ANTHROPIC_API_KEY=your_key_here`
Also ensure `langchain-anthropic` is installed: `pip install langchain-anthropic`

---

### AutoGen: group chat terminates immediately

Check the `is_termination_msg` function — if it matches too broadly, the first message triggers termination.

```python
# Too broad — matches "FINAL" in any context
is_termination_msg=lambda x: "FINAL" in x.get("content", "")

# Correct — matches only the expected termination phrase
is_termination_msg=lambda x: "FINAL RECOMMENDATION:" in x.get("content", "")
```

---

### Pydantic AI: `ValidationError` on result

The model returned something that does not match `IncidentAnalysis`. Enable debug logging:

```python
import logging
logging.getLogger("pydantic_ai").setLevel(logging.DEBUG)
```

The raw model response will be logged before validation. Check which field is failing.

---

## Connection to Later Phases

### To v25 (E2B Sandboxed Execution)
The Pydantic AI agent's `proposed_action` is a typed string. In v25, that string is passed to E2B to execute in a sandbox. Type safety at the agent boundary means the E2B executor receives a guaranteed string, not a dict that might be missing the action field.

### To v28 (GitHub Actions + Dagger)
The eval suite from v23.5 runs against all three framework implementations. v28 adds a CI job that benchmarks CrewAI vs AutoGen vs Pydantic AI on the golden dataset. Regressions in any framework block the merge.

### To v29 (Weights & Biases)
W&B logs each framework's latency, cost, and eval score as separate experiment runs. The W&B dashboard shows which framework performs best on each incident category over time.

---


## Build-It-Blind Challenge

Close the notes. From memory: write a two-agent CrewAI crew — a Detector agent that classifies severity and a Remediation agent that proposes a fix. Both agents use Claude. The crew runs sequentially, passing the Detector output to Remediation. 20 minutes.

```python
result = crew.kickoff(inputs={"log": "auth-service OOMKilled exit code 137"})
print(result.raw)
# Should contain both severity classification and remediation proposal
```

---

## Failure Injection

Create a circular dependency between two AutoGen agents and observe the termination condition:

```python
# Agent A calls Agent B, Agent B calls Agent A back
# What prevents an infinite loop?
# Remove the termination condition and run — how many rounds before it stops?
```

Every multi-agent framework has a termination problem. In AutoGen it is the `is_termination_msg` function. In LangGraph it is the `END` node. In CrewAI it is task completion. Understand how each framework handles infinite loops — this is the failure mode that burns GPU budget.

---

## Osmosis Check

1. You have LangGraph (v23), CrewAI (v24), AutoGen (v24), and Pydantic AI (v24) all available. An incident requires: parallel investigation of 3 subsystems simultaneously, stateful memory across steps, and a human approval gate before remediation. Which framework is the right choice and why? (4-framework comparison — reason from architecture, not preference)
2. Google ADK sends an incident report from AOIS to a Vertex-hosted agent via A2A. That agent is running Gemini 2.5 Pro. The A2A message contains the full incident context including log data that may contain customer identifiers. Which v5 security control should be applied before the A2A handoff, and where in the call stack does it apply?

---

## Mastery Checkpoint

1. Run `python3 multi_agent/compare.py` with a P1 incident. Record: CrewAI latency, AutoGen latency, Pydantic AI latency, and which produced the most actionable proposed action.

2. Modify the CrewAI `analyst` agent backstory to explicitly ask "what changed recently?" Rerun. Does the root cause analysis improve?

3. Add a fourth AutoGen agent: `Database_Expert` who challenges recommendations that might affect data consistency. Run the auth-service OOMKill incident — does the expert have anything to add?

4. Write a test for the Pydantic AI agent that injects a mock `AoisDeps` with a specific `incident_history_summary` and asserts that `requires_human_approval=True` for a memory increase recommendation.

5. Explain to a junior engineer: why would you use AutoGen instead of CrewAI for a complex incident that involves ambiguous evidence? Give a concrete example.

6. Explain to a senior engineer: what is the production risk of using AutoGen's `max_round` without a cost cap? How would you add one?

7. Google ADK is listed in CLAUDE.md but you did not deploy it to Vertex AI in this version. Explain why — what is the architectural point that matters more than the deployment?

8. Run the v23.5 eval suite against the Pydantic AI agent's severity classifications. Compare accuracy to the LangGraph detect_node. Which scores higher and why?

**The mastery bar:** you can explain to any engineer why there are three multi-agent frameworks covered in this version, which one to use for a given production scenario, and what the shared pattern is that persists when any specific framework is replaced.

---

## 4-Layer Tool Understanding

### CrewAI

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | A single LLM prompt trying to classify, analyze, remediate, and report an incident is doing too many things. CrewAI splits these into separate roles — each agent has one job and is prompted to do that job well. The output of one role feeds the next. |
| **System Role** | Where does it sit in AOIS? | Alternative to the LangGraph SRE loop for sequential incident response. The crew (Detector → Analyst → Remediator → Reporter) maps directly to the 4 stages of the SRE workflow. Used when you want role-based prompting without building the orchestration yourself. |
| **Technical** | What is it, precisely? | A Python framework where agents (LLM + system prompt + role definition) are assigned tasks, and a Process (sequential or hierarchical) coordinates their execution. Task `context` passes the output of completed tasks to subsequent tasks. The crew orchestrator calls each agent in sequence and assembles the final output. |
| **Remove it** | What breaks, and how fast? | Remove CrewAI → the SRE loop collapses to a single LLM prompt trying to do all 4 roles at once. Role-based reasoning degrades. The classifier does not have a specialized "I've seen 10,000 alerts" backstory — it reasons generically. Analysis quality declines for complex incidents. |

### AutoGen

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | When an incident is ambiguous, a single agent cannot challenge its own reasoning. AutoGen creates a group chat where agents with different perspectives message each other. A Security Reviewer can push back on an SRE recommendation before it becomes the final answer. |
| **System Role** | Where does it sit in AOIS? | Alternative to CrewAI for incidents where the root cause is not obvious and requires iterative debate. Used in production when: the evidence is incomplete, multiple teams (SRE, security, database) need to weigh in, or the recommended action has cross-functional risk. |
| **Technical** | What is it, precisely? | A Microsoft-backed framework where AssistantAgents and UserProxyAgents participate in a GroupChat managed by a GroupChatManager (itself an LLM). Agents send messages sequentially; the manager selects which agent responds next based on context. A termination condition or human input ends the conversation. |
| **Remove it** | What breaks, and how fast? | Remove AutoGen → ambiguous incidents get single-perspective analysis. Security Reviewer does not push back on memory increase for a leaking service. SRE recommends increasing the limit, the leak continues, the service OOMKills again next week. The iterative challenge is what catches this. |

### Pydantic AI

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | LLM outputs are strings. When you need `confidence: 0.87` and the LLM returns `"confidence: high"`, your downstream code breaks. Pydantic AI makes agents return typed, validated objects — the same guarantee Pydantic gives for API inputs. |
| **System Role** | Where does it sit in AOIS? | The preferred framework for any agent whose output feeds a typed system (database write, E2B executor, downstream API call). The `IncidentAnalysis` model is validated before it reaches any downstream consumer. In v25, the E2B sandbox receives a guaranteed `str` action, not a potentially-missing dict key. |
| **Technical** | What is it, precisely? | A Python agent framework from the Pydantic team. Agents are typed: `Agent[DepsType, ResultType]`. The LLM is called, output is parsed against the `result_type` Pydantic model, and retried if validation fails. Dependencies are injected via `deps_type` — the agent receives them at call time, not via global state. |
| **Remove it** | What breaks, and how fast? | Remove Pydantic AI → agent output is a raw string. Downstream code uses `.get("severity", "P3")` on a JSON parse that may fail. `confidence` is a string that cannot be compared numerically. Tests mock string outputs instead of typed objects. Production: a malformed LLM response silently sets severity to None and the incident is never escalated. |

### OpenAI Agents SDK

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Building agents by hand requires routing logic, tool call handling, output validation, and handoff mechanics — all wired in custom Python. The OpenAI Agents SDK provides these as primitives: agents with instructions, tools, handoffs to other agents, and output guardrails that validate before the response leaves the agent boundary. |
| **System Role** | Where does it sit in AOIS? | An alternative multi-agent implementation pattern — the one you will encounter most often in enterprise codebases. The AOIS triage agent classifies severity; a handoff routes P1/P2 to a senior investigation agent with deeper context. Output guardrails apply the same safety checks as v5's output blocklist, but as a separate verification agent rather than a regex filter — structurally harder to bypass. |
| **Technical** | What is it, precisely? | A Python SDK with `Agent` (instructions + tools + handoffs), `Runner.run()` (executes the agent loop), and `@output_guardrail` (pre/post validation that runs as a separate LLM call). Agents can be composed: a triage agent's handoff target is another `Agent` object, and the full conversation context transfers with it. Built-in tracing emits structured events for every invocation, handoff, and tool call — configurable to any trace backend. Works with any model via `Agent(model="claude-haiku-4-5-20251001")`. |
| **Remove it** | What breaks, and how fast? | Remove it → return to manual tool call routing (v20 pattern), manual output validation (v5 blocklist), and no structured handoff mechanism. For AOIS deployed in an organisation already using OpenAI tooling, removing it means reimplementing the same patterns with a different framework — the cost is migration effort and lost interoperability with OpenAI-native tooling the rest of the team depends on. |
