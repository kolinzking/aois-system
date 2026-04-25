# v16.5 — ClickHouse: Analytics at Scale for AOIS Telemetry

⏱ **Estimated time: 5–7 hours**

---

## Prerequisites

v16 OTel stack running (Prometheus, Grafana, Loki, Tempo). AOIS emitting metrics.

```bash
# Prometheus is scraping AOIS metrics
curl -s http://localhost:9090/api/v1/query?query=aois_incidents_total | jq '.data.result[0].value[1]'
# "47"   (some non-zero count)

# Docker Compose stack is healthy
docker compose ps --format "table {{.Name}}\t{{.Status}}" | grep -E "aois|prometheus|grafana"
# aois         running
# prometheus   running
# grafana      running

# Python deps available
python3 -c "import clickhouse_connect; print('ok')" 2>/dev/null || echo "install: pip install clickhouse-connect"
```

---

## Learning Goals

By the end you will be able to:

- Explain why Prometheus has limits for analytical queries and what those limits are
- Deploy ClickHouse on k8s and confirm it is reachable from AOIS
- Design a ClickHouse schema for AOIS incident telemetry with the right engine and sort key
- Write AOIS code that dual-writes every incident analysis to ClickHouse
- Build materialized views that pre-aggregate cost-by-tier, latency percentiles, and accuracy-by-severity
- Query 100 million rows of AOIS telemetry in under a second
- Explain the ClickHouse storage architecture: MergeTree, parts, merges, and why inserts are always batched
- Know where Prometheus and ClickHouse coexist (they do) and where each owns its domain

---

## The Problem This Solves

Prometheus answers: "what is AOIS doing right now?" It stores time-series data — counters, gauges, histograms — and answers range queries over a sliding window (last 5 minutes, last 24 hours). It is excellent at alerting.

Prometheus cannot answer: "which incident type cost the most money last month?" or "what was the p95 analysis latency for P1 incidents routed to Groq in March?" These are analytical queries across large, historical, multi-dimensional datasets. PromQL is not built for them.

In v16 you set up Prometheus and Grafana. In v16.5 you add a second layer that Prometheus was never designed to be: a columnar analytical database that stores every AOIS incident row, forever, compresses it aggressively, and answers analytical queries in milliseconds.

The pattern: **Prometheus for real-time alerting. ClickHouse for analytics, audit, and cost attribution.**

They are not competitors. A production AI system needs both.

---

## What ClickHouse Is

ClickHouse is an open-source columnar database management system built for analytical queries over large datasets. "Columnar" means data is stored column by column rather than row by row.

### Row store vs Column store

Row store (Postgres):
```
[id=1, model="claude", cost=0.016, latency=1243]
[id=2, model="groq",   cost=0.000001, latency=220]
[id=3, model="claude", cost=0.016, latency=1187]
```

Column store (ClickHouse):
```
id:      [1, 2, 3, ...]
model:   ["claude", "groq", "claude", ...]
cost:    [0.016, 0.000001, 0.016, ...]
latency: [1243, 220, 1187, ...]
```

When you run `SELECT SUM(cost) FROM incidents WHERE model='claude'`, a row store reads every full row to find the cost column. A column store reads only the `model` column (to filter) and the `cost` column (to sum) — it skips every other column entirely. On a table with 50 columns and 100 million rows, this is the difference between 2 seconds and 20 milliseconds.

### Why ClickHouse Specifically

ClickHouse is used by Cloudflare (processes 6M events/second), Uber, GitLab, Contentsquare, and ByteDance for exactly this workload: high-volume, high-cardinality, analytical queries over time-series event data. It is the fastest open-source solution for this problem class. It compresses columnar data aggressively (LZ4 by default, ZSTD optional) — a 100GB raw dataset typically compresses to 5–10GB.

---

## The MergeTree Engine

Almost every ClickHouse table uses the **MergeTree** engine family. Understanding MergeTree is understanding ClickHouse.

When you insert rows, ClickHouse writes them as immutable **parts** — small, sorted files on disk. In the background, ClickHouse **merges** parts into larger ones, applying deduplication, pre-aggregation, and sorting as it goes. This makes inserts extremely fast (no random I/O) and queries fast (sorted parts enable range pruning).

```
INSERT 1000 rows → part_001 (sorted, compressed)
INSERT 1000 rows → part_002 (sorted, compressed)
...background merge...
part_001 + part_002 → part_merged (larger, still sorted, more compressed)
```

