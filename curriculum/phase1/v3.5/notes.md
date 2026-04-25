# v3.5 — RAG: Retrieval-Augmented Generation for Incident History

⏱ **Estimated time: 6–8 hours**

---

## Prerequisites

v3 Instructor + Langfuse working. Postgres from Docker Compose running.

```bash
# AOIS analysis returns validated structured output
python3 -c "from main import analyze; import asyncio; r = asyncio.run(analyze('pod OOMKilled exit code 137')); print(r.severity)"
# P2

# Postgres is up
psql $DATABASE_URL -c "SELECT current_database();"
# current_database
# ──────────────────
# aois

# pgvector extension available
psql $DATABASE_URL -c "SELECT * FROM pg_available_extensions WHERE name='vector';"
# name  | default_version | comment
# vector| 0.7.0           | ...
# (If no row — install pgvector: see Troubleshooting)
```

---

## Learning Goals

By the end you will be able to:

- Explain what RAG is and why a pure LLM cannot solve "have you seen this before?"
- Build the same RAG pipeline on both pgvector and Qdrant and explain the tradeoff
- Implement chunking strategies and explain why chunk size and overlap matter
- Build a hybrid search combining vector similarity with BM25 keyword search
- Add a cross-encoder reranker to improve precision of retrieved results
- Evaluate RAG quality with RAGAS metrics (faithfulness, answer relevance, context precision)
- Integrate past incident retrieval into AOIS so it can say "seen this before — here is what fixed it"

---

## The Problem This Solves

AOIS in v3 analyzes a log and returns a structured assessment. Every analysis starts from scratch. When an OOMKilled event comes in for the third time this week, AOIS gives the same generic answer it gave the first time.

A senior SRE does not do this. A senior SRE says: "this is the third time the auth service has OOMKilled this week. The previous two times we fixed it by increasing the memory limit from 512Mi to 768Mi. We should do that permanently."

That capability requires memory — specifically, retrieval of relevant past incidents. That is RAG.

### Why RAG, Not Just Fine-tuning?

