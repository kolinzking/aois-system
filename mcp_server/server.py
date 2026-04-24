"""
AOIS MCP server — exposes investigative tools to any MCP-compatible client.
Run with stdio transport: python3 -m mcp_server.server
"""
import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from agent.investigator import investigate
from agent.tools.k8s import describe_node, get_metrics, get_pod_logs, list_events
from agent.tools.rag_tool import search_past_incidents

log = logging.getLogger("mcp_server")

_MCP_SESSION = "mcp-default"
server = Server("aois-mcp-server")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_pod_logs",
            description="Retrieve recent logs from a Kubernetes pod in the AOIS cluster",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "pod_name": {"type": "string"},
                    "lines": {"type": "integer", "default": 100},
                },
                "required": ["namespace", "pod_name"],
            },
        ),
        Tool(
            name="describe_node",
            description="Get resource usage and conditions for a Kubernetes node",
            inputSchema={
                "type": "object",
                "properties": {"node_name": {"type": "string"}},
                "required": ["node_name"],
            },
        ),
        Tool(
            name="list_events",
            description="List recent Kubernetes events for a namespace",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "resource_name": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["namespace"],
            },
        ),
        Tool(
            name="get_metrics",
            description="Query current CPU and memory usage for pods or nodes",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "resource_type": {"type": "string", "enum": ["pods", "nodes"]},
                },
                "required": ["namespace", "resource_type"],
            },
        ),
        Tool(
            name="search_past_incidents",
            description="Search AOIS incident history for similar past incidents",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="investigate_incident",
            description="Run a full autonomous AOIS investigation on an incident description",
            inputSchema={
                "type": "object",
                "properties": {
                    "incident_description": {"type": "string"},
                    "agent_role": {
                        "type": "string",
                        "enum": ["read_only", "analyst"],
                        "default": "read_only",
                    },
                },
                "required": ["incident_description"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        sid = _MCP_SESSION
        if name == "get_pod_logs":
            result = await get_pod_logs(session_id=sid, **arguments)
        elif name == "describe_node":
            result = await describe_node(session_id=sid, **arguments)
        elif name == "list_events":
            result = await list_events(session_id=sid, **arguments)
        elif name == "get_metrics":
            result = await get_metrics(session_id=sid, **arguments)
        elif name == "search_past_incidents":
            result = await search_past_incidents(session_id=sid, **arguments)
        elif name == "investigate_incident":
            inv = await investigate(
                arguments["incident_description"],
                agent_role=arguments.get("agent_role", "read_only"),
                session_id=sid,
            )
            result = json.dumps(inv, indent=2)
        else:
            result = f"Unknown tool: {name}"
    except Exception as e:
        result = f"Error: {e}"
        log.error("MCP tool error %s: %s", name, e)

    return [TextContent(type="text", text=str(result))]


async def run_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="aois",
                server_version="21.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_stdio())
