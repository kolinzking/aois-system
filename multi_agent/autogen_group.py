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
    Agents challenge each other until they reach consensus or max_round.
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
        human_input_mode="NEVER",
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

    messages = groupchat.messages
    for msg in reversed(messages):
        if "FINAL RECOMMENDATION:" in msg.get("content", ""):
            return msg["content"]

    for msg in reversed(messages):
        if msg.get("name") == "SRE_Analyst":
            return msg["content"]

    return "No consensus reached"
