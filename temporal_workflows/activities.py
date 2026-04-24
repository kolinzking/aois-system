"""AOIS tool calls as Temporal activities — each is durable and retryable."""
from temporalio import activity

from agent.tools.k8s import describe_node, get_metrics, get_pod_logs, list_events
from agent.tools.rag_tool import search_past_incidents


@activity.defn(name="get_pod_logs_activity")
async def get_pod_logs_activity(namespace: str, pod_name: str,
                                 lines: int = 100, session_id: str = "default") -> str:
    activity.heartbeat("fetching pod logs")
    return await get_pod_logs(namespace=namespace, pod_name=pod_name,
                              lines=lines, session_id=session_id)


@activity.defn(name="describe_node_activity")
async def describe_node_activity(node_name: str, session_id: str = "default") -> str:
    activity.heartbeat("describing node")
    return await describe_node(node_name=node_name, session_id=session_id)


@activity.defn(name="list_events_activity")
async def list_events_activity(namespace: str, resource_name: str = "",
                                limit: int = 20, session_id: str = "default") -> str:
    activity.heartbeat("listing events")
    return await list_events(namespace=namespace, resource_name=resource_name,
                             limit=limit, session_id=session_id)


@activity.defn(name="get_metrics_activity")
async def get_metrics_activity(namespace: str, resource_type: str = "pods",
                                session_id: str = "default") -> str:
    activity.heartbeat("fetching metrics")
    return await get_metrics(namespace=namespace, resource_type=resource_type,
                             session_id=session_id)


@activity.defn(name="search_past_incidents_activity")
async def search_past_incidents_activity(query: str, session_id: str = "default") -> str:
    return await search_past_incidents(query=query, session_id=session_id)


@activity.defn(name="run_llm_step_activity")
async def run_llm_step_activity(messages: list[dict], system: str) -> dict:
    """Single Claude API call — activity so its result is persisted in Temporal history."""
    import anthropic
    import os
    from agent.tools.definitions import TOOL_DEFINITIONS

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    activity.heartbeat("calling Claude")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=system,
        tools=TOOL_DEFINITIONS,
        messages=messages,
    )
    return {
        "stop_reason": response.stop_reason,
        "content": [b.model_dump() for b in response.content],
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }
