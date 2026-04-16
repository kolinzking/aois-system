from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

class InputData(BaseModel):
    text: str

@app.post("/analyze")
def analyze(data: InputData):

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": data.text}
        ]
    )

    return {
        "analysis": response.choices[0].message.content
    }