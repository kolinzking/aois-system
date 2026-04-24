"""Generate 1000 realistic AOIS incident rows for ClickHouse exercises (v16.5)."""
import os
import random
import uuid
from datetime import datetime, timedelta

import clickhouse_connect
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
SEVERITIES   = ["P1", "P2", "P3", "P4"]
SEV_WEIGHTS  = [0.05, 0.20, 0.50, 0.25]

rows = []
base_time = datetime.utcnow() - timedelta(days=30)

for i in range(1000):
    model, tier, base_cost = random.choice(MODELS)
    severity  = random.choices(SEVERITIES, SEV_WEIGHTS)[0]
    cache_hit = 1 if random.random() < 0.35 else 0
    cost      = 0.0 if cache_hit else base_cost * random.uniform(0.8, 1.2)
    latency   = (
        random.randint(5, 30) if cache_hit
        else (random.randint(800, 2000) if "claude" in model else random.randint(150, 350))
    )
    rows.append([
        str(uuid.uuid4()),
        f"INC-{i:04d}",
        model, tier, severity,
        random.randint(200, 600),
        random.randint(80, 200),
        cost, cache_hit, latency,
        round(random.uniform(0.65, 0.99), 3),
        1 if random.random() < 0.08 else 0,
        base_time + timedelta(hours=random.randint(0, 720)),
    ])

client.insert("incident_telemetry", rows, column_names=[
    "request_id", "incident_id", "model", "tier", "severity",
    "input_tokens", "output_tokens", "cost_usd", "cache_hit",
    "latency_ms", "confidence", "pii_detected", "created_at",
])
print(f"Inserted {len(rows)} rows into incident_telemetry.")