**Sort key matters enormously.** If your queries always filter on `(model, severity, created_at)`, define the sort key in that order. ClickHouse skips parts whose key range does not intersect the query — this is called **primary key skipping** and is why analytical queries return in milliseconds.

### The `toStartOfHour` pattern

ClickHouse's `toStartOfHour(created_at)` and similar functions are used in materialized views to bucket time. Instead of storing every event timestamp, you store the hour bucket — pre-aggregating costs and counts per hour. Dashboard queries read 720 rows (30 days × 24 hours) instead of millions of individual events.

---

## Deploying ClickHouse

### Local development (Docker Compose)

Add to `docker-compose.yml`:

```yaml
  clickhouse:
    image: clickhouse/clickhouse-server:24.3
    ports:
      - "8123:8123"   # HTTP interface
      - "9000:9000"   # Native protocol
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    environment:
      CLICKHOUSE_DB: aois
      CLICKHOUSE_USER: aois
      CLICKHOUSE_PASSWORD: aois_ch_pass
    ulimits:
      nofile:
        soft: 262144
        hard: 262144
    healthcheck:
      test: ["CMD", "clickhouse-client", "--query", "SELECT 1"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  clickhouse_data:
```

```bash
docker compose up -d clickhouse
# [+] Running 1/1
#  ✔ Container clickhouse  Started

# Verify
curl -s 'http://localhost:8123/?query=SELECT+version()'
# 24.3.x.x
```

### k8s deployment (Hetzner cluster)

```yaml
# k8s/clickhouse/clickhouse-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: clickhouse
  namespace: aois
spec:
  replicas: 1
  selector:
    matchLabels:
      app: clickhouse
  template:
    metadata:
      labels:
        app: clickhouse
    spec:
      containers:
      - name: clickhouse
        image: clickhouse/clickhouse-server:24.3
        ports:
        - containerPort: 8123
        - containerPort: 9000
        env:
        - name: CLICKHOUSE_DB
          value: aois
        - name: CLICKHOUSE_USER
          value: aois
        - name: CLICKHOUSE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: aois-secrets
              key: CLICKHOUSE_PASSWORD
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        volumeMounts:
        - name: clickhouse-data
          mountPath: /var/lib/clickhouse
      volumes:
      - name: clickhouse-data
        emptyDir: {}   # use PVC in production
---
apiVersion: v1
kind: Service
metadata:
  name: clickhouse
  namespace: aois
spec:
  selector:
    app: clickhouse
  ports:
  - name: http
    port: 8123
  - name: native
    port: 9000
```

```bash
sudo kubectl apply -f k8s/clickhouse/ --kubeconfig /etc/rancher/k3s/k3s.yaml
# deployment.apps/clickhouse created
# service/clickhouse created

sudo kubectl get pods -n aois -l app=clickhouse --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                          READY   STATUS    RESTARTS
# clickhouse-xxxxxxxxxx-xxxxx   1/1     Running   0
```

---

## Schema Design

```sql
-- clickhouse/schema.sql
-- Connect: clickhouse-client --host localhost --user aois --password aois_ch_pass --database aois

CREATE TABLE IF NOT EXISTS incident_telemetry
(
    -- Identity
    request_id      String,
    incident_id     String,

    -- Routing
    model           LowCardinality(String),   -- LowCardinality: for columns with <10k distinct values
    tier            LowCardinality(String),   -- 'premium', 'standard', 'fast', 'local'
    severity        LowCardinality(String),   -- 'P1', 'P2', 'P3', 'P4'

    -- Economics
    input_tokens    UInt32,
    output_tokens   UInt32,
    cost_usd        Float64,
    cache_hit       UInt8,                    -- 0 or 1 (ClickHouse has no bool)

    -- Performance
    latency_ms      UInt32,

    -- Quality
    confidence      Float32,
    pii_detected    UInt8,

    -- Time — partition key: data splits into monthly files, old months cheap to drop
    created_at      DateTime

) ENGINE = MergeTree()
  PARTITION BY toYYYYMM(created_at)
  ORDER BY (model, severity, created_at)   -- sort key: matches most query patterns
  TTL created_at + INTERVAL 1 YEAR        -- auto-drop rows older than 1 year
  SETTINGS index_granularity = 8192;
```

### Why these type choices

