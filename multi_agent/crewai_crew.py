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
