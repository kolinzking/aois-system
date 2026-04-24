import asyncpg
from .embed import embed


async def index_incident(db: asyncpg.Pool, incident_id: str, log_text: str,
                         severity: str, resolution: str = "",
                         root_cause: str = "") -> None:
    vector = embed(f"{log_text} {resolution} {root_cause}".strip())
    await db.execute(
        """
        INSERT INTO incidents
          (incident_id, log_text, severity, resolution, root_cause, embedding)
        VALUES ($1, $2, $3, $4, $5, $6::vector)
        ON CONFLICT (incident_id) DO UPDATE
            SET log_text    = EXCLUDED.log_text,
                severity    = EXCLUDED.severity,
                resolution  = EXCLUDED.resolution,
                root_cause  = EXCLUDED.root_cause,
                embedding   = EXCLUDED.embedding
        """,
        incident_id, log_text, severity, resolution, root_cause, str(vector),
    )


async def search_similar(db: asyncpg.Pool, query: str, k: int = 5,
                         min_similarity: float = 0.7) -> list[dict]:
    query_vec = embed(query)
    rows = await db.fetch(
        """
        SELECT
            incident_id, log_text, severity, resolution, root_cause,
            1 - (embedding <=> $1::vector) AS similarity
        FROM incidents
        WHERE 1 - (embedding <=> $1::vector) >= $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        str(query_vec), min_similarity, k,
    )
    return [dict(r) for r in rows]