- **`LowCardinality(String)`**: for columns with few distinct values (model, tier, severity). ClickHouse uses dictionary encoding — the column stores integer indices instead of repeated strings. Queries on LowCardinality columns are 2–3x faster.
- **`UInt8` for booleans**: ClickHouse does not have a native bool. UInt8 with values 0/1 is the idiomatic choice.
- **`PARTITION BY toYYYYMM(created_at)`**: monthly partitions. To drop all data older than 6 months: `ALTER TABLE incident_telemetry DROP PARTITION '202309'` — instantaneous, no full table scan.
- **`ORDER BY (model, severity, created_at)`**: queries that filter on `model` and `severity` skip most parts entirely. The last key in the ORDER BY (created_at) ensures time-range queries are efficient too.

Apply the schema:

```bash
clickhouse-client --host localhost --user aois --password aois_ch_pass \
  --database aois --queries-file clickhouse/schema.sql
# (no output on success)

# Verify
clickhouse-client --host localhost --user aois --password aois_ch_pass \
  --database aois --query "DESCRIBE incident_telemetry"
# request_id     String
# incident_id    String
# model          LowCardinality(String)
# ...
```

---

## ▶ STOP — do this now

Create the table and insert 5 test rows to confirm the schema works:

```sql
INSERT INTO aois.incident_telemetry VALUES
  ('req-001', 'inc-001', 'claude-haiku-4-5-20251001', 'premium', 'P1', 450, 120, 0.00042, 0, 1243, 0.92, 0, now()),
  ('req-002', 'inc-001', 'groq/llama-3.1-8b-instant', 'fast',    'P3', 200,  80, 0.000001, 0, 218, 0.75, 0, now()),
  ('req-003', 'inc-002', 'claude-haiku-4-5-20251001', 'premium', 'P2', 430, 110, 0.00039, 0, 1189, 0.88, 1, now()),
  ('req-004', 'inc-003', 'groq/llama-3.1-8b-instant', 'fast',    'P3', 210,  75, 0.000001, 1, 11,  0.75, 0, now()),
  ('req-005', 'inc-004', 'claude-haiku-4-5-20251001', 'premium', 'P1', 460, 115, 0.00043, 0, 1312, 0.95, 0, now());
```

```bash
clickhouse-client --host localhost --user aois --password aois_ch_pass \
  --database aois \
  --query "SELECT model, severity, cost_usd, latency_ms FROM incident_telemetry ORDER BY created_at"
# claude-haiku-4-5-20251001  P1  0.00042   1243
# groq/llama-3.1-8b-instant  P3  0.000001  218
# claude-haiku-4-5-20251001  P2  0.00039   1189
# groq/llama-3.1-8b-instant  P3  0.000001  11
# claude-haiku-4-5-20251001  P1  0.00043   1312
```

---

## Dual-Writing from AOIS

Add a ClickHouse writer to the AOIS pipeline. Every analysis call writes a row:

```python
# clickhouse/writer.py
import clickhouse_connect
import os
from datetime import datetime


def get_client() -> clickhouse_connect.driver.Client:
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "aois"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "aois_ch_pass"),
        database=os.getenv("CLICKHOUSE_DB", "aois"),
    )


_client: clickhouse_connect.driver.Client | None = None


def _get() -> clickhouse_connect.driver.Client:
    global _client
    if _client is None:
        _client = get_client()
    return _client


def write_incident(
    *,
    request_id: str,
    incident_id: str,
    model: str,
    tier: str,
    severity: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    cache_hit: bool,
    latency_ms: int,
    confidence: float,
    pii_detected: bool,
) -> None:
    """Fire-and-forget write — never blocks the API response."""
    try:
        _get().insert(
            "incident_telemetry",
            [[
                request_id, incident_id, model, tier, severity,
                input_tokens, output_tokens, cost_usd,
                int(cache_hit), latency_ms, confidence, int(pii_detected),
                datetime.utcnow(),
            ]],
            column_names=[
                "request_id", "incident_id", "model", "tier", "severity",
                "input_tokens", "output_tokens", "cost_usd",
                "cache_hit", "latency_ms", "confidence", "pii_detected",
                "created_at",
            ],
        )
    except Exception as e:
        # Log but never raise — ClickHouse write failure must not block the API
        import logging
        logging.getLogger("clickhouse").warning("ClickHouse write failed: %s", e)
```

Wire it into `main.py` in the `analyze()` function, after the LLM call returns:

