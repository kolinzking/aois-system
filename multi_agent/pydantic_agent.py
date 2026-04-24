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
    incident_history_summary: str
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
        "P3=warning/no current impact, P4=informational. "
        "confidence must be a float between 0.0 and 1.0."
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
    return result.data
