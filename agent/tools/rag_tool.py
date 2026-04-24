"""RAG-backed past incident search tool."""
import os

import asyncpg

from agent_gate.enforce import gated_tool
from rag.aois_rag import retrieve_context

_db_pool = None


async def _get_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    return _db_pool


@gated_tool(agent_role="read_only")
async def search_past_incidents(query: str, session_id: str = "default") -> str:
    db = await _get_pool()
    context = await retrieve_context(db, query, k_candidates=10, top_k=3)
    return context if context else "No similar past incidents found."
