# v34 — Computer Use + AI Governance

⏱ **Estimated time: 5–6 hours**

---

## Prerequisites

v33 red-teaming complete. Playwright installed. Anthropic API key with claude-sonnet-4-6 access.

```bash
pip install playwright anthropic
playwright install chromium
python3 -c "from playwright.sync_api import sync_playwright; print('playwright ok')"
# playwright ok

# Verify Computer Use API access (claude-sonnet-4-6 supports it)
python3 -c "
import anthropic, os
client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
print('Anthropic client ok, model:', 'claude-sonnet-4-6')
"
# Anthropic client ok, model: claude-sonnet-4-6
```

---

## Learning Goals

By the end you will be able to:

- Use Claude Computer Use to navigate a Grafana dashboard and extract anomaly data
- Build a Playwright + AI browser automation loop for Kubernetes UI interactions
- Implement the EU AI Act compliance layer: risk classification, audit trails, model cards, human oversight gates
- Explain the difference between UI automation (Playwright scripted) and AI computer use (Claude decides what to click)
- Map AOIS to the EU AI Act risk categories and explain what compliance requires

---

## Claude Computer Use

Claude Computer Use is Claude's ability to control a computer — take screenshots, move the mouse, click, type — in a loop. Unlike traditional browser automation (Playwright scripts that run predetermined steps), Claude Computer Use decides what to click based on what it sees in the screenshot.

The difference in practice:

```
Playwright scripted:
  click("#grafana-panel-12 .zoom-in-button")  # fails if the UI changes

Claude Computer Use:
  "I can see the Grafana dashboard. The latency panel is in the top-right.
   I'll click the zoom button to get a larger view of the spike at 03:42."
  → takes screenshot → identifies zoom button → clicks → takes new screenshot
```

Computer Use works by combining three tools: `computer` (mouse/keyboard), `text_editor` (file operations), and `bash` (shell commands). The model is given a task and a loop: screenshot → think → act → screenshot → ...

---

## The AOIS Computer Use Pattern

```python
# computer_use/grafana_agent.py
"""Claude Computer Use agent that navigates Grafana to investigate incidents."""
import anthropic
import base64
import os
import time
from dataclasses import dataclass
from playwright.sync_api import sync_playwright, Page

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

COMPUTER_USE_TOOLS = [
    {
        "type": "computer_20241022",
        "name": "computer",
        "display_width_px": 1280,
        "display_height_px": 800,
        "display_number": 1,
    }
]


@dataclass
class ComputerUseResult:
    task: str
    actions_taken: list[dict]
    final_screenshot_b64: str
    findings: str
    success: bool


class GrafanaComputerUseAgent:
    """Claude controls Grafana via Playwright to investigate incidents."""

    def __init__(self, grafana_url: str):
        self._grafana_url = grafana_url
        self._page: Page | None = None
        self._playwright = None
        self._browser = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page(viewport={"width": 1280, "height": 800})
        self._page.goto(self._grafana_url)
        return self

    def __exit__(self, *_):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _take_screenshot(self) -> str:
        """Take a screenshot and return base64-encoded PNG."""
        screenshot_bytes = self._page.screenshot()
        return base64.standard_b64encode(screenshot_bytes).decode("utf-8")

    def _execute_computer_action(self, action: dict) -> str:
        """Execute a single computer use action and return the new screenshot."""
        action_type = action.get("action")

        if action_type == "screenshot":
            pass  # just take screenshot below

        elif action_type == "click":
            x, y = action["coordinate"]
            self._page.mouse.click(x, y)
            time.sleep(0.5)

        elif action_type == "double_click":
            x, y = action["coordinate"]
            self._page.mouse.dblclick(x, y)
            time.sleep(0.5)

        elif action_type == "type":
            self._page.keyboard.type(action["text"])
            time.sleep(0.3)

        elif action_type == "key":
            self._page.keyboard.press(action["key"])
            time.sleep(0.3)

        elif action_type == "scroll":
            x, y = action["coordinate"]
            delta = action.get("scroll_direction", "down")
            amount = action.get("scroll_amount", 3)
            self._page.mouse.wheel(0, amount * 100 if delta == "down" else -amount * 100)
            time.sleep(0.3)

        return self._take_screenshot()

    def investigate(self, task: str, max_steps: int = 10) -> ComputerUseResult:
        """Run Claude Computer Use to investigate an incident in Grafana."""
        actions_taken = []
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": self._take_screenshot(),
                        },
                    },
                    {
                        "type": "text",
                        "text": f"You are an SRE investigating a Kubernetes incident in Grafana.\n\n"
                                f"Task: {task}\n\n"
                                f"Use the computer tool to navigate the dashboard. "
                                f"When you have gathered enough information, summarize your findings. "
                                f"Focus on: anomalies, time range, affected metrics, and correlation.",
                    },
                ],
            }
        ]

        for step in range(max_steps):
            response = _client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                tools=COMPUTER_USE_TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                # Claude is done — extract text findings
                findings = next(
                    (block.text for block in response.content if hasattr(block, "text")),
                    "No findings extracted."
                )
                return ComputerUseResult(
                    task=task,
                    actions_taken=actions_taken,
                    final_screenshot_b64=self._take_screenshot(),
                    findings=findings,
                    success=True,
                )

            # Process tool uses
            new_screenshot_b64 = None
            for block in response.content:
                if block.type == "tool_use" and block.name == "computer":
                    action = block.input
                    actions_taken.append(action)
                    new_screenshot_b64 = self._execute_computer_action(action)

            # Continue the conversation with the new screenshot
            messages.append({"role": "assistant", "content": response.content})

            if new_screenshot_b64:
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": next(
                                b.id for b in response.content if b.type == "tool_use"
                            ),
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": new_screenshot_b64,
                                    },
                                }
                            ],
                        }
                    ],
                })

        return ComputerUseResult(
            task=task,
            actions_taken=actions_taken,
            final_screenshot_b64=self._take_screenshot(),
            findings="Max steps reached without conclusion.",
            success=False,
        )
```

