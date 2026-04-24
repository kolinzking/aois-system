import asyncpg

from .pgvector_store import search_similar
from .rerank import rerank


async def retrieve_context(db: asyncpg.Pool, log_text: str,
                           k_candidates: int = 10, top_k: int = 3) -> str:
    """
    Retrieve and rerank similar past incidents.
    Returns a formatted context string ready to prepend to the LLM system prompt.
    """
    candidates = await search_similar(db, log_text, k=k_candidates)
    if not candidates:
        return ""
    top = rerank(log_text, candidates, top_k=top_k)
    lines = ["## Similar Past Incidents\n"]
    for i, inc in enumerate(top, 1):
        lines.append(f"### Incident {i}: {inc['incident_id']} (Severity: {inc['severity']})")
        lines.append(f"**Log**: {inc['log_text']}")
        lines.append(f"**Root cause**: {inc.get('root_cause', 'unknown')}")
        lines.append(f"**Resolution**: {inc.get('resolution', 'unknown')}\n")
    return "\n".join(lines)