Fine-tuning (v15) bakes knowledge into model weights at training time. It is good for consistent *style* (always return structured JSON) and domain vocabulary. It is poor for *specific factual recall* (what was the resolution of incident #2047 on April 3rd?).

RAG retrieves specific facts at inference time from a searchable store. It is good for factual recall and keeps the knowledge base fresh (new incidents are indexed immediately, no retraining needed). In production, most AI products use both: fine-tuning for style/format, RAG for facts.

---

## What RAG Is

```
User query: "auth service OOMKilled"
          ↓
     Embedding model
          ↓
  Query vector [0.12, -0.34, ...]
          ↓
  Vector DB: find K nearest neighbors
          ↓
  Retrieved chunks:
    - "Incident 2031: auth-service OOMKilled — resolution: memory limit 512→768Mi"
    - "Incident 2019: auth-service memory spike — root cause: JWT cache unbounded"
    - "Incident 1998: auth pod restart loop — unrelated, low similarity"
          ↓
  Reranker: re-score for actual relevance, keep top 2
          ↓
  LLM prompt = system + retrieved context + current log
          ↓
  Response: "I've seen this twice before. Previous resolution was..."
```

Four components:
1. **Embedding**: convert text to a vector that captures semantic meaning
2. **Vector store**: search for vectors close to the query vector (approximate nearest neighbor)
3. **Reranker**: re-score retrieved results for true relevance (cross-encoder, slower but more accurate)
4. **Generation**: LLM receives the retrieved context alongside the query

---

## pgvector vs Qdrant

You will build the same pipeline on both. The exercise is not to pick a winner — it is to understand what each adds and where each fits.

| | pgvector | Qdrant |
|---|---|---|
| **What it is** | Vector similarity search extension for Postgres | Purpose-built vector database |
| **Deployment** | One more extension in your existing Postgres | Separate service (Docker container) |
| **Index type** | IVFFlat or HNSW | HNSW (always) |
| **Max scale** | ~1M vectors comfortably | 100M+ vectors |
| **Metadata filtering** | SQL WHERE clauses | Qdrant filter syntax |
| **When to use** | You already have Postgres; <1M vectors | Dedicated vector workload; scale matters |
| **AOIS use** | Dev/staging; incident history | Production at scale; multi-tenant |

The decision is operational, not correctness. Both return the same results for a small incident store. When your incident history exceeds ~500k entries, pgvector starts to show latency; that is when you migrate to Qdrant.

---

## Setting Up pgvector

```bash
# Enable the extension in your Postgres instance
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS vector;"
# CREATE EXTENSION

# Verify
psql $DATABASE_URL -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
# extversion
# ───────────
# 0.7.0

# Create the incidents table with a vector column
psql $DATABASE_URL <<'SQL'
CREATE TABLE IF NOT EXISTS incidents (
    id              BIGSERIAL PRIMARY KEY,
    incident_id     TEXT UNIQUE NOT NULL,
    log_text        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    resolution      TEXT,
    root_cause      TEXT,
    resolved_at     TIMESTAMPTZ,
    embedding       VECTOR(1536),   -- OpenAI text-embedding-3-small dimension
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW index: approximate nearest neighbor, faster than IVFFlat at query time
-- m=16: number of connections per layer. ef_construction=64: build quality vs speed
CREATE INDEX IF NOT EXISTS incidents_embedding_hnsw
    ON incidents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
SQL
# CREATE TABLE
# CREATE INDEX
```

### Why HNSW over IVFFlat?

IVFFlat partitions vectors into clusters (like a k-means clustering), then searches only the relevant clusters. Fast to build, memory-efficient, but requires you to specify the number of clusters (`lists`) at index creation — and you need data to choose the right number.

HNSW (Hierarchical Navigable Small World) builds a multi-layer graph where each vector is connected to its nearest neighbors. Query: start at the top layer, navigate toward the query vector, descend layers to find the closest matches. No cluster count to tune. Better recall at the same latency. Higher memory usage. HNSW is the modern default.

---

## The Embedding Model

You need to convert text to vectors. In v3.5 you will use OpenAI's `text-embedding-3-small` (1536 dimensions, $0.02/1M tokens). It is cheap, fast, and the most widely deployed embedding model.

```python
# rag/embed.py
import os
import openai
from functools import lru_cache

_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_MODEL = "text-embedding-3-small"


def embed(text: str) -> list[float]:
    """Embed a single text. For batch use embed_many()."""
    response = _client.embeddings.create(model=_MODEL, input=text)
    return response.data[0].embedding


def embed_many(texts: list[str]) -> list[list[float]]:
    """Batch embedding — cheaper per token than individual calls."""
    response = _client.embeddings.create(model=_MODEL, input=texts)
    return [item.embedding for item in response.data]
```

Why not use a local embedding model (e.g., `sentence-transformers`)? You could. Local models:
- Zero cost
- No API dependency
- 384 or 768 dimensions (smaller than OpenAI's 1536)
- Slightly lower quality on domain-specific text

For AOIS in v3.5, OpenAI embeddings give you a benchmark quality. In production, you would evaluate whether the cost of API embeddings justifies the quality improvement over a local model. The `embed.py` interface is the same either way — swap the implementation, not the callers.

---

## Chunking Strategy

Before embedding, you need to decide how to break incident documents into searchable chunks.

### Fixed-size chunking

Split at every N characters, with overlap:

```python
def chunk_fixed(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks
```

Simple. Works when text has no natural boundaries. The problem: a sentence split mid-way can produce meaningless chunks ("...memory limit from 512" / "Mi to 768Mi — root cause...").

### Sentence/semantic chunking

Split at sentence boundaries, group until a size threshold:

```python
import re

def chunk_sentences(text: str, max_tokens: int = 200) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current, current_len = [], [], 0
    for sent in sentences:
        word_count = len(sent.split())
        if current_len + word_count > max_tokens and current:
            chunks.append(" ".join(current))
            current, current_len = [], 0
        current.append(sent)
        current_len += word_count
    if current:
        chunks.append(" ".join(current))
    return chunks
```

For AOIS incident records (short, structured documents), the entire incident fits in one chunk. Chunking matters most for long-form documents (runbooks, post-mortems). For the incident store, each incident is one document, one embedding.

---

## Building the pgvector RAG Pipeline

```python
# rag/pgvector_store.py
import asyncpg
import os
from .embed import embed, embed_many


async def index_incident(db: asyncpg.Pool, incident_id: str, log_text: str,
                         severity: str, resolution: str = "", root_cause: str = "") -> None:
    vector = embed(f"{log_text} {resolution} {root_cause}".strip())
    await db.execute(
        """
        INSERT INTO incidents (incident_id, log_text, severity, resolution, root_cause, embedding)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (incident_id) DO UPDATE
            SET log_text=EXCLUDED.log_text, severity=EXCLUDED.severity,
                resolution=EXCLUDED.resolution, root_cause=EXCLUDED.root_cause,
                embedding=EXCLUDED.embedding
        """,
        incident_id, log_text, severity, resolution, root_cause,
        str(vector),  # asyncpg serializes lists as Postgres arrays; vector type needs string
    )


async def search_similar(db: asyncpg.Pool, query: str, k: int = 5,
                         min_similarity: float = 0.7) -> list[dict]:
    query_vec = embed(query)
    rows = await db.fetch(
        """
        SELECT
            incident_id,
            log_text,
            severity,
            resolution,
            root_cause,
            1 - (embedding <=> $1::vector) AS similarity
        FROM incidents
        WHERE 1 - (embedding <=> $1::vector) >= $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        str(query_vec), min_similarity, k,
    )
    return [dict(r) for r in rows]
```

The `<=>` operator is pgvector's cosine distance. `1 - cosine_distance = cosine_similarity`. A similarity of 1.0 is identical; 0.7 is the minimum threshold — below that, the retrieved incident is probably about a different problem.

---

## ▶ STOP — do this now

Index 10 synthetic incidents and run a retrieval query:

```python
# rag/seed_incidents.py
import asyncio
import asyncpg
import os
from pgvector_store import index_incident

INCIDENTS = [
    ("INC-001", "pod OOMKilled exit code 137 auth-service", "P2",
     "Increased memory limit from 512Mi to 768Mi", "JWT cache unbounded growth"),
    ("INC-002", "CrashLoopBackOff api-gateway ImagePullBackOff", "P3",
     "Fixed image tag from :latest to :v1.2.3", "Unstable latest tag"),
    ("INC-003", "disk pressure node-1 /var/lib/kubelet 95% full", "P2",
     "Pruned old container images with crictl rmi", "Docker images accumulated"),
    ("INC-004", "5xx spike 503 upstream connect error or disconnect", "P1",
     "Rolled back deployment to v2.1.0", "Memory leak in v2.2.0"),
    ("INC-005", "certificate expired for aois.example.com", "P2",
     "Renewed via cert-manager ACME challenge", "cert-manager misconfigured renewal"),
    ("INC-006", "pod OOMKilled payment-service exit code 137", "P2",
     "Increased memory limit from 1Gi to 2Gi", "Burst traffic during sale"),
    ("INC-007", "Kafka consumer lag growing aois-logs partition 0", "P3",
     "Scaled consumer pods from 1 to 3", "KEDA threshold set too high"),
    ("INC-008", "CPU throttling 99% on analysis-worker pods", "P3",
     "Raised CPU limit from 500m to 1000m", "Batch analysis job competed with realtime"),
    ("INC-009", "etcd high latency 500ms p99 disk io wait", "P1",
     "Moved etcd data to NVMe volume", "Spinning disk caused election timeouts"),
    ("INC-010", "auth-service memory spike RSS 900Mi out of 512Mi limit", "P2",
     "Increased limit and added memory profiling", "Session store not evicting expired sessions"),
]

async def main():
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    for inc_id, log, sev, resolution, root_cause in INCIDENTS:
        await index_incident(db, inc_id, log, sev, resolution, root_cause)
        print(f"Indexed {inc_id}")
    await db.close()

asyncio.run(main())
```

```bash
cd /home/collins/aois-system
python3 -m rag.seed_incidents
# Indexed INC-001
# Indexed INC-002
# ...
# Indexed INC-010

# Now query for a similar incident
python3 - <<'EOF'
import asyncio, asyncpg, os
from rag.pgvector_store import search_similar

async def main():
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    results = await search_similar(db, "auth service OOMKilled memory limit", k=3)
    for r in results:
        print(f"[{r['similarity']:.3f}] {r['incident_id']}: {r['log_text'][:60]}")
        print(f"  Resolution: {r['resolution']}")
    await db.close()

asyncio.run(main())
EOF
# [0.923] INC-001: pod OOMKilled exit code 137 auth-service
#   Resolution: Increased memory limit from 512Mi to 768Mi
# [0.891] INC-010: auth-service memory spike RSS 900Mi out of 512Mi limit
#   Resolution: Increased limit and added memory profiling
# [0.841] INC-006: pod OOMKilled payment-service exit code 137
#   Resolution: Increased memory limit from 1Gi to 2Gi
```

INC-001 and INC-010 are correctly the top results for an auth service OOM query. INC-006 is a related OOM in a different service — lower similarity, included because the pattern matches.

---

## Hybrid Search: Vector + BM25

Pure vector search finds semantically similar results. BM25 (the algorithm behind Elasticsearch's default ranking) finds keyword matches. They are complementary:

- Vector: "auth service crashed because it ran out of memory" → finds OOMKilled incidents even without the exact words
- BM25: "OOMKilled exit code 137" → finds incidents with those exact tokens, even if semantically distant

Production RAG combines both (Reciprocal Rank Fusion). In v3.5 you will implement a simplified hybrid using pgvector for vectors and a Postgres full-text search index for BM25-like keyword matching.

```sql
-- Add full-text search to the incidents table
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(log_text, '') || ' ' ||
                               coalesce(resolution, '') || ' ' ||
                               coalesce(root_cause, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS incidents_fts_idx ON incidents USING GIN(fts);
```

```python
# rag/hybrid_search.py
import asyncpg


async def hybrid_search(db: asyncpg.Pool, query: str, query_vec: list[float],
                        k: int = 5, vector_weight: float = 0.7) -> list[dict]:
    """
    Combine vector similarity and full-text search via Reciprocal Rank Fusion.
    vector_weight=0.7 means vector results contribute 70% of the final score.
    """
    rows = await db.fetch(
        """
        WITH vector_results AS (
            SELECT incident_id, log_text, severity, resolution, root_cause,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS vector_rank
            FROM incidents
            LIMIT $3
        ),
        text_results AS (
            SELECT incident_id, log_text, severity, resolution, root_cause,
                   ROW_NUMBER() OVER (ORDER BY ts_rank(fts, plainto_tsquery('english', $2)) DESC) AS text_rank
            FROM incidents
            WHERE fts @@ plainto_tsquery('english', $2)
            LIMIT $3
        ),
        combined AS (
            SELECT
                COALESCE(v.incident_id, t.incident_id) AS incident_id,
                COALESCE(v.log_text, t.log_text) AS log_text,
                COALESCE(v.severity, t.severity) AS severity,
                COALESCE(v.resolution, t.resolution) AS resolution,
                COALESCE(v.root_cause, t.root_cause) AS root_cause,
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
```

Reciprocal Rank Fusion (RRF) combines results by their rank, not their raw score. This avoids the scaling problem: vector similarity scores (0.0–1.0) and BM25 scores (0–∞) are not directly comparable. RRF works on ranks, which are comparable.

---

## Qdrant: Purpose-Built Vector Search

Install Qdrant via Docker:

```bash
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_data:/qdrant/storage \
  qdrant/qdrant:v1.9.0
# (pull and start — takes ~30 seconds)

# Verify
curl -s http://localhost:6333/healthz
# {"title":"qdrant","version":"1.9.0"}
```

```python
# rag/qdrant_store.py
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue, SearchRequest,
)
from .embed import embed
import uuid

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
```

The key Qdrant capability demonstrated here: **metadata filtering**. `severity_filter="P1"` retrieves only critical incidents, regardless of vector similarity to lower-severity events. pgvector can do this too (SQL WHERE clause), but Qdrant's filter is applied *during* the ANN search, not as a post-filter — it is faster at scale.

---

## Cross-Encoder Reranking

The embedding model retrieves candidates quickly (milliseconds for 10k vectors). But embeddings are computed independently — they do not capture how relevant a retrieved chunk is *to the specific query*. A reranker scores each (query, chunk) pair jointly, which is more accurate but slower.

```python
# rag/rerank.py
"""
Cross-encoder reranker using a small local model (no API cost).
sentence-transformers: pip install sentence-transformers
"""
from sentence_transformers import CrossEncoder

_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def rerank(query: str, candidates: list[dict], top_k: int = 3) -> list[dict]:
    """
    Re-score retrieved incidents. Returns top_k most relevant.
    candidates: list of dicts with 'log_text', 'resolution', etc.
    """
    pairs = [
        (query, f"{c['log_text']} Resolution: {c.get('resolution', '')}")
        for c in candidates
    ]
    scores = _model.predict(pairs)
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked[:top_k]]
```

```bash
pip install sentence-transformers
# (downloads cross-encoder/ms-marco-MiniLM-L-6-v2 on first run — ~80MB)

python3 - <<'EOF'
from rag.rerank import rerank

query = "auth service running out of memory"
candidates = [
    {"log_text": "pod OOMKilled exit code 137 auth-service", "resolution": "Increased memory limit"},
    {"log_text": "auth-service memory spike RSS 900Mi", "resolution": "Added memory profiling"},
    {"log_text": "Kafka consumer lag growing", "resolution": "Scaled consumer pods"},  # unrelated
]
results = rerank(query, candidates, top_k=2)
for r in results:
    print(r["log_text"][:60])
EOF
# pod OOMKilled exit code 137 auth-service
# auth-service memory spike RSS 900Mi
# (Kafka entry correctly dropped by reranker)
```

The reranker correctly identifies the Kafka incident as irrelevant even if the vector search returned it as a candidate. This is precision vs recall: embeddings optimise recall (find everything plausibly related), rerankers optimise precision (keep only the actually relevant ones).

---

## ▶ STOP — do this now

Run a benchmark comparing pgvector vs Qdrant on 10 queries:

```python
# rag/benchmark.py
import asyncio, asyncpg, os, time
from pgvector_store import search_similar
from qdrant_store import search_qdrant

QUERIES = [
    "auth service OOMKilled memory limit exceeded",
    "Kafka consumer lag growing beyond threshold",
    "certificate expired TLS handshake failure",
    "pod CrashLoopBackOff image pull error",
    "disk pressure node storage full kubelet",
]

async def main():
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    print(f"{'Query':<50} {'pgvector':>10} {'Qdrant':>10}")
    print("-" * 72)
    for q in QUERIES:
        t0 = time.time()
        pgv_results = await search_similar(db, q, k=3)
        pgv_ms = int((time.time() - t0) * 1000)

        t0 = time.time()
        qd_results = search_qdrant(q, k=3)
        qd_ms = int((time.time() - t0) * 1000)

        print(f"{q[:48]:<50} {pgv_ms:>9}ms {qd_ms:>9}ms")
    await db.close()

asyncio.run(main())
```

```bash
python3 -m rag.benchmark
# Query                                              pgvector     Qdrant
# ────────────────────────────────────────────────────────────────────────
# auth service OOMKilled memory limit exceeded         143ms       38ms
# Kafka consumer lag growing beyond threshold          138ms       41ms
# certificate expired TLS handshake failure            141ms       36ms
# pod CrashLoopBackOff image pull error                139ms       39ms
# disk pressure node storage full kubelet              137ms       40ms
```

At 10 incidents, Qdrant is 3–4x faster. At 10,000 incidents, the gap widens. At 1,000,000 incidents, pgvector's HNSW performance degrades noticeably while Qdrant's stays consistent. For AOIS at current scale, either is fine. Know the crossover point.

---

## RAGAS: Evaluating RAG Quality

RAGAS (Retrieval Augmented Generation Assessment) is an evaluation framework that scores your RAG pipeline on four metrics:

| Metric | What it measures | How |
|---|---|---|
| **Faithfulness** | Does the answer only claim things the retrieved context supports? | LLM-as-judge: check if each claim in the answer appears in the context |
| **Answer Relevance** | Does the answer actually address the question? | Reverse: generate questions from the answer, measure similarity to original question |
| **Context Precision** | Of the retrieved chunks, how many were actually useful? | What fraction of retrieved items contributed to the answer? |
| **Context Recall** | Did retrieval find all the relevant information? | Given ground truth, what fraction was retrieved? |

```bash
pip install ragas datasets
```

```python
# rag/ragas_eval.py
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from datasets import Dataset

# Build a small eval dataset
eval_data = {
    "question": [
        "What caused the auth service OOMKilled and how was it fixed?",
        "Why did the Kafka consumer lag grow?",
    ],
    "answer": [
        "The auth service OOMKilled because the JWT cache grew unbounded. Fixed by increasing memory limit from 512Mi to 768Mi.",
        "The Kafka consumer lag grew because the KEDA threshold was set too high. Fixed by scaling consumer pods from 1 to 3.",
    ],
    "contexts": [
        ["INC-001: pod OOMKilled exit code 137 auth-service. Resolution: Increased memory limit from 512Mi to 768Mi. Root cause: JWT cache unbounded growth."],
        ["INC-007: Kafka consumer lag growing aois-logs partition 0. Resolution: Scaled consumer pods from 1 to 3. Root cause: KEDA threshold set too high."],
    ],
    "ground_truth": [
        "JWT cache unbounded growth caused OOM. Memory limit increased.",
        "KEDA threshold misconfigured. Consumer pods scaled to 3.",
    ],
}

dataset = Dataset.from_dict(eval_data)
results = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision])
print(results)
```

```bash
python3 -m rag.ragas_eval
# {'faithfulness': 0.94, 'answer_relevancy': 0.89, 'context_precision': 1.00}
```

Interpreting:
- **Faithfulness 0.94**: 94% of claims in the answers are supported by the retrieved context — good
- **Answer Relevancy 0.89**: the answers are mostly on-topic — acceptable
- **Context Precision 1.00**: every retrieved chunk was useful — ideal (small dataset, easy to achieve)

In production with 10,000 incidents, Context Precision is the metric to watch. If it drops below 0.6, your retrieval is polluted with irrelevant results. Fix: increase `min_similarity` threshold or add a reranker.

---

## Integrating RAG into AOIS

Add a `retrieve_similar_incidents` function that the main analyze endpoint calls before prompting the LLM:

```python
# rag/aois_rag.py
import asyncpg
from .pgvector_store import search_similar
from .rerank import rerank


async def retrieve_context(db: asyncpg.Pool, log_text: str,
                           k_candidates: int = 10, top_k: int = 3) -> str:
    """
    Retrieve and rerank similar past incidents.
    Returns a formatted context string for the LLM prompt.
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
```

In `main.py`, include the retrieved context in the LLM prompt:

```python
# In the analyze() function, before the LLM call:
from rag.aois_rag import retrieve_context

async def analyze(log_text: str, ...) -> IncidentAnalysis:
    # ... existing code ...

    # RAG: retrieve similar past incidents
    past_context = ""
    if db_pool:  # graceful degradation if DB unavailable
        past_context = await retrieve_context(db_pool, log_text)

    # Build system prompt with RAG context
    system = SYSTEM_PROMPT
    if past_context:
        system += f"\n\n{past_context}"

    # LLM call proceeds with enhanced system prompt
    ...
```

Now AOIS responds with: *"I've seen similar incidents before. INC-001 showed the same OOMKilled pattern in the auth service. The root cause was JWT cache unbounded growth. The resolution was increasing the memory limit from 512Mi to 768Mi. For the current incident, I recommend the same investigation path."*

---

## ▶ STOP — do this now

Index all 10 incidents, then call the full RAG-augmented analysis:

```python
# From the AOIS root:
import asyncio, asyncpg, os
from rag.aois_rag import retrieve_context

async def main():
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    ctx = await retrieve_context(db, "auth-service pod OOMKilled exit code 137")
    print(ctx)
    await db.close()

asyncio.run(main())
```

Expected output:
```
## Similar Past Incidents

### Incident 1: INC-001 (Severity: P2)
**Log**: pod OOMKilled exit code 137 auth-service
**Root cause**: JWT cache unbounded growth
**Resolution**: Increased memory limit from 512Mi to 768Mi

### Incident 2: INC-010 (Severity: P2)
**Log**: auth-service memory spike RSS 900Mi out of 512Mi limit
**Root cause**: Session store not evicting expired sessions
**Resolution**: Increased limit and added memory profiling
```

If the output is empty, check: (a) embedding succeeded (no API error), (b) the incidents are actually indexed (`SELECT COUNT(*) FROM incidents`), (c) similarity threshold is not too high.

---

## Common Mistakes

### 1. Vector stored as text string instead of Postgres vector type

```python
# Wrong — stores as plain text, index not used
await db.execute("UPDATE incidents SET embedding = $1", str(vector))

# Correct — asyncpg with pgvector requires string representation
# but the column type must be VECTOR(n), not TEXT
await db.execute("UPDATE incidents SET embedding = $1::vector", str(vector))
```

If you see: `ERROR: operator does not exist: text <=> text`, the column is TEXT not VECTOR. Drop and recreate.

---

### 2. Embedding dimension mismatch

```
ERROR: expected 1536 dimensions, not 384
```

You indexed with `text-embedding-3-small` (1536d) but are querying with a `sentence-transformers` model (384d). The collection/column dimension is fixed at creation time. Either use the same model consistently, or create separate columns/collections for different embedding models.

---

### 3. RAGAS import error on evaluation

```
ImportError: cannot import name 'context_precision' from 'ragas.metrics'
```

RAGAS has changed its import paths across versions. For v0.1.x:
```python
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
```
For v0.2.x+, check `ragas --version` and use the updated import path from the changelog.

---

### 4. Reranker first inference is slow

The cross-encoder model downloads on first use (~80MB). Subsequent inferences are fast (<100ms for 10 pairs on CPU). If the first call times out, increase your HTTP timeout or pre-load the model at startup.

---

## Troubleshooting

### pgvector extension not available

```bash
psql $DATABASE_URL -c "CREATE EXTENSION vector;"
# ERROR: could not open extension control file ".../vector.control": No such file or directory
```

pgvector is not installed in the Postgres image. If using Docker:

```bash
# Stop the current container and switch to the pgvector image
docker compose down postgres
# In docker-compose.yml, change the postgres image:
# image: postgres:15  →  image: pgvector/pgvector:pg15
docker compose up -d postgres
psql $DATABASE_URL -c "CREATE EXTENSION vector;"
# CREATE EXTENSION
```

---

### Qdrant returns empty results

```python
results = search_qdrant("auth OOMKilled", k=3)
# []
```

Check: (a) `ensure_collection()` was called, (b) `index_incident_qdrant()` actually indexed data:

```python
from qdrant_client import QdrantClient
c = QdrantClient(host="localhost", port=6333)
info = c.get_collection("aois_incidents")
print(info.points_count)
# 0  ← nothing was indexed
```

If 0, re-run the indexing step. If the count is correct but results are empty, the similarity threshold (0.7) may be too high — lower it temporarily to 0.0 to confirm retrieval works.

---

## LlamaIndex: The Production RAG Standard

You have built RAG from scratch — embeddings, pgvector, hybrid search, reranker. That is the right way to *understand* RAG. Now learn the tool that production codebases use to *build* it.

LlamaIndex is a framework that handles the full RAG pipeline — document loading, chunking, embedding, indexing, retrieval, reranking — with a consistent API across every vector store and every embedding model. When you join an AI engineering team, their codebase will use LlamaIndex or LangChain, not a custom pipeline.

**Install:**
```bash
pip install llama-index llama-index-vector-stores-postgres llama-index-embeddings-openai
```

**The same AOIS RAG pipeline, built with LlamaIndex:**
```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core import Settings
import sqlalchemy

# Configure embedding model globally
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

# Connect to pgvector
engine = sqlalchemy.create_engine(os.getenv("DATABASE_URL"))
vector_store = PGVectorStore.from_params(
    database="aois",
    host="localhost",
    port=5432,
    table_name="llamaindex_incidents",
    embed_dim=1536,
)

# Build index from incident documents
storage_context = StorageContext.from_defaults(vector_store=vector_store)
documents = SimpleDirectoryReader("incidents/").load_data()
index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)

# Query — this is the full retrieve + rerank + generate pipeline in one call
query_engine = index.as_query_engine(similarity_top_k=5)
response = query_engine.query("auth service OOMKilled exit code 137")
print(response)
# AOIS past incident INC-001 (2024-03-12): auth-service OOMKilled due to
# connection pool leak. Resolution: increased memory limit to 512Mi and
# patched connection pool max to 50.
```

**LlamaIndex vs custom pipeline — when each wins:**

| Concern | Custom pipeline | LlamaIndex |
|---------|----------------|------------|
| Understanding | Forced — you see every step | Hidden in abstractions |
| Speed to build | Slow | Fast |
| Flexibility | Total control | Plugin architecture |
| Enterprise codebase | You build it | You read it |
| Multi-source ingestion | Write each loader | 100+ built-in loaders |
| Switching vector stores | Rewrite queries | Change one class |

**The critical insight:** LlamaIndex and custom RAG are not alternatives — they represent different phases. You built custom to understand. You use LlamaIndex in production because it solves ingestion (PDFs, Notion, Slack, databases — all via the same `load_data()` interface) and store-switching (swap pgvector for Qdrant by changing one class) at a cost you would otherwise pay in weeks of engineering work.

**AOIS integration — expose LlamaIndex as a query engine alongside the existing custom RAG:**
```python
# agent/tools/rag_tool.py — add LlamaIndex as a second retrieval path
def retrieve_with_llamaindex(query: str, top_k: int = 5) -> list[dict]:
    """LlamaIndex-powered retrieval — same data, different engine."""
    query_engine = _get_llamaindex_engine()
    response = query_engine.query(query)
    return [
        {"text": node.text, "score": node.score}
        for node in response.source_nodes
    ]
```

**▶ STOP — do this now**

Install LlamaIndex, index the same 10 synthetic incidents from earlier in this version using `VectorStoreIndex`, and run a query for "memory limit exceeded". Compare the top result to what your custom `retrieve_context()` returns for the same query. Are they the same incident? If not, explain why — is it chunking, embedding model, or similarity threshold?

```bash
pip install llama-index llama-index-vector-stores-postgres
python3 -c "
from llama_index.core import VectorStoreIndex, Document
from llama_index.core import Settings
# Use default local embedding for this test
docs = [Document(text='INC-001 auth-service OOMKilled memory limit 256Mi')]
idx = VectorStoreIndex.from_documents(docs)
engine = idx.as_query_engine()
print(engine.query('auth service memory limit exceeded'))
"
```

Expected: a response grounded in the indexed document, not a generic LLM answer.

---

## Long Context vs RAG: The 2026 Architectural Decision

This is the most important architectural question in AI engineering right now and it is not addressed in most curricula.

**The question:** Claude has a 200,000-token context window. Gemini has 1,000,000. If you can fit your entire knowledge base into the context window — why do you need RAG at all?

**The honest answer:** sometimes you don't. Understanding when is the difference between overengineering and underengineering.

**The decision framework:**

```
Knowledge base size → fits in context window?
    YES → Cost acceptable?
        YES → Is latency acceptable?
            YES → use long context (simpler, no retrieval errors)
            NO  → use RAG (retrieve only what's needed)
        NO  → use RAG (cost control)
    NO  → use RAG (no choice)
```

**Concrete numbers (April 2026):**

| Scenario | Tokens | Approach | Why |
|----------|--------|----------|-----|
| 50 past incidents | ~25,000 | Long context | Fits, $0.004/call, fast |
| 500 past incidents | ~250,000 | Long context or RAG | At boundary — measure cost |
| 5,000 past incidents | ~2,500,000 | RAG | Exceeds context, must retrieve |
| 50,000 past incidents | ~25,000,000 | RAG | No choice |

**What long context wins at:**
- No retrieval errors (you cannot miss a relevant incident if everything is included)
- No embedding model drift (no semantic mismatch between query and indexed content)
- Simpler architecture (no vector store, no chunking decisions)
- Better for reasoning across all documents simultaneously ("which three incidents have the same root cause?")

**What RAG wins at:**
- Cost at scale (retrieve 5 incidents instead of sending 50,000)
- Latency (smaller prompt = faster response)
- Fresh data (vector store updates without re-prompting)
- Privacy (don't send your entire knowledge base to an API for every query)

**The AOIS-specific answer:**

For AOIS at current scale (hundreds of incidents), long context is viable and simpler. The reason AOIS uses RAG is not because it must — it is because v3.5 teaches the RAG pattern which matters at scale. At 10,000+ incidents, RAG becomes necessary. At 100 incidents, long context is the right call.

**Hybrid pattern (production standard for 2026):**

```python
def retrieve_for_aois(query: str, incident_store: list[dict]) -> str:
    """
    Route to long context or RAG based on store size.
    Threshold is cost-driven: 100k tokens = ~$0.08 with Claude Haiku.
    """
    estimated_tokens = len(incident_store) * 500  # ~500 tokens per incident
    
    if estimated_tokens < 50_000:
        # Long context: stuff everything in, no retrieval errors
        context = "\n".join(i["text"] for i in incident_store)
        return f"All past incidents:\n{context}"
    else:
        # RAG: retrieve top-k most relevant
        return retrieve_context(query, top_k=5)
```

**▶ STOP — do this now**

Run the cost calculation for your AOIS incident store. Check how many incidents are currently indexed:
```python
import psycopg2, os
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM incidents")
count = cur.fetchone()[0]
print(f"Incidents in store: {count}")
print(f"Estimated tokens: {count * 500:,}")
print(f"Estimated cost per query (Claude Haiku, $0.80/1M input): ${count * 500 * 0.00000080:.4f}")
print(f"RAG threshold: {'long context viable' if count < 100 else 'RAG recommended'}")
```

At what incident count does long context become more expensive than RAG for AOIS? Write the number down — that is your architectural inflection point.

---

## Connection to Later Phases

### To v2.5 (AI Gateway)
The RAG retrieve step can be cached in the AI Gateway exactly like LLM responses. Identical log queries return cached retrieved contexts with no embedding API call. The `gateway/cache.py` SHA256 key works for RAG contexts too: `key = sha256("rag:" + query)`.

### To v20 (Claude Tool Use)
In v20, AOIS gets a `search_past_incidents` tool. The agent calls it explicitly when investigating an incident, rather than automatically prepending context. The tool is the RAG retrieve step from v3.5, exposed as a callable tool the agent decides when to use. The underlying `retrieve_context()` function is identical.

### To v23.5 (Agent Evaluation)
The RAGAS evaluation framework you used in v3.5 is the same framework used to evaluate agent outputs in v23.5. Faithfulness (does the agent's answer cite valid evidence?) and answer relevance (does the suggested action address the incident?) are directly applicable to agent evaluation, not just RAG.

### To v34.5 (AI SRE Capstone)
Embedding drift is an AI-specific SLO in the capstone. RAG quality degrades silently when the incident store grows large enough that the embedding model's representation of new incidents drifts from older ones. v3.5's RAGAS metrics are the baseline. In v34.5, you detect drift when Context Precision drops below 0.7 over a 7-day rolling window.

---


## Build-It-Blind Challenge

Close the notes. From memory: write `retrieve_context()` — it must embed a query string, search the pgvector incidents table using cosine similarity, apply a 0.7 minimum threshold, and return the top 3 results as formatted strings for LLM context injection. 20 minutes.

```python
ctx = retrieve_context("auth service keeps restarting with exit code 137")
print(len(ctx))    # > 0 if incidents are indexed
print(ctx[0])      # formatted incident string
```

---

## Failure Injection

Drop the HNSW index and run retrieval:

```sql
DROP INDEX incidents_embedding_idx;
```

```python
import time
start = time.time()
retrieve_context("OOMKilled auth service")
print(f"Without index: {time.time()-start:.3f}s")
```

Re-create the index and compare. Then set `min_similarity=0.99` and run the same query. What happens to results? Lower it to `0.0` — what returns now? This is the threshold calibration problem every RAG system faces.

---

## Osmosis Check

1. The embedding model you use in v3.5 is `text-embedding-3-small`. In v20 (agent tool use), `search_past_incidents` calls the same `retrieve_context()`. If the embedding model is upgraded between now and v20, what breaks in the existing index and what is the remediation?
2. Your RAG pipeline adds 2,000 tokens of retrieved context to every LLM call. Calculate the additional monthly cost at Claude Sonnet pricing for 5,000 incidents/day where 60% trigger RAG retrieval. Is caching (v1) applicable here?

---

## Mastery Checkpoint

1. Enable pgvector in Postgres and verify with `SELECT extversion FROM pg_extension WHERE extname='vector'`. Create the incidents table with a HNSW index and confirm the index exists with `\d incidents`.

2. Embed and index all 10 synthetic incidents. Run a similarity search for "auth service memory limit" and confirm INC-001 and INC-010 are in the top 3 results. Record the similarity scores.

3. Add the full-text search column and index. Run a hybrid search for "OOMKilled" and compare the results to pure vector search. Which incidents appear in one but not the other?

4. Set up Qdrant in Docker, index the same 10 incidents, and run the benchmark script. Record: pgvector latency vs Qdrant latency. What scale would you need to reach before the latency difference changes your architecture decision?

5. Run the reranker on 5 candidates for a query of your choice. Confirm the reranker changes the order relative to vector similarity alone. Explain in one sentence why the reranker and the embedding model disagree on ranking.

6. Run RAGAS evaluation. Record the three metric scores. If Context Precision is below 0.9, identify which retrieved chunk was not useful and explain why it was retrieved.

7. Integrate `retrieve_context()` into the main AOIS `analyze()` function. Confirm the LLM response for "auth service OOMKilled" now mentions the specific past incident and its resolution.

8. Explain to a non-technical person why AOIS needs to "remember" past incidents, and how retrieval gives it that memory without retraining the model.

9. Explain to a senior engineer the tradeoff between `min_similarity` threshold and false positives in retrieval. At what threshold does a retrieved incident stop being useful? How would you measure this in production?

9. Build the same RAG pipeline using LlamaIndex. Run both your custom `retrieve_context()` and the LlamaIndex query engine on the same query. Where do results differ, and why?

10. For your current AOIS incident count: should you use RAG or long context? Show the cost calculation. At what incident count does your answer change?

**The mastery bar:** you can build a complete RAG pipeline from scratch — embed, index, retrieve, rerank, evaluate — and explain every decision (embedding model choice, chunking strategy, HNSW vs IVFFlat, reranking necessity) at all three audience levels. You can also explain when RAG is the wrong choice and long context is better, with numbers to back the decision.

---

## 4-Layer Tool Understanding

### RAG (Retrieval-Augmented Generation)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | LLMs do not have memory. RAG gives them access to a searchable knowledge base so they can say "I've seen this before" and retrieve the specific past resolution, rather than giving a generic answer from training data. |
| **System Role** | Where does it sit in AOIS? | Before the LLM call in the analyze pipeline. The current log is embedded, similar past incidents are retrieved from Postgres/Qdrant, the top results are reranked, and the retrieved context is prepended to the LLM prompt as grounding evidence. |
| **Technical** | What is it, precisely? | A pipeline of: embedding (dense vector representation of text), approximate nearest neighbor search (cosine similarity in vector space), optional reranking (cross-encoder scores candidate pairs), and generation (LLM produces answer grounded in retrieved context). Reduces hallucination by anchoring responses to real retrieved evidence. |
| **Remove it** | What breaks, and how fast? | Remove RAG → AOIS treats every incident as novel. It cannot leverage the institution's historical knowledge. In a mature cluster, 60-70% of incidents are recurrences — RAG turns those from investigations into recognitions. Loss is immediate and measurable: MTTR for recurrent incidents increases. |

### pgvector

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | You want to find "similar" documents — not matching keywords, but conceptually related. pgvector adds that capability to your existing Postgres database without adding a new service. |
| **System Role** | Where does it sit in AOIS? | As an extension in the Postgres instance from the Docker Compose stack. The incidents table has a `VECTOR(1536)` column and a HNSW index. AOIS queries it with the `<=>` cosine distance operator. |
| **Technical** | What is it, precisely? | A Postgres extension that adds a native vector data type and three distance operators (`<->` Euclidean, `<#>` inner product, `<=>` cosine). Supports IVFFlat and HNSW index types for approximate nearest neighbor search. HNSW is preferred: better recall, no cluster count to tune, scales to ~1M vectors without degradation. |
| **Remove it** | What breaks, and how fast? | Remove pgvector → can no longer store or query embeddings in Postgres. RAG falls back to keyword search (full-text only), losing semantic retrieval. "Auth service crashed due to memory exhaustion" would not find "OOMKilled" incidents. Recall drops significantly. |

### Qdrant

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | At large scale (millions of incidents), pgvector slows down. Qdrant is a database built specifically for vector search — it stays fast at any scale and adds filtering, namespacing, and richer metadata management. |
| **System Role** | Where does it sit in AOIS? | As an alternative vector store to pgvector, running as a separate Docker container. Same interface — `index_incident_qdrant()` / `search_qdrant()` — different backend. Choose Qdrant when AOIS processes more than ~500k incidents. |
| **Technical** | What is it, precisely? | A purpose-built vector database using HNSW for indexing, written in Rust for performance. Supports payload filtering applied during the ANN search (not post-filter), named vectors, and sparse-dense hybrid search natively. REST and gRPC APIs. |
| **Remove it** | What breaks, and how fast? | Remove Qdrant → fall back to pgvector. At small scale: no impact. At large scale: query latency increases from ~40ms to ~500ms+. Above 10M vectors, pgvector becomes unusable for real-time retrieval. |

### LlamaIndex

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Building a RAG pipeline from scratch requires writing loaders, chunkers, embedding calls, index management, and retrieval logic. LlamaIndex solves all of that — you describe what you want to index and query, and it handles the plumbing. |
| **System Role** | Where does it sit in AOIS? | As an alternative retrieval engine alongside the custom pipeline. Both index the same incidents table. LlamaIndex is used when you need rapid ingestion from new sources (Slack, PDFs, runbooks) without writing custom loaders. |
| **Technical** | What is it, precisely? | A framework with three layers: data connectors (100+ loaders for files, databases, APIs), indexing (VectorStoreIndex, SummaryIndex, KnowledgeGraphIndex), and querying (query engines, chat engines, agents). Uses the same underlying vector stores (pgvector, Qdrant, Pinecone) but abstracts the query interface into a uniform API. |
| **Remove it** | What breaks, and how fast? | Remove LlamaIndex → custom retrieval pipeline still works. The loss is velocity: adding a new data source (runbooks, Confluence pages, Slack history) now requires writing a custom loader and parser. LlamaIndex reduces that from a day's work to one line: `SimpleDirectoryReader("runbooks/").load_data()`. |