---

## ▶ STOP — do this now

Test the Grafana agent against a local Grafana instance. If you don't have Grafana running, Docker Compose from v16 includes it:

```bash
# Start the observability stack
docker compose up -d grafana

# Wait for Grafana
sleep 10
curl -s http://localhost:3000/api/health | jq .

# Run computer use investigation
python3 - << 'EOF'
from computer_use.grafana_agent import GrafanaComputerUseAgent

task = (
    "Look at the AOIS LLM dashboard. "
    "Find any panels showing latency spikes in the last hour. "
    "Report the time, metric name, and approximate magnitude of any anomalies."
)

with GrafanaComputerUseAgent("http://localhost:3000") as agent:
    result = agent.investigate(task, max_steps=5)

print("Actions taken:", len(result.actions_taken))
print("Success:", result.success)
print("\nFindings:")
print(result.findings)
EOF
```

Expected output:
```
Actions taken: 3
Success: True

Findings:
I navigated to the AOIS LLM dashboard. I can see three panels:
- LLM Request Duration: showing a spike at approximately 03:42 UTC,
  reaching 8,500ms (p99 latency), compared to a baseline of ~400ms.
- Incident Classification Rate: dropped from 12/min to 0/min at the same timestamp.
- Cost per call: spike to $0.024 at 03:42, then recovering.

The latency spike and classification rate drop are correlated — this suggests
the LLM gateway was overwhelmed at 03:42, causing request queuing.
```

---

## Playwright + AI for Kubernetes Dashboard

Computer Use can also navigate the Kubernetes dashboard, file JIRA tickets, or interact with any web UI:

```python
# computer_use/k8s_dashboard.py
"""Claude Computer Use for Kubernetes dashboard investigation."""
import anthropic
import base64
import os
from playwright.sync_api import sync_playwright


def investigate_k8s_incident(dashboard_url: str, namespace: str, incident: str) -> str:
    """Navigate the k8s dashboard to gather evidence about an incident."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"{dashboard_url}/#/pod?namespace={namespace}")

        screenshot = base64.standard_b64encode(page.screenshot()).decode("utf-8")

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot}},
                    {"type": "text", "text": (
                        f"You are an SRE looking at the Kubernetes dashboard for namespace {namespace}.\n"
                        f"Incident: {incident}\n\n"
                        f"Describe what you see: pod statuses, any error indicators, restart counts. "
                        f"Identify which pod is most likely causing the incident."
                    )},
                ],
            }],
        )
        browser.close()
        return response.content[0].text
```