```python
# At the end of analyze(), after response is parsed:
from clickhouse.writer import write_incident
import uuid

write_incident(
    request_id=str(uuid.uuid4()),
    incident_id=log_text[:32],     # or a real incident ID if you have one
    model=model_used,
    tier=tier,
    severity=result.severity,
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    cost_usd=cost_usd,
    cache_hit=False,
    latency_ms=latency_ms,
    confidence=result.confidence,
    pii_detected=False,
)
```

---

## Materialized Views

Materialized views in ClickHouse are not like Postgres materialized views. In ClickHouse, a materialized view is a **trigger**: when rows are inserted into the source table, the view's query runs on those rows and the result is appended to a target table. The target table always has fresh aggregated data — no manual refresh.

### Cost by tier and hour

```sql
-- clickhouse/views.sql

-- Target table for cost aggregation
CREATE TABLE IF NOT EXISTS cost_by_tier_hourly
(
    hour        DateTime,
    tier        LowCardinality(String),
    model       LowCardinality(String),
    total_cost  Float64,
    call_count  UInt64,
    cache_hits  UInt64
) ENGINE = SummingMergeTree()
  ORDER BY (hour, tier, model);

-- Materialized view: triggers on incident_telemetry inserts
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cost_by_tier
TO cost_by_tier_hourly
AS SELECT
    toStartOfHour(created_at) AS hour,
    tier,
    model,
    sum(cost_usd)             AS total_cost,
    count()                   AS call_count,
    sum(cache_hit)            AS cache_hits
FROM incident_telemetry
GROUP BY hour, tier, model;


-- Target table for latency percentiles
CREATE TABLE IF NOT EXISTS latency_by_severity_hourly
(
    hour            DateTime,
    severity        LowCardinality(String),
    p50_ms          Float64,
    p95_ms          Float64,
    p99_ms          Float64,
    sample_count    UInt64
) ENGINE = AggregatingMergeTree()
  ORDER BY (hour, severity);

-- Materialized view for latency
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_latency_by_severity
TO latency_by_severity_hourly
AS SELECT
    toStartOfHour(created_at)       AS hour,
    severity,
    quantile(0.50)(latency_ms)      AS p50_ms,
    quantile(0.95)(latency_ms)      AS p95_ms,
    quantile(0.99)(latency_ms)      AS p99_ms,
    count()                         AS sample_count
FROM incident_telemetry
GROUP BY hour, severity;
```

```bash
clickhouse-client --host localhost --user aois --password aois_ch_pass \
  --database aois --queries-file clickhouse/views.sql
# (no output on success)

# Verify the views exist
clickhouse-client --host localhost --user aois --password aois_ch_pass \
  --database aois --query "SHOW TABLES"
# cost_by_tier_hourly
# incident_telemetry
# latency_by_severity_hourly
# mv_cost_by_tier
# mv_latency_by_severity
```

---

## ▶ STOP — do this now

Insert 1000 synthetic rows and query the materialized views:

```python
# clickhouse/generate_data.py
"""Generate 1000 realistic AOIS incident rows for ClickHouse demo."""
import random
import uuid
from datetime import datetime, timedelta
import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

client = clickhouse_connect.get_client(
    host=os.getenv("CLICKHOUSE_HOST", "localhost"),
    username=os.getenv("CLICKHOUSE_USER", "aois"),
    password=os.getenv("CLICKHOUSE_PASSWORD", "aois_ch_pass"),
    database=os.getenv("CLICKHOUSE_DB", "aois"),
)

MODELS = [
    ("claude-haiku-4-5-20251001", "premium", 0.00040),
    ("groq/llama-3.1-8b-instant", "fast",    0.000001),
    ("claude-sonnet-4-6",         "premium", 0.0120),
]
SEVERITIES = ["P1", "P2", "P3", "P4"]
SEVERITY_WEIGHTS = [0.05, 0.20, 0.50, 0.25]

rows = []
base_time = datetime.utcnow() - timedelta(days=30)
for i in range(1000):
    model, tier, base_cost = random.choice(MODELS)
    severity = random.choices(SEVERITIES, SEVERITY_WEIGHTS)[0]
    cache_hit = 1 if random.random() < 0.35 else 0
    cost = 0.0 if cache_hit else base_cost * random.uniform(0.8, 1.2)
    latency = random.randint(5, 30) if cache_hit else (
        random.randint(800, 2000) if "claude" in model else random.randint(150, 350)
    )
    rows.append([
        str(uuid.uuid4()),
        f"INC-{i:04d}",
        model, tier, severity,
        random.randint(200, 600),
        random.randint(80, 200),
        cost,
        cache_hit,
        latency,
        random.uniform(0.65, 0.99),
        1 if random.random() < 0.08 else 0,
        base_time + timedelta(hours=random.randint(0, 720)),
    ])

client.insert("incident_telemetry", rows, column_names=[
    "request_id", "incident_id", "model", "tier", "severity",
    "input_tokens", "output_tokens", "cost_usd", "cache_hit",
    "latency_ms", "confidence", "pii_detected", "created_at",
])
print(f"Inserted {len(rows)} rows")
```

