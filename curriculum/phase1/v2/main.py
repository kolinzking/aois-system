from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import litellm
import os
import json

load_dotenv()

litellm.drop_params = True  # ignore unsupported params per provider silently

SYSTEM_PROMPT = """
You are AOIS — AI Operations Intelligence System, an expert SRE.
Analyze infrastructure logs and classify incidents.

Severity levels:
P1 - Critical: production down, immediate action required
P2 - High: degraded, action within 1 hour
P3 - Medium: warning, action within 24 hours
P4 - Low: preventive, action within 1 week
"""

# Tool definition in OpenAI format — LiteLLM translates to each provider's format
ANALYZE_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_incident",
        "description": "Analyze a log and return structured incident data",
        "parameters": {
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
}

# Routing tiers — swap models here, zero code changes downstream
ROUTING_TIERS = {
    "premium": "anthropic/claude-opus-4-6",   # P1 incidents, deep reasoning
    "standard": "gpt-4o-mini",                # P2/P3, summarization, 10x cheaper
    "fast": "groq/llama-3.1-8b-instant",      # high-volume, sub-second latency
    "local": "ollama/mistral",                # air-gapped, zero cost
}

DEFAULT_TIER = "premium"


class LogInput(BaseModel):
    log: str
    tier: str = DEFAULT_TIER


class IncidentAnalysis(BaseModel):
    summary: str
    severity: str
    suggested_action: str
    confidence: float
    provider: str
    cost_usd: float


def analyze(log: str, tier: str) -> IncidentAnalysis:
    model = ROUTING_TIERS.get(tier, ROUTING_TIERS[DEFAULT_TIER])

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this log:\n\n{log}"}
        ],
        tools=[ANALYZE_TOOL],
        tool_choice={"type": "function", "function": {"name": "analyze_incident"}},
        max_tokens=1024,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    data = json.loads(tool_call.function.arguments)

    cost = litellm.completion_cost(completion_response=response)

    return IncidentAnalysis(
        **data,
        provider=model,
        cost_usd=round(cost, 6),
    )


app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok", "tiers": list(ROUTING_TIERS.keys())}


@app.post("/analyze", response_model=IncidentAnalysis)
def analyze_endpoint(data: LogInput):
    tier = data.tier if data.tier in ROUTING_TIERS else DEFAULT_TIER
    try:
        return analyze(data.log, tier)
    except Exception as e:
        if tier != "standard":
            try:
                return analyze(data.log, "standard")
            except Exception:
                pass
        raise HTTPException(status_code=503, detail=str(e))