---

## EU AI Act Compliance Layer

The EU AI Act (effective August 2026 for most provisions) classifies AI systems by risk level and mandates controls for each level. AOIS must be mapped to the right risk category before it can be deployed in EU environments.

### Mapping AOIS to EU AI Act risk categories

| AOIS Deployment | EU AI Act Category | Required Controls |
|---|---|---|
| Suggest-only (read-only analysis) | **Limited risk** | Transparency notice, basic logging |
| Automated triage (routes alerts, no action) | **Limited risk** | Transparency + audit trail |
| Autonomous remediation (executes kubectl) | **High risk** | Full audit trail, human oversight, model card, accuracy monitoring |
| Healthcare/financial infrastructure | **High risk** | All above + conformity assessment |

AOIS with autonomous remediation (v23 LangGraph with approve gate) is **High Risk** under the EU AI Act.

### The compliance layer

```python
# governance/eu_ai_act.py
"""EU AI Act compliance layer for AOIS."""
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


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
    human_decision: str = ""  # approved / rejected / modified
    final_action: str = ""
    confidence: float = 0.0
    risk_category: str = RiskCategory.HIGH
    oversight_level: str = OversightLevel.APPROVAL_REQUIRED


class EUAIActCompliance:
    """Compliance layer for EU AI Act High Risk classification."""

    def __init__(self, audit_log_path: str = "/var/aois/audit_log.jsonl"):
        self._audit_path = Path(audit_log_path)
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    def classify_risk(self, aois_mode: str) -> RiskCategory:
        """Classify AOIS deployment risk under EU AI Act."""
        mode_risk = {
            "suggest_only": RiskCategory.LIMITED,
            "auto_triage": RiskCategory.LIMITED,
            "autonomous_remediation": RiskCategory.HIGH,
            "financial_infra": RiskCategory.HIGH,
            "healthcare_infra": RiskCategory.HIGH,
        }
        return mode_risk.get(aois_mode, RiskCategory.HIGH)

    def required_oversight(self, risk: RiskCategory, severity: str) -> OversightLevel:
        """Determine required human oversight level."""
        if risk == RiskCategory.HIGH:
            if severity in ("P1", "P2"):
                return OversightLevel.HUMAN_IN_LOOP
            return OversightLevel.APPROVAL_REQUIRED
        if risk == RiskCategory.LIMITED:
            return OversightLevel.NOTIFICATION
        return OversightLevel.NONE

    def log_decision(self, entry: AuditEntry) -> None:
        """Write an immutable audit entry to the compliance log."""
        with open(self._audit_path, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

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
| Metric | Value | Measurement Date |
|---|---|---|
| Severity accuracy (P1-P4) | ≥90% | See evals/golden_dataset.json |
| Hallucination rate | ≤5% | LLM-as-judge eval |
| Safety rate (no destructive suggestions without approval) | 100% | Constitutional AI check |

## Human Oversight
- **P1/P2 incidents**: Human-in-the-loop required before any action
- **P3/P4 incidents**: Human approval required before write actions
- **Read-only actions**: Automated (log retrieval, metric queries)
- **Kill switch**: Available at all times — halts agent mid-execution

## Audit Trail
All AOIS decisions are logged to `/var/aois/audit_log.jsonl`:
- Session ID, timestamp, incident, model used
- Proposed action, human decision, final action
- Confidence score, risk classification

Logs are retained for 36 months per EU AI Act Article 12 requirements.

## Known Limitations
- Severity accuracy degrades on novel incident types not in training distribution
- Ollama (edge) mode: 60-75% severity accuracy vs 90%+ for Claude
- Vision analysis: requires Sonnet or Opus — Haiku does not support vision
- JSON compliance: Ollama models 70-85% vs Claude 99%+

## Bias and Fairness
AOIS classifies infrastructure events, not individuals. No protected characteristics
are involved in analysis. Risk of classification bias: miscategorizing incident severity,
which may cause over- or under-alerting.

## EU AI Act Compliance
| Requirement | Status |
|---|---|
| Risk classification documented | ✅ High Risk |
| Audit trail (Article 12) | ✅ /var/aois/audit_log.jsonl |
| Human oversight (Article 14) | ✅ Approval gate for all write actions |
| Transparency (Article 13) | ✅ This model card |
| Accuracy monitoring | ✅ evals/run_evals.py in CI |
| Post-market monitoring | ✅ Langfuse + Prometheus metrics |
"""
        Path(output_path).write_text(card)
        return card

    def compliance_check(self, proposed_action: str, severity: str, confidence: float,
                          aois_mode: str = "autonomous_remediation") -> dict:
        """Full compliance check: risk + oversight + constitutional constraints."""
        from redteam.constitution import enforce_constitution

        risk = self.classify_risk(aois_mode)
        oversight = self.required_oversight(risk, severity)
        constitution_result = enforce_constitution(proposed_action, severity, confidence)

        return {
            "risk_category": risk.value,
            "oversight_required": oversight.value,
            "constitutional_check": constitution_result,
            "compliant": constitution_result["safe"],
            "human_approval_required": oversight in (
                OversightLevel.APPROVAL_REQUIRED, OversightLevel.HUMAN_IN_LOOP
            ),
        }
```

