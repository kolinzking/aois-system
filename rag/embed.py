import os
import openai

_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_MODEL = "text-embedding-3-small"


def embed(text: str) -> list[float]:
    response = _client.embeddings.create(model=_MODEL, input=text)
    return response.data[0].embedding


def embed_many(texts: list[str]) -> list[list[float]]:
    response = _client.embeddings.create(model=_MODEL, input=texts)
    return [item.embedding for item in response.data]