```bash
python3 clickhouse/generate_data.py
# Inserted 1000 rows

# Query the materialized view — no scan of 1000 rows, reads the pre-aggregated target
clickhouse-client --host localhost --user aois --password aois_ch_pass \
  --database aois --query "
SELECT tier, model,
       round(sum(total_cost), 6) AS total_cost_usd,
       sum(call_count)           AS calls,
       sum(cache_hits)           AS cache_hits
FROM cost_by_tier_hourly
GROUP BY tier, model
ORDER BY total_cost_usd DESC
FORMAT PrettyCompact"

# ┌─tier────┬─model────────────────────┬─total_cost_usd─┬─calls─┬─cache_hits─┐
# │ premium │ claude-sonnet-4-6        │       2.482100 │   164 │         59 │
# │ premium │ claude-haiku-4-5-...     │       0.132400 │   333 │        116 │
# │ fast    │ groq/llama-3.1-8b-instant│       0.000503 │   503 │        175 │
# └─────────┴──────────────────────────┴────────────────┴───────┴────────────┘
```

Claude Sonnet is 5000x more expensive per call than Groq. This table makes that obvious and persistent. At scale, this answers: "which team is burning budget on Sonnet for P3 incidents?" — a question that saves real money.

---

## Analytical Queries

These are the queries Prometheus cannot answer. Run them against your 1000-row dataset:

```sql
-- Cost breakdown by severity: which incident type costs most?
SELECT
    severity,
    count()                           AS incidents,
    round(sum(cost_usd), 4)           AS total_cost_usd,
    round(avg(cost_usd) * 1000, 4)   AS avg_cost_per_call_millicents
FROM aois.incident_telemetry
GROUP BY severity
ORDER BY total_cost_usd DESC;

-- Cache efficiency: what fraction of calls were cached, by tier?
SELECT
    tier,
    countIf(cache_hit = 1)  AS cached,
    count()                 AS total,
    round(100.0 * countIf(cache_hit = 1) / count(), 1) AS hit_rate_pct
FROM aois.incident_telemetry
GROUP BY tier;

-- Latency percentiles over the past 7 days, by model
SELECT
    model,
    quantile(0.50)(latency_ms) AS p50,
    quantile(0.95)(latency_ms) AS p95,
    quantile(0.99)(latency_ms) AS p99,
    count()                    AS samples
FROM aois.incident_telemetry
WHERE created_at >= now() - INTERVAL 7 DAY
GROUP BY model
ORDER BY p99 DESC;

-- PII detection rate by model — are some log sources dirtier than others?
SELECT
    model,
    countIf(pii_detected = 1) AS pii_calls,
    count()                   AS total_calls,
    round(100.0 * countIf(pii_detected = 1) / count(), 2) AS pii_rate_pct
FROM aois.incident_telemetry
GROUP BY model;
```

Run all four:

```bash
clickhouse-client --host localhost --user aois --password aois_ch_pass \
  --database aois \
  --query "SELECT severity, count() AS incidents, round(sum(cost_usd),4) AS total_cost FROM incident_telemetry GROUP BY severity ORDER BY total_cost DESC FORMAT PrettyCompact"
```

---

## Retention Tiers

In production, not all data has the same value. Recent data (last 7 days) is queried constantly — alerting, debugging, dashboards. Older data is queried rarely — audits, trend analysis. ClickHouse supports tiered storage via multiple disk volumes.

For AOIS on a single Hetzner node, apply a simple TTL policy:

```sql
-- Data older than 90 days moves to a compressed cold partition
-- Data older than 1 year is deleted automatically (set in the CREATE TABLE TTL clause)

-- To change TTL on an existing table:
ALTER TABLE aois.incident_telemetry
MODIFY TTL created_at + INTERVAL 1 YEAR;

-- To check TTL configuration:
SELECT name, ttl FROM system.tables WHERE name='incident_telemetry';
```

In a multi-disk setup (e.g., NVMe for hot, HDD for cold, S3 for archive):