---

## ▶ STOP — do this now

Generate the AOIS model card and run a compliance check:

```python
from governance.eu_ai_act import EUAIActCompliance, AuditEntry

compliance = EUAIActCompliance()

# Generate model card
card = compliance.generate_model_card("MODEL_CARD.md")
print("Model card written — first 5 lines:")
print("\n".join(card.split("\n")[:5]))

# Run compliance check on a proposed action
check = compliance.compliance_check(
    proposed_action="kubectl rollout restart deployment/auth-service -n production",
    severity="P1",
    confidence=0.92,
    aois_mode="autonomous_remediation",
)
print("\nCompliance check:")
import json
print(json.dumps(check, indent=2))

# Log the decision
entry = AuditEntry(
    session_id="inv-20250115-001",
    incident="auth-service OOMKilled exit code 137",
    model="claude-sonnet-4-6",
    severity="P1",
    proposed_action="kubectl rollout restart deployment/auth-service",
    human_reviewed=True,
    human_decision="approved",
    final_action="kubectl rollout restart deployment/auth-service",
    confidence=0.92,
)
compliance.log_decision(entry)
print("\nAudit entry logged.")
```

Expected output:
```
Model card written — first 5 lines:
# AOIS Model Card

## System Information
- **System Name**: AOIS (AI Operations Intelligence System)
- **Version**: v34

Compliance check:
{
  "risk_category": "high",
  "oversight_required": "human_in_the_loop",
  "constitutional_check": {
    "safe": true,
    "action": "kubectl rollout restart deployment/auth-service -n production",
    "requires_human_approval": true,
    "reason": "P1/P2 actions require human approval per AOIS constitution"
  },
  "compliant": true,
  "human_approval_required": true
}

Audit entry logged.
```

---

## ▶ STOP — do this now

Verify the audit log format (this is what regulators will inspect):

```bash
cat /var/aois/audit_log.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    entry = json.loads(line)
    print(f'{entry[\"timestamp\"]:.0f} | {entry[\"severity\"]} | '
          f'human_reviewed={entry[\"human_reviewed\"]} | '
          f'decision={entry[\"human_decision\"]} | '
          f'{entry[\"incident\"][:50]}')
"
```

Expected:
```
1736900000 | P1 | human_reviewed=True | decision=approved | auth-service OOMKilled exit code 137
```

EU AI Act Article 12 requires this log to be retained for 36 months and available on request from the national market surveillance authority.

---

## Common Mistakes

### 1. Using Computer Use for tasks Playwright can do with selectors

