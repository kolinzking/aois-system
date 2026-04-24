"""Tool definitions in Anthropic JSON schema format — passed to the Claude API."""

TOOL_DEFINITIONS = [
    {
        "name": "get_pod_logs",
        "description": (
            "Retrieve recent logs from a Kubernetes pod. Use this when you need to understand "
            "what a pod is doing, why it crashed, or what errors it is producing. "
            "Returns the last N lines of logs from the specified pod."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "pod_name": {"type": "string", "description": "Pod name or app label"},
                "lines": {"type": "integer", "description": "Log lines to retrieve (max 500)", "default": 100},
                "container": {"type": "string", "description": "Container name (optional)"},
            },
            "required": ["namespace", "pod_name"],
        },
    },
    {
        "name": "describe_node",
        "description": (
            "Get detailed information about a Kubernetes node including resource usage, "
            "conditions, and pod count. Use this to investigate node-level issues."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_name": {"type": "string", "description": "Node name, or 'all' to list all nodes"},
            },
            "required": ["node_name"],
        },
    },
    {
        "name": "list_events",
        "description": (
            "List recent Kubernetes events for a namespace or resource. "
            "Events show OOMKills, scheduling decisions, image pulls, and probe failures."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "resource_name": {"type": "string", "description": "Filter to a specific resource (optional)"},
                "limit": {"type": "integer", "description": "Max events to return", "default": 20},
            },
            "required": ["namespace"],
        },
    },
    {
        "name": "get_metrics",
        "description": (
            "Query current CPU and memory usage for pods or nodes. "
            "Use this to check whether a pod is approaching its resource limits."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query"},
                "resource_type": {"type": "string", "enum": ["pods", "nodes"]},
            },
            "required": ["namespace", "resource_type"],
        },
    },
    {
        "name": "search_past_incidents",
        "description": (
            "Search AOIS incident history for similar past incidents and their resolutions. "
            "Always call this early in any investigation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Description of the current incident"},
            },
            "required": ["query"],
        },
    },
]
