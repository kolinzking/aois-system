package aois.agent

default allow = false

read_only_tools := {
    "get_pod_logs",
    "describe_node",
    "list_events",
    "get_metrics",
    "search_past_incidents",
    "describe_deployment",
    "get_pod_status",
}

analyst_tools := read_only_tools | {
    "write_incident_report",
    "create_jira_ticket",
    "post_slack_message",
}

operator_tools := analyst_tools | {
    "scale_deployment",
    "restart_pod",
    "update_configmap",
    "patch_resource_limits",
}

blocked_tools := {
    "delete_namespace",
    "delete_cluster",
    "delete_persistent_volume",
    "exec_arbitrary_command",
    "modify_rbac",
    "access_secret_store",
}

allow {
    not input.tool_name in blocked_tools
    input.agent_role == "read_only"
    input.tool_name in read_only_tools
}

allow {
    not input.tool_name in blocked_tools
    input.agent_role == "analyst"
    input.tool_name in analyst_tools
}

allow {
    not input.tool_name in blocked_tools
    input.agent_role == "operator"
    input.tool_name in operator_tools
    not requires_approval(input.tool_name)
}

allow {
    not input.tool_name in blocked_tools
    input.agent_role == "operator"
    input.tool_name in operator_tools
    requires_approval(input.tool_name)
    input.human_approved == true
}

requires_approval(tool) {
    tool in {"scale_deployment", "restart_pod", "update_configmap", "patch_resource_limits"}
}

reason = msg {
    allow
    msg := "allowed"
}

reason = msg {
    not allow
    input.tool_name in blocked_tools
    msg := sprintf("tool '%v' is permanently blocked — no role may invoke it", [input.tool_name])
}

reason = msg {
    not allow
    not input.tool_name in blocked_tools
    input.agent_role == "operator"
    requires_approval(input.tool_name)
    not input.human_approved
    msg := sprintf("tool '%v' requires human_approved=true for operator role", [input.tool_name])
}

reason = msg {
    not allow
    not input.tool_name in blocked_tools
    msg := sprintf("tool '%v' is not in the allowed set for role '%v'", [input.tool_name, input.agent_role])
}