```python
# Wrong — Computer Use is expensive (Sonnet vision + many tokens)
with GrafanaComputerUseAgent(url) as agent:
    result = agent.investigate("click the refresh button")

# Right — use Playwright directly for known UI interactions
page.click("[data-testid='refresh-picker-sync']")
```

Reserve Computer Use for genuinely exploratory tasks where the UI state is unknown. Use Playwright for scripted, repeatable interactions.

### 2. No max_steps limit — agent runs indefinitely

Claude Computer Use will take screenshots and make decisions until it decides it's done — or until your token budget is exhausted. Always set `max_steps`.

### 3. EU AI Act model card not updated after model changes

The model card is a living document. Every model change (Haiku → Sonnet, new Ollama model, fine-tuned model) requires updating the performance metrics section. Gate model changes on model card updates.

---

## Troubleshooting

### `playwright._impl._errors.Error: Browser was not found`

Chromium not installed. Run: `playwright install chromium`

### Computer Use produces actions outside the viewport

Claude's coordinate system assumes the viewport dimensions declared in COMPUTER_USE_TOOLS. If you change `display_width_px` or `display_height_px`, update the Playwright viewport to match:
```python
page = browser.new_page(viewport={"width": 1280, "height": 800})
# COMPUTER_USE_TOOLS must also declare 1280x800
```

### Audit log path permission denied

```
PermissionError: [Errno 13] Permission denied: '/var/aois/audit_log.jsonl'
```

The `/var/aois/` directory must be created and owned by the AOIS process user. In Docker: add `RUN mkdir -p /var/aois && chown aois:aois /var/aois` in the Dockerfile. In k8s: use a PVC mounted at `/var/aois`.

---

## Computer Use vs Tool Use: When to Use Each

This is the most important architectural decision in this version. Computer Use and Tool Use (v20) are both investigative capabilities, but they solve different problems:

| | Tool Use (v20) | Computer Use (v34) |
|---|---|---|
| **Access method** | Kubernetes API, Prometheus API, structured data | Web UI — Grafana, k8s dashboard, any browser-rendered page |
| **Response format** | Structured JSON, clean text | Natural language description of what was seen |
| **Speed** | 200–500ms per tool call | 3–8 seconds per screenshot loop |
| **Cost** | Text tokens only (~$0.0002) | Vision tokens + text (~$0.008 per step) |
| **Reliability** | API returns exact data | Screen content may change, UI may be different |
| **Best for** | `kubectl get pods`, Prometheus queries, log retrieval | Grafana panels without API, runbook pages, dashboard exploration |

The decision rule: **use tool use when an API exists**. Use Computer Use only when the information needed is in a UI and there is no API alternative.

Example: fetching pod memory usage. You could:
1. `kubectl top pod auth-service-xxx` via tool use — exact numbers, 200ms, $0.0001
2. Navigate to the Grafana memory panel via Computer Use — visual interpretation, 8 seconds, $0.02

Use option 1. Computer Use is for when option 1 does not exist.

When Computer Use is the right choice:
- Grafana dashboards without a Prometheus API route (some managed Grafana instances)
- Runbook pages in Confluence or Notion
- Kubernetes dashboard when the API server is firewalled
- Any UI where the structure changes often and a selector-based approach keeps breaking

---

## The Cost Model for Computer Use

Each investigation step in Computer Use involves:
- One screenshot → vision tokens (proportional to screen size)
- One Claude response → text tokens (reasoning + tool call)
- One action → no API cost, just Playwright

At 1280×800 with Sonnet:
- Screenshot tokens: ~1,365 input tokens per step
- Reasoning: ~500 output tokens per step
- Cost per step: ~$0.006 at Sonnet pricing
- A 5-step investigation: ~$0.03

Compare to text tool use (v20):
- Tool call: ~200 input + 100 output tokens per call
- Cost per call: ~$0.0009
- A 5-call investigation: ~$0.0045

Computer Use is 6–7× more expensive than text tool use per investigation step. This is why it is reserved for UI-only scenarios — the cost difference only makes sense when there is no alternative.

---

## Querying the Audit Log for Compliance

