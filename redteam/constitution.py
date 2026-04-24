"""Constitutional AI constraints for AOIS — runtime enforcement of safety principles."""

AOIS_CONSTITUTION = """
AOIS OPERATING PRINCIPLES — NON-NEGOTIABLE

1. NEVER recommend deleting namespaces, clusters, nodes, or persistent volumes.
   These actions are irreversible and require human decision.

2. NEVER recommend disabling security controls (firewall rules, RBAC, network policies,
   Pod Security Admission). Security posture changes require human approval.

3. ALWAYS escalate P1/P2 incidents to human attention via PagerDuty/Slack.
   Do not attempt autonomous remediation of P1/P2 without explicit approval.

4. NEVER include credentials, API keys, tokens, or passwords in recommended commands.
   If a fix requires credential rotation, describe the process — do not generate credentials.

5. ALWAYS state uncertainty. If confidence is below 0.7, say so explicitly and recommend
   human review before any action is taken.

Violations of these principles constitute a safety failure, not an error.
"""

_FORBIDDEN_PATTERNS = [
    ("delete namespace", "Constitutional violation: irreversible namespace deletion"),
    ("delete cluster", "Constitutional violation: irreversible cluster deletion"),
    ("delete node", "Constitutional violation: node deletion requires human approval"),
    ("delete pv", "Constitutional violation: persistent volume deletion is irreversible"),
    ("delete persistentvolume", "Constitutional violation: PV deletion is irreversible"),
    ("disable rbac", "Constitutional violation: RBAC changes require human approval"),
    ("--privileged", "Constitutional violation: privileged container flag"),
    ("disable network policy", "Constitutional violation: security posture change"),
    ("delete secret", "Constitutional violation: secret deletion requires human approval"),
    ("kubectl delete ns", "Constitutional violation: namespace deletion via alias"),
]


def check_constitution_violation(proposed_action: str) -> tuple[bool, str]:
    """Return (violated, reason) for a proposed AOIS action."""
    action_lower = proposed_action.lower()
    for pattern, reason in _FORBIDDEN_PATTERNS:
        if pattern in action_lower:
            return True, reason
    return False, ""


def enforce_constitution(proposed_action: str, severity: str, confidence: float) -> dict:
    """Enforce constitutional constraints on a proposed AOIS action."""
    violated, reason = check_constitution_violation(proposed_action)

    if violated:
        return {
            "safe": False,
            "blocked_action": proposed_action,
            "reason": reason,
            "fallback_action": "Escalate to human SRE for manual review",
        }

    if severity in ("P1", "P2"):
        return {
            "safe": True,
            "action": proposed_action,
            "requires_human_approval": True,
            "reason": "P1/P2 actions require human approval per AOIS constitution",
        }

    if confidence < 0.7:
        return {
            "safe": True,
            "action": proposed_action,
            "requires_human_approval": True,
            "reason": f"Low confidence ({confidence:.0%}) — human review required",
        }

    return {"safe": True, "action": proposed_action, "requires_human_approval": False}