```xml
<!-- /etc/clickhouse-server/config.d/storage.xml -->
<storage_configuration>
  <disks>
    <default>  <path>/var/lib/clickhouse/</path> </default>
    <cold_disk><path>/mnt/hdd/clickhouse/</path> </cold_disk>
  </disks>
  <policies>
    <tiered>
      <volumes>
        <hot>  <disk>default</disk>   <max_data_part_size_bytes>1073741824</max_data_part_size_bytes> </hot>
        <cold> <disk>cold_disk</disk> </cold>
      </volumes>
      <move_factor>0.2</move_factor>
    </tiered>
  </policies>
</storage_configuration>
```

Parts larger than 1GB automatically move to the cold disk. With S3-compatible storage (Hetzner Object Storage), parts older than 90 days move to object storage — effectively infinite retention at object storage prices.

---

## Grafana Integration

ClickHouse has an official Grafana plugin. Install it in your Grafana instance, then build dashboards from ClickHouse instead of (or alongside) Prometheus.

```bash
# In your Grafana container:
grafana-cli plugins install grafana-clickhouse-datasource
# Restart Grafana to load the plugin
```

Example Grafana panel query (hourly cost trend):

```sql
SELECT
    toStartOfHour(created_at)      AS time,
    sum(cost_usd)                  AS cost_usd
FROM aois.incident_telemetry
WHERE $__timeFilter(created_at)
GROUP BY time
ORDER BY time
```

The `$__timeFilter(created_at)` macro is replaced by Grafana with a WHERE clause matching the dashboard time range — same pattern as PromQL's `[$__range]` variable.

---

## ▶ STOP — do this now

Answer these three questions from ClickHouse, without touching Prometheus:

1. What is the total cost of all P1 incidents in the last 30 days?
2. What is the p99 latency for Groq calls vs Claude calls?
3. What fraction of calls were cache hits?

Write the three queries and record the results. Then ask: can you answer these questions in Prometheus? Try writing the PromQL equivalent. This is the moment you feel the limit.

---

## Prometheus vs ClickHouse: The Right Division

This is the question that always comes up. The answer is not "one replaces the other."

| | Prometheus | ClickHouse |
|---|---|---|
| **What it stores** | Pre-aggregated time-series (counters, histograms) | Raw event rows |
| **Query language** | PromQL — range vectors, functions | SQL — full analytical power |
| **Retention** | Short (weeks, months) | Long (years) |
| **Granularity** | Scrape interval (15s) | Per-event |
| **Cardinality** | Limited — 100k+ unique label combinations causes OOM | Unlimited |
| **Alerting** | First-class — AlertManager integration | Not designed for it |
| **Cost attribution** | Hard — aggregations lose per-call detail | Easy — every row has cost |
| **When to use** | Real-time monitoring, alerting, dashboards | Analytics, audit, cost, trend |

Keep Prometheus for alerts (`AOISHighAnalysisLatency`, `AOISPipelineStalled`). Add ClickHouse for analytics (monthly cost reports, model performance comparisons, PII detection trends). They coexist on the same cluster and answer different questions.

---

## Common Mistakes

### 1. Inserting row by row

```python
# Wrong — 1000 individual inserts, each with network round-trip overhead
for row in rows:
    client.insert("incident_telemetry", [row], column_names=...)

# Correct — one insert, batch of rows
client.insert("incident_telemetry", rows, column_names=...)
```

ClickHouse is designed for batch inserts. Row-by-row inserts create one part per insert — the merge background job cannot keep up, and the "too many parts" error appears:

```
DB::Exception: Too many parts (300). Merges are processing significantly slower than inserts.
```

Always batch. For high-frequency writes from AOIS, collect rows in a list and flush every 100 rows or every 5 seconds, whichever comes first.

---

### 2. Using `ReplacingMergeTree` without understanding eventual consistency

`ReplacingMergeTree` deduplicates rows with the same ORDER BY key — but only after merges run. Between insert and merge, duplicates exist. If you read immediately after insert, you see duplicates:

```sql
-- Add FINAL to force deduplication at query time (slower but consistent)
SELECT * FROM incident_telemetry FINAL WHERE request_id = 'req-001';
```

For AOIS audit telemetry, use plain `MergeTree` — each `request_id` is unique by design (UUID), so deduplication is not needed.

---

### 3. Wrong ORDER BY for query patterns

```sql
-- Your ORDER BY is:
ORDER BY (created_at, model, severity)

-- But your queries always filter on model first:
WHERE model = 'claude-haiku-...' AND created_at > now() - INTERVAL 7 DAY
```