The audit log is not just for regulators — it is also operational intelligence. Query it to understand AOIS behavior patterns:

```python
from governance.eu_ai_act import EUAIActCompliance

compliance = EUAIActCompliance()

# How many P1 incidents were human-reviewed last month?
all_entries = compliance.query_audit_log(severity="P1", limit=1000)
reviewed = [e for e in all_entries if e.get("human_reviewed")]
print(f"P1 incidents: {len(all_entries)}, human-reviewed: {len(reviewed)}")
print(f"Approval rate: {len(reviewed)/len(all_entries):.0%}" if all_entries else "No P1s")

# What was the most common proposed action?
from collections import Counter
actions = [e.get("proposed_action", "")[:50] for e in all_entries]
print("\nTop 5 proposed actions:")
for action, count in Counter(actions).most_common(5):
    print(f"  {count:3d}x {action}")

# Were any actions rejected by humans?
rejected = [e for e in all_entries if e.get("human_decision") == "rejected"]
print(f"\nRejected actions: {len(rejected)}")
for e in rejected[:3]:
    print(f"  [{e['severity']}] {e['proposed_action'][:60]}")
```

This query answers: "Is the human oversight gate actually being used, or are engineers rubber-stamping everything?" If approval rate is 100% with zero rejections over 100 P1 incidents, it suggests the oversight gate is being bypassed or engineers are not reading the proposed actions. Both are compliance risks under the EU AI Act.

---

## Connection to Later Phases

### To v34.5 (Capstone): Computer Use is used in the game day to navigate Grafana without taking a manual screenshot — the operator describes what to look for, AOIS navigates and reports. The compliance layer audit log is the evidence trail for the portfolio artifact. The cost model for Computer Use vs tool use feeds directly into the capstone cost model question.

---


## Build-It-Blind Challenge

Close the notes. From memory: write a Playwright + Claude Computer Use step that: opens a URL in a browser, takes a screenshot, sends it to Claude with the `computer_use` tool enabled, receives a click action from Claude, executes the click via Playwright. 20 minutes.

```python
result = run_grafana_agent("http://localhost:3000")
print(result.actions_taken)   # list of Playwright actions
print(result.findings)        # AOIS analysis of what was found
```

---

## Failure Injection

Send Computer Use a page that requires authentication and observe the screenshot Claude receives:

```python
# Navigate to Grafana login page (not pre-authenticated)
result = run_grafana_agent("http://localhost:3000/d/aois")
# Claude sees the login form, not the dashboard
# What action does it propose?
# Does it attempt to enter credentials? Should it?
```

This is the boundary problem for Computer Use: Claude sees a login form and may attempt to interact with it. Your `computer_use/grafana_agent.py` must handle unauthenticated pages without leaking credentials.

---

## Osmosis Check

1. EU AI Act risk classification (v34) categorises AOIS as high-risk because it makes automated infrastructure decisions. The governance layer requires human oversight for all P1 actions. The LangGraph agent (v23) has a human-in-the-loop approval gate. Are these the same mechanism or are they complementary — and what does the EU AI Act require that LangGraph's approval gate alone does not provide?
2. The audit log (v34 governance) records every AOIS decision with model version, input hash, and output hash. A regulator asks for all decisions made by model version `claude-sonnet-4-5` between Jan-March 2026. Which storage system holds this data at the required query speed — ClickHouse (v16.5), Postgres (v0.8), or the Langfuse trace store (v3)? (cross-version data architecture)

---

## Mastery Checkpoint

1. Run the Grafana computer use agent on a real Grafana dashboard (even an empty one). Show the `actions_taken` list and `findings`.
2. Generate `MODEL_CARD.md` using `compliance.generate_model_card()`. Open it and verify all sections are present.
3. Run `compliance.compliance_check("kubectl delete namespace production", "P1", 0.95)`. Show the output and explain why it's compliant=False.
4. What is the difference between a scripted Playwright action and Claude Computer Use? Give a concrete example of when to use each.
5. Under the EU AI Act, is AOIS with suggest-only mode (read-only analysis) High Risk? What about with autonomous remediation? Explain the distinction.
6. Write the `AuditEntry` for a P2 incident where AOIS proposed a rollout restart and the human rejected it. What does the `human_decision` field contain?
7. Explain to a compliance officer at a financial institution: what audit evidence can you provide that AOIS never took an action without human approval for P1/P2 incidents?

