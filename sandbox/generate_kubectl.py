"""
Generate a kubectl command from a natural language proposed action.
The command is then validated in E2B before being presented for human approval.
"""
import anthropic
import logging
import os

log = logging.getLogger("sandbox.generate_kubectl")
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def generate_kubectl_patch(proposed_action: str, namespace: str = "default") -> str:
    """
    Ask Claude to generate a specific kubectl command from a natural language action.
    Returns a kubectl command string suitable for dry-run validation, or "" if unsafe.
    """
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"Convert this SRE action to a single kubectl command:\n"
                f"Action: {proposed_action}\n"
                f"Namespace: {namespace}\n\n"
                f"Rules:\n"
                f"- Return ONLY the kubectl command, no explanation\n"
                f"- Do NOT include --dry-run (the caller adds this)\n"
                f"- Never use delete, drain, cordon without explicit instruction\n"
                f"- Prefer 'kubectl set resources' or 'kubectl patch' over editing manifests\n"
                f"- If the action cannot be expressed as a safe kubectl command, return: CANNOT_GENERATE"
            ),
        }],
    )
    text = response.content[0].text.strip()

    if "CANNOT_GENERATE" in text or not text.startswith("kubectl"):
        log.info("Cannot generate safe kubectl command for: %s", proposed_action[:80])
        return ""

    first_line = text.split("\n")[0].strip()
    return first_line if first_line.startswith("kubectl") else ""