ClickHouse can only skip parts based on a prefix of the ORDER BY key. If `created_at` is first, filtering on `model` alone reads all parts — no skipping. Put the most selective filter columns first in the ORDER BY.

Fix: `ORDER BY (model, severity, created_at)` — now a `WHERE model=...` query skips irrelevant parts efficiently.

---

## Troubleshooting

### `Connection refused` on port 8123

```bash
curl http://localhost:8123/ping
# curl: (7) Failed to connect to localhost port 8123
```

ClickHouse is not running or bound to a different address.

```bash
docker compose ps clickhouse
# If status is "exited", check logs:
docker compose logs clickhouse | tail -20
# Look for: "listen_host: [::1]" — binding to IPv6 loopback only
# Fix: add listen_host 0.0.0.0 to ClickHouse config, or use docker compose restart
```

---

### Materialized view not populating

```bash
clickhouse-client --query "SELECT count() FROM aois.cost_by_tier_hourly"
# 0
```

Materialized views in ClickHouse only process rows inserted *after* the view was created. They do not backfill existing data. To populate from existing rows:

```sql
INSERT INTO cost_by_tier_hourly
SELECT
    toStartOfHour(created_at) AS hour,
    tier, model,
    sum(cost_usd), count(), sum(cache_hit)
FROM incident_telemetry
GROUP BY hour, tier, model;
```

---

### `Not enough memory` on large aggregation

ClickHouse processes aggregations in memory. On the 512Mi-limited Hetzner node, a GROUP BY over millions of rows may hit the memory limit.

```sql
-- Add SETTINGS to limit memory and enable external aggregation to disk
SELECT ... FROM incident_telemetry
GROUP BY ...
SETTINGS max_memory_usage = 1000000000,  -- 1GB
         group_by_overflow_mode = 'any'; -- approximate results, stays in memory
```

For AOIS at v16.5 scale (thousands, not millions), this is unlikely to trigger.

---

## Connection to Later Phases

### To Phase 7 (v20+, Agents)
When AOIS agents make 10–15 LLM calls per incident investigation, per-incident cost attribution requires ClickHouse. A GROUP BY on `incident_id` across 15 rows gives you "this investigation cost $0.04". That query runs in Postgres too, but ClickHouse handles it at the scale of 10,000 simultaneous investigations without degradation.

### To v23.5 (Agent Evaluation)
Agent evaluation datasets — the 50-incident golden set — are stored and queried against ClickHouse telemetry. "For incidents labeled P1, what fraction did the agent correctly classify?" is a ClickHouse GROUP BY query, not a Prometheus query.

### To v34.5 (AI SRE Capstone)
The AI-specific SLOs in the capstone — model accuracy SLO, hallucination rate SLO, cost SLO — are monitored via ClickHouse materialized views. Prometheus fires the alert; ClickHouse provides the 30-day trend that the post-incident report requires.

---


## Build-It-Blind Challenge

Close the notes. From memory: write the ClickHouse `incidents` table schema — correct MergeTree engine, partition by month, order by timestamp and severity, columns for all AOIS analysis fields including model, tier, cost, latency, tokens. 20 minutes.

```sql
SHOW CREATE TABLE aois.incidents;
-- Must show MergeTree, correct PARTITION BY, ORDER BY
```

---

## Failure Injection

Create the table with the wrong engine and observe the query difference:

```sql
CREATE TABLE aois.incidents_wrong (
  timestamp DateTime,
  severity String,
  cost Float32
) ENGINE = Log;   -- wrong engine, no ORDER BY

INSERT INTO aois.incidents_wrong SELECT now(), 'P1', 0.016 FROM numbers(1000000);

-- Compare query times:
SELECT severity, count() FROM aois.incidents GROUP BY severity;
SELECT severity, count() FROM aois.incidents_wrong GROUP BY severity;
```

The MergeTree query should be 10-100x faster. If it is not, check the ORDER BY — ClickHouse uses it for physical data ordering, not just sorting.

---

## Osmosis Check

1. Prometheus (v16) stores metrics with 15-second resolution. ClickHouse stores every incident with full metadata. Which do you query to answer "what was AOIS p99 latency at 2:47am on Tuesday"? Which do you query to answer "which log pattern has the highest P1 rate this month"?
2. ClickHouse's MergeTree engine merges data parts in the background. During a heavy write burst (10,000 incidents in 60 seconds), query latency increases temporarily. What is happening internally and which ClickHouse system table shows you the merge status?

