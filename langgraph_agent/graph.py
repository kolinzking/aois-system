"""Assemble the AOIS SRE graph and compile it with Postgres checkpointing."""
import asyncpg
import logging
import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph_agent.state import InvestigationState
from langgraph_agent.nodes import (
    detect_node, investigate_node, hypothesize_node,
    verify_node, remediate_node, report_node,
)

log = logging.getLogger("langgraph_agent")


def build_graph() -> StateGraph:
    graph = StateGraph(InvestigationState)

    graph.add_node("detect",      detect_node)
    graph.add_node("investigate", investigate_node)
    graph.add_node("hypothesize", hypothesize_node)
    graph.add_node("verify",      verify_node)
    graph.add_node("remediate",   remediate_node)
    graph.add_node("report",      report_node)

    graph.set_entry_point("detect")
    graph.add_edge("detect",      "investigate")
    graph.add_edge("investigate", "hypothesize")
    graph.add_edge("hypothesize", "verify")
    graph.add_edge("verify",      "remediate")
    graph.add_edge("remediate",   "report")
    graph.add_edge("report",      END)

    return graph


async def run_investigation(incident: str, session_id: str,
                             agent_role: str = "read_only") -> dict:
    """
    Run the full AOIS SRE graph for an incident.
    Pauses before remediate for human approval.
    Checkpoints state to Postgres after each node.
    """
    graph = build_graph()

    async with await asyncpg.create_pool(os.getenv("DATABASE_URL")) as db:
        checkpointer = AsyncPostgresSaver(db)
        await checkpointer.setup()

        compiled = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["remediate"],
        )

        initial_state = InvestigationState(
            incident_description=incident,
            session_id=session_id,
            agent_role=agent_role,
            evidence=[],
            tool_calls=[],
            hypothesis="",
            severity="P3",
            verified=False,
            proposed_action="",
            human_approved=False,
            remediation_result="",
            report="",
            cost_usd=0.0,
            total_tokens=0,
        )

        config = {"configurable": {"thread_id": session_id}}
        log.info("Running graph to approval gate: %s", incident[:60])
        result = await compiled.ainvoke(initial_state, config=config)
        return result


async def approve_and_continue(session_id: str) -> dict:
    """
    Resume the graph after human approval.
    Updates human_approved=True and runs remediate → report.
    """
    graph = build_graph()
    async with await asyncpg.create_pool(os.getenv("DATABASE_URL")) as db:
        checkpointer = AsyncPostgresSaver(db)
        compiled = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["remediate"],
        )
        config = {"configurable": {"thread_id": session_id}}
        await compiled.aupdate_state(
            config,
            {"human_approved": True},
            as_node="verify",
        )
        result = await compiled.ainvoke(None, config=config)
        return result
