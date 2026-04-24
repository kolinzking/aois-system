"""Run all three frameworks against the same incident and compare outputs."""
import asyncio
import time
from multi_agent.crewai_crew import run_crew
from multi_agent.autogen_group import run_autogen_analysis
from multi_agent.pydantic_agent import analyze_incident, AoisDeps


async def compare(incident: str):
    print(f"Incident: {incident}\n")
    print("=" * 60)

    t0 = time.perf_counter()
    crewai_result = run_crew(incident)
    crewai_time = time.perf_counter() - t0
    print(f"CrewAI ({crewai_time:.1f}s):")
    print(crewai_result[:400])
    print()

    t0 = time.perf_counter()
    autogen_result = run_autogen_analysis(incident)
    autogen_time = time.perf_counter() - t0
    print(f"AutoGen ({autogen_time:.1f}s):")
    print(autogen_result[:400])
    print()

    t0 = time.perf_counter()
    deps = AoisDeps(
        incident_history_summary="No prior incidents found",
        cluster_name="hetzner-k3s-prod",
    )
    pydantic_result = await analyze_incident(incident, deps)
    pydantic_time = time.perf_counter() - t0
    print(f"Pydantic AI ({pydantic_time:.1f}s):")
    print(f"  severity={pydantic_result.severity}")
    print(f"  root_cause={pydantic_result.root_cause[:200]}")
    print(f"  action={pydantic_result.proposed_action[:200]}")
    print(f"  confidence={pydantic_result.confidence:.0%}")
    print(f"  human_approval={pydantic_result.requires_human_approval}")

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  CrewAI:      {crewai_time:.1f}s — role-based, sequential, narrative output")
    print(f"  AutoGen:     {autogen_time:.1f}s — conversation-based, agents challenge each other")
    print(f"  Pydantic AI: {pydantic_time:.1f}s — type-safe, validated structured output")


if __name__ == "__main__":
    asyncio.run(compare(
        "auth-service pod OOMKilled exit code 137 — memory limit 256Mi, third time this week"
    ))
