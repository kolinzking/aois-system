from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import anthropic

load_dotenv()

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
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
