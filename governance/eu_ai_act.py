"""EU AI Act compliance layer for AOIS — risk classification, audit trail, model card."""
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class RiskCategory(str, Enum):
    MINIMAL = "minimal"
    LIMITED = "limited"
    HIGH = "high"
    UNACCEPTABLE = "unacceptable"


class OversightLevel(str, Enum):
    NONE = "none"
    NOTIFICATION = "notification"
    APPROVAL_REQUIRED = "approval_required"
    HUMAN_IN_LOOP = "human_in_the_loop"


@dataclass
class AuditEntry:
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    incident: str = ""
    model: str = ""
    severity: str = ""
    proposed_action: str = ""
    human_reviewed: bool = False
    human_decision: str = ""
    final_action: str = ""
    confidence: float = 0.0
    risk_category: str = RiskCategory.HIGH
    oversight_level: str = OversightLevel.APPROVAL_REQUIRED


_MODE_RISK: dict[str, RiskCategory] = {
    "suggest_only": RiskCategory.LIMITED,
    "auto_triage": RiskCategory.LIMITED,
    "autonomous_remediation": RiskCategory.HIGH,
    "financial_infra": RiskCategory.HIGH,
    "healthcare_infra": RiskCategory.HIGH,
}


class EUAIActCompliance:
    """Compliance layer for EU AI Act High Risk classification."""

    def __init__(self, audit_log_path: str = "/var/aois/audit_log.jsonl"):
        self._audit_path = Path(audit_log_path)
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    def classify_risk(self, aois_mode: str) -> RiskCategory:
        return _MODE_RISK.get(aois_mode, RiskCategory.HIGH)

    def required_oversight(self, risk: RiskCategory, severity: str) -> OversightLevel:
        if risk == RiskCategory.HIGH:
            if severity in ("P1", "P2"):
                return OversightLevel.HUMAN_IN_LOOP
            return OversightLevel.APPROVAL_REQUIRED
        if risk == RiskCategory.LIMITED:
            return OversightLevel.NOTIFICATION
        return OversightLevel.NONE

    def log_decision(self, entry: AuditEntry) -> None:
        """Append an immutable audit entry to the compliance log."""
        with open(self._audit_path, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def compliance_check(
        self,
        proposed_action: str,
        severity: str,
        confidence: float,
        aois_mode: str = "autonomous_remediation",
    ) -> dict:
        """Full compliance check: risk classification + oversight level + constitutional check."""
        from redteam.constitution import enforce_constitution

        risk = self.classify_risk(aois_mode)
        oversight = self.required_oversight(risk, severity)
        constitution = enforce_constitution(proposed_action, severity, confidence)

        return {
            "risk_category": risk.value,
            "oversight_required": oversight.value,
            "constitutional_check": constitution,
            "compliant": constitution["safe"],
            "human_approval_required": oversight in (
                OversightLevel.APPROVAL_REQUIRED,
                OversightLevel.HUMAN_IN_LOOP,
            ),
        }

    def generate_model_card(self, output_path: str = "MODEL_CARD.md") -> str:
        """Generate an EU AI Act-compliant model card for AOIS."""
        card = """# AOIS Model Card

## System Information
- **System Name**: AOIS (AI Operations Intelligence System)
- **Version**: v34
- **Classification**: EU AI Act High-Risk AI System (autonomous infrastructure remediation)
- **Provider**: Collins (operator)
- **Contact**: gspice1@proton.me

## Intended Use
AOIS analyzes Kubernetes infrastructure logs and incidents. It classifies severity (P1-P4),
proposes remediation actions, and (with human approval) executes those actions via kubectl.

## Out-of-Scope Use
- Medical device control
- Financial trading decisions
- Decisions about individuals' access to essential services
- Any use without human oversight for P1/P2 incidents

## Training Data
AOIS does not train on incident data. It uses pre-trained LLMs (Claude Sonnet, Claude Haiku)
via the Anthropic API. No personal data is used for training.

## Performance Metrics
| Metric | Value | Measurement Method |
|---|---|---|
| Severity accuracy (P1-P4) | ≥90% | evals/golden_dataset.json — 20 labeled incidents |
| Hallucination rate | ≤5% | LLM-as-judge eval with Claude |
| Safety rate (no destructive action without approval) | 100% | Constitutional AI check in CI |
| P1 alert latency | <30s (99th percentile) | Prometheus SLO in v19 |

## Human Oversight
- **P1/P2 incidents**: Human-in-the-loop required before any action
- **P3/P4 incidents**: Human approval required before any write action
- **Read-only actions**: Automated (log retrieval, metric queries, kubectl get)
- **Kill switch**: Halts agent mid-execution, requires human restart

## Audit Trail (EU AI Act Article 12)
All AOIS decisions are logged to `/var/aois/audit_log.jsonl`:
- session_id, timestamp, incident description
- model used, severity classified, proposed action
- human_reviewed flag, human_decision (approved/rejected/modified)
- final_action taken, confidence score, risk classification

Logs retained for 36 months. Available on request from national market surveillance authority.

## Known Limitations
- Severity accuracy degrades on incident types absent from training distribution
- Edge/Ollama mode: 60-75% severity accuracy vs 90%+ for Claude API
- Vision analysis requires Sonnet or Opus (Haiku does not support vision)
- JSON compliance: Ollama 70-85% vs Claude 99%+

## EU AI Act Compliance Status
| Requirement | Article | Status |
|---|---|---|
| Risk classification documented | Art. 9 | ✅ High Risk — autonomous remediation |
| Audit trail | Art. 12 | ✅ /var/aois/audit_log.jsonl, 36 months |
| Human oversight | Art. 14 | ✅ Approval gate for all write actions |
| Transparency | Art. 13 | ✅ This model card |
| Accuracy monitoring | Art. 9 | ✅ evals/run_evals.py in CI |
| Post-market monitoring | Art. 72 | ✅ Langfuse + Prometheus metrics |
| Conformity assessment | Art. 43 | ⚠️ Self-assessment (not third-party) |
"""
        Path(output_path).write_text(card)
        return card

    def query_audit_log(self, session_id: str | None = None,
                         severity: str | None = None, limit: int = 100) -> list[dict]:
        """Query the audit log with optional filters."""
        if not self._audit_path.exists():
            return []

        entries = []
        for line in self._audit_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if session_id and entry.get("session_id") != session_id:
                    continue
                if severity and entry.get("severity") != severity:
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
            except json.JSONDecodeError:
                continue

        return entries
