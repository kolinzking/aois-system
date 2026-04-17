from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Literal
import instructor
import litellm
import os

load_dotenv()

litellm.drop_params = True

# Langfuse — if keys are in .env, every LiteLLM call is traced automatically
if os.getenv("LANGFUSE_SECRET_KEY"):
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]

SYSTEM_PROMPT = """
You are AOIS — AI Operations Intelligence System, an expert SRE.
Analyze infrastructure logs and classify incidents.

Severity levels:
P1 - Critical: production down, immediate action required
P2 - High: degraded, action within 1 hour
P3 - Medium: warning, action within 24 hours
P4 - Low: preventive, action within 1 week
"""

ROUTING_TIERS = {
    "premium": "anthropic/claude-opus-4-6",
    "standard": "gpt-4o-mini",
    "fast": "groq/llama-3.1-8b-instant",
    "local": "ollama/mistral",
}

DEFAULT_TIER = "premium"


class LogInput(BaseModel):
    log: str
    tier: str = DEFAULT_TIER


# Instructor reads this model and builds the tool definition automatically
# Field descriptions guide the LLM. Constraints (ge, le, Literal) are enforced by Pydantic.
# If the LLM returns anything invalid, Instructor retries with the error fed back to the model.
class IncidentAnalysis(BaseModel):
    summary: str = Field(description="Concise description of what happened and why it matters")
    severity: Literal["P1", "P2", "P3", "P4"] = Field(description="Incident severity level")
    suggested_action: str = Field(description="Specific remediation steps for the on-call engineer")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    provider: str = Field(default="")
    cost_usd: float = Field(default=0.0)


# Instructor wraps LiteLLM — one line, adds validation + retry on top of all routing tiers
client = instructor.from_litellm(litellm.completion)


def analyze(log: str, tier: str) -> IncidentAnalysis:
    model = ROUTING_TIERS.get(tier, ROUTING_TIERS[DEFAULT_TIER])

    result, completion = client.chat.completions.create_with_completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this log:\n\n{log}"}
        ],
        response_model=IncidentAnalysis,
        max_retries=2,
        max_tokens=1024,
    )

    result.provider = model
    result.cost_usd = round(litellm.completion_cost(completion_response=completion), 6)
    return result


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