---

## Mastery Checkpoint

1. Deploy ClickHouse via Docker Compose. Confirm `SELECT version()` returns `24.x`. Create the `incident_telemetry` table and verify the HNSW-equivalent: confirm `DESCRIBE incident_telemetry` shows `LowCardinality(String)` for model, tier, and severity.

2. Insert the 5 test rows manually. Query them back and confirm the ORDER BY (model, severity, created_at) is reflected in the output ordering.

3. Run `generate_data.py` to insert 1000 rows. Query: total cost grouped by tier. Confirm Groq is orders of magnitude cheaper than Claude per call.

4. Create both materialized views. Insert 100 more rows. Query `cost_by_tier_hourly` — confirm the new rows are reflected without any manual refresh.

5. Run the four analytical queries from the "Analytical Queries" section. Record the answers. Then write the PromQL equivalent of the "cost by severity" query and confirm it either cannot be expressed or requires cardinality that Prometheus would struggle with.

6. Add `write_incident()` to `main.py`. Send 10 requests through AOIS and confirm they appear in `incident_telemetry` via `SELECT count() FROM aois.incident_telemetry`.

7. Explain to a non-technical person why you use two databases (Prometheus and ClickHouse) instead of one, using a supermarket analogy: Prometheus is the store's live inventory scanner; ClickHouse is the annual stocktake report.

8. Explain to a junior engineer the difference between a Postgres materialized view (point-in-time snapshot, manual refresh) and a ClickHouse materialized view (insert trigger, always fresh). When would each be correct?

9. Explain to a senior engineer why `ORDER BY (model, severity, created_at)` is better than `ORDER BY created_at` for AOIS query patterns, referencing part skipping. What is the worst-case query for the current ORDER BY — the one that forces a full scan?

**The mastery bar:** you can answer any AOIS cost, latency, or quality question for any time range in under 1 second, and explain to a finance team exactly how much each LLM tier cost them last month — from ClickHouse, without touching Prometheus.

---

## 4-Layer Tool Understanding

### ClickHouse

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | You need to ask questions like "which incident type cost the most last month?" — questions that require scanning millions of rows across many columns. ClickHouse stores data column-by-column so those scans run in milliseconds, not minutes. |
| **System Role** | Where does it sit in AOIS? | As a parallel write target alongside the API response. Every `analyze()` call writes a row to ClickHouse (fire-and-forget, never blocks the response). Grafana dashboards and analytical queries read from ClickHouse; Prometheus handles real-time alerting. |
| **Technical** | What is it, precisely? | A columnar OLAP database using the MergeTree engine family. Inserts write immutable parts; background merges compact them. LowCardinality encoding, LZ4 compression, and primary key skipping combine to make analytical queries over billions of rows return in under a second. Materialized views are insert triggers that maintain pre-aggregated summary tables. |
| **Remove it** | What breaks, and how fast? | Remove ClickHouse → lose per-event analytical history. Prometheus still alerts in real time. But monthly cost reports, model performance trends, and per-incident cost attribution become impossible without rebuilding from logs. Discovery: the next quarterly cost review has no data. Detection: immediately if you try to run the analytical queries. Recovery: rebuild from logs (slow) or accept the data gap. |

### MergeTree (ClickHouse Engine)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Databases need to handle lots of writes without slowing down reads. MergeTree does this by writing small files quickly and merging them in the background — like a librarian who accepts returned books in any order and re-shelves them properly later. |
| **System Role** | Where does it sit in AOIS? | It is the storage engine for the `incident_telemetry` table. Every write from AOIS creates or extends a part. Background merges maintain the sort order and apply TTL deletions automatically. |
| **Technical** | What is it, precisely? | An LSM-tree-inspired storage engine. Inserts produce sorted, immutable parts. Background merges combine parts, enforce ORDER BY sort order, apply TTL deletions, and optionally deduplicate (ReplacingMergeTree) or pre-aggregate (SummingMergeTree, AggregatingMergeTree). Primary key is a sparse index into the sorted parts — every 8192 rows (index_granularity) one index entry is stored. |
| **Remove it** | What breaks, and how fast? | MergeTree is the only viable engine for this workload — there is no alternative within ClickHouse for time-series event storage. The alternatives are different databases (Postgres for transactional, Prometheus for metrics). Choosing a wrong engine (e.g., Log) loses indexing and part merging, making queries linear scans. |
