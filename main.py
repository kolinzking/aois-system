from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
load_dotenv()
class LogInput(BaseModel):
    log: str

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
