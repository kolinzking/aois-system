from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import anthropic

load_dotenv()

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """
You are AOIS — AI Operations Intelligence System, an expert SRE.
Analyze infrastructure logs and classify incidents.

Severity levels:
P1 - Critical: production down, immediate action required
P2 - High: degraded, action within 1 hour
P3 - Medium: warning, action within 24 hours
P4 - Low: preventive, action within 1 week
"""

ANALYZE_TOOL = {
    "name": "analyze_incident",
    "description": "Analyze a log and return structured incident data",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "suggested_action": {"type": "string"},
            "confidence": {"type": "number"}
        },
        "required": ["summary", "severity", "suggested_action", "confidence"]
    }
}

def analyze_with_claude(log: str) -> IncidentAnalysis:
    response = anthropic_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }
        ],
        tools=[ANALYZE_TOOL],
        tool_choice={"type": "tool", "name": "analyze_incident"},
        messages=[
            {"role": "user", "content": f"Analyze this log:\n\n{log}"}
        ]
    )
    for block in response.content:
        if block.type == "tool_use":
            return IncidentAnalysis(**block.input)
    raise ValueError("Claude did not return structured output")
class LogInput(BaseModel):
    log: str

class IncidentAnalysis(BaseModel):
    summary: str
    severity: str
    suggested_action: str
    confidence: float

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