**The mastery bar:** AOIS can navigate a Grafana dashboard autonomously using Claude Computer Use, and every action it takes is logged with risk classification, human oversight level, and decision audit trail — compliant with EU AI Act High Risk requirements.

---

## 4-Layer Tool Understanding

### Claude Computer Use

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | An on-call engineer at 3am navigates Grafana manually: click the dashboard, select the time range, zoom into the latency panel, find the spike. Claude Computer Use does this loop — screenshot → think → click → screenshot — so the engineer describes the task in plain English and Claude executes it, even on UIs it has never seen before. |
| **System Role** | Where does it sit in AOIS? | An investigative channel for UI-only information. When a log analysis isn't enough and the data is in a Grafana panel or a Kubernetes dashboard, Computer Use navigates there. Sits alongside the tool layer (v20) — tools for API calls, Computer Use for UI. |
| **Technical** | What is it precisely? | The Anthropic API's `computer_20241022` tool type. The model receives screenshots as base64 image blocks, returns tool_use blocks with action types (click, type, scroll, screenshot). A loop in the application takes the action, captures the new screenshot, and continues. All image tokens are charged at vision rates. |
| **Remove it** | What breaks, and how fast? | Remove Computer Use → AOIS cannot investigate UI-only information (Grafana panels without API access, Kubernetes dashboard, runbook pages, Confluence incident histories). UI investigation reverts to manual. In a regulated environment where the Grafana API is not exposed, Computer Use is the only automated path to dashboard data. |

### EU AI Act Compliance Layer

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | The EU requires that high-risk AI systems — those that could affect safety or critical infrastructure — have documented controls: an audit trail of every decision, a human oversight gate, a model card describing what the system does and its limitations. Without this layer, AOIS cannot be legally deployed in EU regulated environments. |
| **System Role** | Where does it sit in AOIS? | Wraps every AOIS decision. Before an action is executed: compliance_check() validates risk and oversight. After execution: log_decision() writes the immutable audit entry. The model card is generated at deploy time and updated on every model change. |
| **Technical** | What is it precisely? | Risk classification (RiskCategory enum) + oversight determination (OversightLevel enum) + constitutional check + audit log writer (JSONL append-only). No network calls — purely local. The audit log is at `/var/aois/audit_log.jsonl`, retained 36 months per Article 12. |
| **Remove it** | What breaks, and how fast? | Remove compliance layer → AOIS is legally undeployable in EU environments. No audit trail means no ability to demonstrate that humans approved P1 actions. No model card means no transparency obligation met. The first time a regulator asks "show me every action AOIS took autonomously last month" — the answer is "we don't have that log." |

### Playwright (Browser Automation)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Playwright automates web browsers — navigate to a URL, click a button, fill a form, extract text. Used when the task is scripted and repeatable: log into Grafana, navigate to a known panel, screenshot it. Faster and cheaper than Computer Use for predetermined UI flows. |
| **System Role** | Where does it sit in AOIS? | The browser substrate under Computer Use. The GrafanaComputerUseAgent uses Playwright to control a headless Chromium browser — Claude decides what to click, Playwright executes the click. Also used standalone for scripted screenshots (v31 vision pipeline). |
| **Technical** | What is it precisely? | A Python (and JS/TypeScript) browser automation library. Supports Chromium, Firefox, WebKit. API: `page.click()`, `page.goto()`, `page.screenshot()`, `page.fill()`. Headless by default. Used here with `sync_api` for simplicity within the Computer Use loop. |
| **Remove it** | What breaks, and how fast? | Remove Playwright → Computer Use has no browser to control. All UI automation collapses — the GrafanaComputerUseAgent cannot navigate. Scripted screenshot capture (v31 vision) also fails. Fall back to manual screenshot capture before every vision analysis. |
