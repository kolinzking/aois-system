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
