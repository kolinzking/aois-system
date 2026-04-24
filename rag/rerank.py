from sentence_transformers import CrossEncoder

_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def rerank(query: str, candidates: list[dict], top_k: int = 3) -> list[dict]:
    """Re-score retrieved incidents with a cross-encoder. Returns top_k most relevant."""
    pairs = [
        (query, f"{c['log_text']} Resolution: {c.get('resolution', '')}")
        for c in candidates
    ]
    scores = _model.predict(pairs)
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked[:top_k]]
