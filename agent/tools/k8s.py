"""Kubernetes investigative tools, each protected by the @gated_tool decorator."""
import logging
import subprocess

from agent_gate.enforce import gated_tool

log = logging.getLogger("agent.tools.k8s")

KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"


def _kubectl(*args) -> str:
    cmd = ["sudo", "kubectl", "--kubeconfig", KUBECONFIG] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return f"kubectl error: {result.stderr.strip()}"
    return result.stdout.strip()


@gated_tool(agent_role="read_only")
async def get_pod_logs(namespace: str, pod_name: str, lines: int = 100,
                       container: str = "", session_id: str = "default") -> str:
    lines = min(lines, 500)
    if len(pod_name) > 40 and pod_name.count("-") >= 3:
        # full pod name with hash — use direct reference
        args = ["logs", "-n", namespace, pod_name, f"--tail={lines}"]
    else:
        args = ["logs", "-n", namespace, f"--selector=app={pod_name}", f"--tail={lines}"]
    if container:
        args += ["-c", container]
    return _kubectl(*args) or f"No logs found for {pod_name} in {namespace}"


@gated_tool(agent_role="read_only")
async def describe_node(node_name: str, session_id: str = "default") -> str:
    if node_name == "all":
        return _kubectl("get", "nodes", "-o", "wide")
    return _kubectl("describe", "node", node_name)


@gated_tool(agent_role="read_only")
async def list_events(namespace: str, resource_name: str = "",
                      limit: int = 20, session_id: str = "default") -> str:
    if resource_name:
        args = ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp",
                f"--field-selector=involvedObject.name={resource_name}"]
    else:
        args = ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]
    output = _kubectl(*args)
    return "\n".join(output.split("\n")[-limit:])


@gated_tool(agent_role="read_only")
async def get_metrics(namespace: str, resource_type: str = "pods",
                      session_id: str = "default") -> str:
    if resource_type == "nodes":
        return _kubectl("top", "nodes")
    return _kubectl("top", "pods", "-n", namespace)
