import asyncpg


async def hybrid_search(db: asyncpg.Pool, query: str, query_vec: list[float],
                        k: int = 5, vector_weight: float = 0.7) -> list[dict]:
    """Reciprocal Rank Fusion over vector similarity + Postgres full-text search."""
    rows = await db.fetch(
        """
        WITH vector_results AS (
            SELECT incident_id, log_text, severity, resolution, root_cause,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS vector_rank
            FROM incidents LIMIT $3
        ),
        text_results AS (
            SELECT incident_id, log_text, severity, resolution, root_cause,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank(fts, plainto_tsquery('english', $2)) DESC
                   ) AS text_rank
            FROM incidents
            WHERE fts @@ plainto_tsquery('english', $2)
            LIMIT $3
        ),
        combined AS (
            SELECT
                COALESCE(v.incident_id, t.incident_id)   AS incident_id,
                COALESCE(v.log_text, t.log_text)         AS log_text,
                COALESCE(v.severity, t.severity)         AS severity,
                COALESCE(v.resolution, t.resolution)     AS resolution,
                COALESCE(v.root_cause, t.root_cause)     AS root_cause,
                ($4 * (1.0 / (60 + COALESCE(v.vector_rank, 1000)))) +
                ((1 - $4) * (1.0 / (60 + COALESCE(t.text_rank, 1000)))) AS rrf_score
            FROM vector_results v
            FULL OUTER JOIN text_results t USING (incident_id)
        )
        SELECT * FROM combined ORDER BY rrf_score DESC LIMIT $3
        """,
        str(query_vec), query, k, vector_weight,
    )
    return [dict(r) for r in rows]
