-- Materialized views for AOIS telemetry (v16.5)
-- Run after schema.sql

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

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_latency_by_severity
TO latency_by_severity_hourly
AS SELECT
    toStartOfHour(created_at)  AS hour,
    severity,
    quantile(0.50)(latency_ms) AS p50_ms,
    quantile(0.95)(latency_ms) AS p95_ms,
    quantile(0.99)(latency_ms) AS p99_ms,
    count()                    AS sample_count
FROM incident_telemetry
GROUP BY hour, severity;
