"""Shared state for the AOIS SRE graph."""
from typing import TypedDict, Annotated
import operator


class InvestigationState(TypedDict):
    # Input
    incident_description: str
    session_id: str
    agent_role: str

    # Investigation outputs (accumulated)
    evidence: Annotated[list[str], operator.add]
    tool_calls: Annotated[list[dict], operator.add]

    # Reasoning outputs
    hypothesis: str
    severity: str
    verified: bool

    # Remediation
    proposed_action: str
    human_approved: bool
    remediation_result: str

    # Final
    report: str
    cost_usd: float
    total_tokens: int
