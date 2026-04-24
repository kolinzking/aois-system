-- ClickHouse schema for AOIS incident telemetry (v16.5)
-- Connect: clickhouse-client --host localhost --user aois --password aois_ch_pass --database aois

CREATE TABLE IF NOT EXISTS incident_telemetry
(
    request_id      String,
    incident_id     String,
    model           LowCardinality(String),
    tier            LowCardinality(String),
    severity        LowCardinality(String),
    input_tokens    UInt32,
    output_tokens   UInt32,
    cost_usd        Float64,
    cache_hit       UInt8,
    latency_ms      UInt32,
    confidence      Float32,
    pii_detected    UInt8,
    created_at      DateTime
) ENGINE = MergeTree()
  PARTITION BY toYYYYMM(created_at)
  ORDER BY (model, severity, created_at)
  TTL created_at + INTERVAL 1 YEAR
  SETTINGS index_granularity = 8192;
