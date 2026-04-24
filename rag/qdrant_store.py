import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchValue,
    PointStruct, VectorParams,
)

from .embed import embed

_client = QdrantClient(host="localhost", port=6333)
_COLLECTION = "aois_incidents"
_VECTOR_SIZE = 1536


def ensure_collection() -> None:
    existing = [c.name for c in _client.get_collections().collections]
    if _COLLECTION not in existing:
        _client.create_collection(
            collection_name=_COLLECTION,
            vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
        )


def index_incident_qdrant(incident_id: str, log_text: str, severity: str,
                           resolution: str = "", root_cause: str = "") -> None:
    ensure_collection()
    vector = embed(f"{log_text} {resolution} {root_cause}".strip())
    _client.upsert(
        collection_name=_COLLECTION,
        points=[PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, incident_id)),
            vector=vector,
            payload={
                "incident_id": incident_id,
                "log_text": log_text,
                "severity": severity,
                "resolution": resolution,
                "root_cause": root_cause,
            },
        )],
    )


def search_qdrant(query: str, k: int = 5,
                  severity_filter: str | None = None) -> list[dict]:
    ensure_collection()
    query_vec = embed(query)
    qfilter = None
    if severity_filter:
        qfilter = Filter(must=[
            FieldCondition(key="severity", match=MatchValue(value=severity_filter))
        ])
    results = _client.search(
        collection_name=_COLLECTION,
        query_vector=query_vec,
        limit=k,
        query_filter=qfilter,
        with_payload=True,
    )
    return [
        {**r.payload, "similarity": r.score}
        for r in results
        if r.score >= 0.7
    ]
