# v16 — OpenTelemetry: Making Every LLM Call Visible
⏱ **Estimated time: 4–6 hours**

*Phase 6 — Full SRE Observability Stack. This phase adds the instrumentation that turns AOIS from a black box into a system you can reason about under pressure.*

---

## What this version builds

v15 closed Phase 5 with six inference tiers. You can route by cost and speed. But you have no visibility into what is actually happening: which tier is slowest, which model is most expensive per incident, what latency the P99 user experiences, whether the OOMKilled analysis costs 10× more than the disk-pressure one.

Without observability, you are flying blind. This is what kills production AI systems: not wrong answers, but costs that spiral undetected, latency spikes that go unnoticed, one tier silently failing over to another and nobody knowing.

v16 instruments everything. Every `/analyze` call produces:
- A **trace** (Tempo) — the full span tree: HTTP request → AOIS handler → LLM call → response
- **Metrics** (Prometheus) — per-model latency histograms, token counts, cost counters, severity distribution
- **Logs** (Loki) — structured JSON per analysis with tier, model, severity, cost, duration

All three are unified in **Grafana**. One dashboard to answer: what is AOIS doing right now?

At the end of v16:
- 7-container stack running locally: AOIS + Redis + Postgres + OTel Collector + Prometheus + Grafana + Loki + Tempo
- Every LLM call emits OTel GenAI semantic convention spans
- Prometheus scrapes per-model latency histograms, token counters, cost counters
- Grafana pre-provisioned with datasources and AOIS dashboard
- The pipeline validated end-to-end: request → metric → Prometheus → Grafana

---

## Prerequisites

Verify before starting:

```bash
# Docker with Compose V2
docker compose version
# Expected: Docker Compose version v2.x.x

# All existing versions working
curl -s http://localhost:8000/health | python3 -m json.tool
# Expected: {"status": "ok", "tiers": [...]}

# Python OTel packages available (installed by requirements.txt)
python3 -c "import opentelemetry; print('OTel SDK', opentelemetry.__version__)"
# Expected: OTel SDK 1.x.x
```

---

## Learning Goals

By the end of v16 you will be able to:

- Explain the three pillars of observability — traces, metrics, logs — and what each answers
- Describe the OTel data pipeline: SDK → Collector → backend (Tempo/Prometheus/Loki)
- Read the OTel GenAI semantic convention spec and implement it correctly for LLM spans
- Configure an OTel Collector to fan out signals to multiple backends
- Mount a Prometheus `/metrics` endpoint on a FastAPI app
- Use Grafana to query across all three pillars simultaneously
- Diagnose the three most common OTel startup failures (permission errors, config parse errors, wrong paths)

---

## Part 1: The Three Pillars

Production systems are observable when you can answer any question about their behavior from their outputs alone — without having to add new code and redeploy. The three outputs are:

**Traces** answer "what happened in this specific request?" A trace is a tree of spans. The root span is the HTTP request. Child spans are: AOIS handler, sanitize_log, LLM call (groq), validate_output. Each span has a start time, duration, and key-value attributes. When a user reports "my analysis took 8 seconds," you find the trace and see exactly which span took 7.9 of those seconds.

**Metrics** answer "what is the overall behavior of the system?" A metric is a time series: latency histogram, request counter, cost gauge. Metrics are aggregated — they tell you that the p99 latency for the fast tier is 400ms, not which specific request was slow. Prometheus is the standard collection and query engine.

**Logs** answer "what did the system say happened?" Logs are the narrative. In AOIS, each analysis emits a structured JSON log line: `{"tier": "fast", "model": "groq/...", "severity": "P3", "cost_usd": 0.000001, "duration_s": 0.274}`. Loki aggregates and indexes logs by label so you can query them without full-text scan.

The key insight: all three are connected. A Grafana trace view links to the logs from the same time window. A log line contains the trace ID so you can jump from log to trace. A metric spike links to example traces from that spike. This is the unified observability model.

---

## Part 2: OpenTelemetry — One Standard to Rule All Three

Before OpenTelemetry (OTel), each observability backend had its own SDK. You instrumented your code with Jaeger SDK, then Zipkin SDK, then Datadog SDK. Three SDKs, three sets of code changes, all incompatible.

OTel is the W3C standard that unified everything:
- **One SDK** to instrument your code
- **One Collector** to receive, process, and fan out to any backend
- **One data format** (OTLP — OpenTelemetry Protocol) for all three signal types
- **Vendor-neutral** — switch from Tempo to Jaeger by changing the Collector config, not the app code

**OTel GenAI Semantic Conventions** are the standard attribute names for LLM calls:
- `gen_ai.system` — the inference system ("openai", "anthropic", "vertex_ai")
- `gen_ai.operation.name` — the operation ("chat", "embeddings", "completion")
- `gen_ai.request.model` — the model ID requested
- `gen_ai.response.model` — the model that actually served (may differ if load-balanced)
- `gen_ai.usage.input_tokens` — tokens consumed from the prompt
- `gen_ai.usage.output_tokens` — tokens in the generated response
- `gen_ai.client.token.usage` — the counter metric for tokens (input/output by type)
- `gen_ai.client.operation.duration` — the histogram metric for LLM call duration

These conventions mean any OTel-aware tool — Grafana, Datadog, Honeycomb, Langfuse — can render LLM telemetry without custom configuration. You emit once, all backends understand it.

---

## Part 3: The Data Pipeline

```
AOIS FastAPI app
    │
    │  OTLP gRPC (port 4317)
    ▼
OTel Collector (otelcol-contrib)
    │
    ├── traces  ──► Tempo  (port 4317 internal)
    ├── metrics ──► Prometheus exporter (port 8889)
    └── logs    ──► Loki   (port 3100)
                      │
Prometheus ───scrapes─┘
    │
    └──► Grafana (datasources: Prometheus, Loki, Tempo)
```

The Collector is the fan-out layer. The AOIS app sends one OTLP stream. The Collector splits it into three pipelines and routes each to the right backend. This means you can add a new backend (Datadog, Honeycomb, Jaeger) by adding one exporter to the Collector config — zero code changes in AOIS.

The Prometheus exporter in the Collector exposes metrics at `:8889` for Prometheus to scrape. AOIS also has its own `/metrics/` endpoint (prometheus-client) that Prometheus scrapes directly — this gives you HTTP-level metrics (request count, latency by endpoint) plus the custom LLM metrics.

---

## Part 4: Instrumenting the FastAPI App

Three instrumentation layers in `main.py`:

**1. OTel SDK setup** — creates TracerProvider and MeterProvider, configures OTLP exporters:

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

resource = Resource.create({"service.name": "aois", "service.version": "16"})
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://otelcol:4317", insecure=True))
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer("aois")
```

`BatchSpanProcessor` buffers spans and flushes them in batches — the right production pattern. `SimpleSpanProcessor` would flush synchronously on every span close, adding latency to every request.

**2. FastAPI auto-instrumentation** — creates spans for every HTTP request automatically:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)
```

This wraps every route handler. You get a span for `GET /health`, `POST /analyze`, etc. with HTTP status, method, route template as attributes. No per-route code needed.

**3. Per-LLM-call spans** — the custom GenAI semantic convention spans:

```python
with tracer.start_as_current_span(
    f"gen_ai.chat {model}",
    attributes={
        "gen_ai.system": "openai",
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": model,
        "aois.tier": tier,
        "aois.log_length": len(clean_log),
    },
) as span:
    t0 = time.perf_counter()
    result = _do_analyze(model, tier, messages, clean_log)
    duration_s = time.perf_counter() - t0
    span.set_attribute("aois.severity", result.severity)
    span.set_attribute("aois.cost_usd", result.cost_usd)
```

The context manager pattern (`with tracer.start_as_current_span`) is important: if `_do_analyze` raises, the span is still closed and the exception is recorded. The OTel SDK handles this automatically.

**4. Prometheus metrics** — custom counters and histograms scraped by Prometheus:

```python
from prometheus_client import Counter, Histogram, make_asgi_app

_prom_incidents = Counter("aois_incidents_total", "...", ["severity", "tier"])
_prom_llm_latency = Histogram("aois_llm_duration_ms", "...", ["model"], buckets=[100, 250, 500, 1000, 2000, 5000, 10000, 30000])
_prom_llm_cost = Counter("aois_llm_cost_usd_total", "...", ["model"])

app.mount("/metrics", make_asgi_app())
```

`make_asgi_app()` creates a WSGI-compatible Prometheus metrics endpoint. Mounting it at `/metrics` means Prometheus can scrape `http://aois:8000/metrics/` to get all custom metrics.

---

## ▶ STOP — do this now

Start the observability stack and generate traces:

```bash
# Start everything
docker compose up -d

# Wait for all 7 containers
docker compose ps
```

Expected (all STATUS = "Up"):
```
aois-system-aois-1         ...    Up    0.0.0.0:8000->8000/tcp
aois-system-grafana-1      ...    Up    0.0.0.0:3000->3000/tcp
aois-system-loki-1         ...    Up    0.0.0.0:3100->3100/tcp
aois-system-otelcol-1      ...    Up    0.0.0.0:4317-4318->4317-4318/tcp
aois-system-postgres-1     ...    Up    0.0.0.0:5432->5432/tcp
aois-system-prometheus-1   ...    Up    0.0.0.0:9090->9090/tcp
aois-system-redis-1        ...    Up    0.0.0.0:6379->6379/tcp
aois-system-tempo-1        ...    Up    0.0.0.0:3200->3200/tcp
```

Fire a test request:

```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled: container aois-api exceeded memory limit 512Mi, exit code 137", "tier": "fast"}' | python3 -m json.tool
```

Expected:
```json
{
    "summary": "...",
    "severity": "P1",
    "suggested_action": "...",
    "confidence": 0.95,
    "provider": "groq/llama-3.1-8b-instant",
    "cost_usd": 1e-06
}
```

Verify metrics are flowing:

```bash
curl -s http://localhost:8000/metrics/ | grep aois_incidents_total
```

Expected:
```
# HELP aois_incidents_total Total incidents analyzed
# TYPE aois_incidents_total counter
aois_incidents_total{severity="P1",tier="fast"} 1.0
```

Verify Prometheus scraped them:

```bash
curl -s "http://localhost:9090/api/v1/query?query=aois_incidents_total" | python3 -m json.tool
```

Expected: `"status": "success"` with a result containing `aois_incidents_total`.

Open Grafana: `http://localhost:3000` — you should see the AOIS dashboard pre-loaded under Dashboards → AOIS.

---

## Part 5: The OTel Collector Config

`otel/otelcol-config.yaml` defines the pipeline:

```yaml
receivers:
  otlp:
    protocols:
      grpc: {endpoint: 0.0.0.0:4317}
      http: {endpoint: 0.0.0.0:4318}

processors:
  batch:
    timeout: 5s
    send_batch_size: 512
  resource:
    attributes:
      - {key: service.namespace, value: aois, action: upsert}

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls: {insecure: true}
  prometheus:
    endpoint: 0.0.0.0:8889
  loki:
    endpoint: http://loki:3100/loki/api/v1/push

service:
  pipelines:
    traces:  {receivers: [otlp], processors: [batch, resource], exporters: [otlp/tempo]}
    metrics: {receivers: [otlp], processors: [batch, resource], exporters: [prometheus]}
    logs:    {receivers: [otlp], processors: [batch, resource], exporters: [loki]}
```

Key design decisions:

**`batch` processor**: buffers spans before exporting. Without it, every span close sends an HTTP request to Tempo. With batch, 512 spans are sent in one request every 5 seconds. Dramatically reduces network overhead at scale.

**`resource` processor**: adds `service.namespace=aois` to every signal. This lets you filter all AOIS signals in Grafana with one label, even when you have multiple services in the same Collector.

**`otlp/tempo`**: the `/tempo` suffix namespaces the exporter. You can have multiple OTLP exporters (e.g., `otlp/tempo` and `otlp/jaeger`) without collision.

**`prometheus` exporter**: exposes collected metrics as a Prometheus scrape target at `:8889`. Prometheus pulls from this endpoint every 15 seconds. The Collector acts as a metrics aggregation point — you could add 10 more services sending OTLP metrics and Prometheus only needs one scrape target.

---

## ▶ STOP — do this now

Generate traffic across multiple tiers and inspect in Prometheus:

```bash
# P1/P2 incidents → premium tier (Claude)
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "Node worker-3 NotReady: kubelet stopped posting node status 8m ago", "tier": "premium"}' \
  | python3 -m json.tool

# P3/P4 incidents → fast tier (Groq)
for log in \
  "Disk usage at 94% on /var/lib/docker, inode exhaustion imminent" \
  "TLS certificate for api.prod.company.com expires in 3 days" \
  "Redis: used_memory 7.8GB of 8GB maxmemory, evicting keys"; do
  curl -s -X POST http://localhost:8000/analyze \
    -H "Content-Type: application/json" \
    -d "{\"log\": \"$log\", \"tier\": \"fast\"}" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['severity'], r['provider'])"
done
```

Then query Prometheus:

```bash
# Per-tier incident count
curl -s "http://localhost:9090/api/v1/query?query=aois_incidents_total" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); [print(m['metric']['severity'], m['metric']['tier'], m['value'][1]) for m in r['data']['result']]"
```

Expected: rows showing severity + tier + count for each combination.

```bash
# p99 latency per model
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,+rate(aois_llm_duration_ms_bucket[5m]))" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); [print(m['metric'].get('model','?'), round(float(m['value'][1]),0), 'ms') for m in r['data']['result']]"
```

Expected: model names with latency values. Groq should be 200–400ms. Claude/premium 2000–12000ms.

---

## Part 6: Grafana — Reading the Dashboard

Open `http://localhost:3000`. The AOIS dashboard (pre-provisioned) shows:

**Requests/min** (top left): rate of `/analyze` calls. Use this to spot traffic spikes.

**P99 Latency** (top right): the 99th percentile user experience. If this spikes above 5000ms, your premium tier is the culprit.

**LLM Tokens In/Out** (middle left): raw token consumption per model. Watch this for cost forecasting: if input tokens double, your cost doubles.

**Cost/min** (middle right): the number that matters for the CFO conversation. 1 call at $0.016 (Claude) vs 1000 calls at $0.000001 (Groq) — same cost. When auto_route is working correctly, you should see the expensive model handling low volume.

**LLM Latency by Model (p99)** (bottom left): which model is your bottleneck? This is where you discover that NIM is actually slower than Groq at p99.

**Severity Distribution** (bottom right): pie chart of P1/P2/P3/P4 incidents in the last hour. If P1 > 20%, something systemic is wrong in your production environment.

**Recent AOIS Logs** (bottom): the structured JSON log stream from Loki. Click any log line to see the full fields. Click the trace ID (if present) to jump directly to the trace in Tempo.

To navigate to traces manually: Explore → Tempo → search by service name "aois" → click any trace → see the span tree.

---

## ▶ STOP — do this now

Inspect a trace end-to-end:

```bash
# Fire one request
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "Consumer lag: topic aois-logs partition 0 lag=142000", "tier": "fast"}' \
  | python3 -m json.tool
```

In Grafana:
1. Go to Explore (compass icon)
2. Select datasource: Tempo
3. Query type: Search
4. Service name: aois
5. Click "Run query"
6. Click the trace that just appeared
7. Expand the span tree — you should see the FastAPI HTTP span as root, with the `gen_ai.chat` span as a child

In the `gen_ai.chat` span attributes, verify:
- `gen_ai.operation.name = chat`
- `gen_ai.request.model = groq/llama-3.1-8b-instant`
- `aois.tier = fast`
- `aois.severity = P3` (or whichever severity was assigned)

This is what end-to-end observability looks like: one request, full visibility.

---

## Part 7: VictoriaMetrics — When Prometheus Runs Out

The v16 AOIS stack generates roughly 50 active time series — well within Prometheus's comfort zone. The problem comes later: Phase 7 adds autonomous agents running 10–15 LLM calls per incident, Phase 9 adds CI pipelines generating telemetry, and production traffic grows. A busy AOIS deployment can generate 10,000+ active series. At that point, Prometheus starts to struggle.

**What happens when Prometheus hits its limit:**
- Memory usage spikes during high-cardinality queries
- Long-range queries (7-day cost trends) become slow or time out
- Scrape intervals must be increased to reduce ingestion pressure
- Retention is limited to 15 days by default without federation complexity

VictoriaMetrics is a drop-in Prometheus replacement that solves all four. "Drop-in" is literal:

```yaml
# docker-compose.yml — replace the prometheus service
# Before:
prometheus:
  image: prom/prometheus:v2.53.0
  volumes:
    - ./otel/prometheus.yml:/etc/prometheus/prometheus.yml

# After:
victoriametrics:
  image: victoriametrics/victoria-metrics:v1.100.0
  command:
    - -storageDataPath=/storage
    - -retentionPeriod=90d
    - -httpListenAddr=:8428
  ports:
    - "8428:8428"
  volumes:
    - vm_data:/storage
```

Then update the Grafana datasource URL from `http://prometheus:9090` to `http://victoriametrics:8428`. Every PromQL query in your dashboards works unchanged — VictoriaMetrics implements the full PromQL specification plus MetricsQL extensions.

**Why it handles more scale than Prometheus:**

| Characteristic | Prometheus | VictoriaMetrics |
|---|---|---|
| Ingestion throughput | ~200k samples/sec (single node) | ~2M samples/sec (single node) |
| Compression | LZ4, ~8 bytes/sample | ZSTD, ~1–2 bytes/sample |
| High-cardinality handling | OOM risk above ~10M series | Handles 100M+ series gracefully |
| Long-range query performance | Degrades past 7-day windows | Fast on 90-day windows |
| Default retention | 15 days | Configurable, `--retentionPeriod=1y` |

**When to stay on Prometheus:** development scale with few series, exact Prometheus recording rule evaluation semantics required, deeply integrated Alertmanager.

**When to switch:** Prometheus exceeds 4GB RAM, retention beyond 30 days required, agent loops generating thousands of LLM spans per hour.

**Migration with historical data preserved:**

```bash
# Step 1: export Prometheus data (while Prometheus is running)
docker run --rm -v prometheus_data:/prometheus \
  prom/prometheus:v2.53.0 \
  promtool tsdb dump /prometheus > prometheus-dump.txt

# Step 2: start VictoriaMetrics (after updating docker-compose.yml)
docker compose up -d victoriametrics

# Step 3: import via vmctl
docker run --rm \
  -v $(pwd)/prometheus-dump.txt:/data/dump.txt \
  victoriametrics/vmctl:v1.100.0 \
  prometheus --prom-snapshot=/data/dump.txt \
  --vm-addr=http://localhost:8428

# Step 4: update Grafana datasource URL from :9090 to :8428
```

For development environments: just swap the docker-compose service and start fresh — dev metric history is rarely worth preserving.

VictoriaMetrics also ships `vmauth` (authentication proxy), `vminsert`/`vmselect` (cluster mode), and `vmagent` (Prometheus-compatible scraper that pushes instead of being pulled). For AOIS scale, single binary is sufficient — but knowing the cluster components exist means you have a clear path when AOIS grows to multi-cluster or multi-region.

---

## Common Mistakes

### 1. Loki crashes with `mkdir /tmp/loki/rules: permission denied`

**Symptom:** `docker compose logs loki` shows permission denied on the rules directory. Loki restarts in a loop.

**Cause:** Loki 3.0+ runs as uid 10001 by default. The volume path `/tmp/loki` inside the container is owned by root. Loki cannot create subdirectories.

**Fix:** either use `user: "0"` in the compose service, or use a named Docker volume (Docker manages permissions). Both work. `user: "0"` is simpler for local development.

```yaml
loki:
  image: grafana/loki:3.0.0
  user: "0"          # run as root for volume write access
  volumes:
    - loki_data:/loki  # named volume, not /tmp path
```

Also ensure the config `path_prefix` matches the volume mount path (`/loki` not `/tmp/loki`).

### 2. Tempo crashes with `field processors not found in type generator.Config`

**Symptom:** `docker compose logs tempo` shows a config parse error on the `processors` field.

**Cause:** Tempo 2.5.0 moved `processors` out of `metrics_generator` and into `overrides.defaults.metrics_generator`. The old config structure is rejected by the parser.

**Fix:** move `processors` to the correct path:

```yaml
# WRONG (pre-2.4)
metrics_generator:
  processors: [service-graphs, span-metrics]

# RIGHT (2.5.0+)
overrides:
  defaults:
    metrics_generator:
      processors: [service-graphs, span-metrics]
```

### 3. `load_dotenv` imported at module level crashes Modal container

**Symptom:** Modal function fails with `ModuleNotFoundError: No module named 'dotenv'`.

**Cause:** `from dotenv import load_dotenv` at the top of any file that Modal imports runs inside the Modal container, which only has packages specified in `pip_install()`. `python-dotenv` is not a training dependency.

**Fix:** move any local-only imports into the `@app.local_entrypoint()` function only.

```python
@app.local_entrypoint()
def main():
    from dotenv import load_dotenv   # only runs locally
    load_dotenv()
    ...
```

### 4. OTel Collector silently drops spans because `insecure: true` is missing

**Symptom:** AOIS starts, sends spans, no errors — but nothing appears in Tempo.

**Cause:** the OTLP exporter defaults to TLS. Tempo is running without TLS (local dev). The connection fails with a TLS handshake error that the Collector logs but the app doesn't surface.

**Fix:** add `tls: {insecure: true}` to the Collector's OTLP exporter:

```yaml
exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true   # required for non-TLS Tempo
```

### 6. VictoriaMetrics stops ingesting with `max active series` error

**Symptom:** VictoriaMetrics logs `the number of active time series exceeds...` and new metrics stop appearing in Grafana.

**Cause:** A label with unbounded values (incident IDs, request IDs) was used as a Prometheus label, creating a new time series per unique value. VictoriaMetrics enforces a default cardinality limit.

**Fix:** Identify which label is unbounded:

```bash
curl -s http://localhost:8428/api/v1/status/tsdb \
  | python3 -c "import sys,json; r=json.load(sys.stdin); [print(e['name'], e['value']) for e in r['data']['topMetricsBySeriesCountPerLabelName'][:10]]"
```

Remove the unbounded label from the metric definition. Incident IDs, trace IDs, and request IDs belong in structured log lines (Loki) or span attributes (Tempo) — not as Prometheus label values. This applies equally to Prometheus: cardinality is a universal constraint, not a VictoriaMetrics-specific one.

### 5. `BatchSpanProcessor` never flushes during short tests

**Symptom:** spans are emitted in code but never appear in Tempo after short test runs.

**Cause:** `BatchSpanProcessor` flushes on a timer (default 5s) or when the buffer fills. If your process exits in 2 seconds, buffered spans are dropped.

**Fix:** call `tracer_provider.shutdown()` before the process exits, or use `force_flush()` in tests. In production (long-running FastAPI), this is not an issue.

```python
import atexit
atexit.register(tracer_provider.shutdown)
```

---

## Troubleshooting

### Prometheus shows "aois-app (1/1 up)" but no aois_* metrics

Check the scrape target path. AOIS mounts the Prometheus ASGI app at `/metrics` but FastAPI adds a trailing slash redirect. Prometheus doesn't follow redirects by default.

```yaml
# prometheus.yml — use trailing slash
metrics_path: /metrics/
```

Verify manually:
```bash
curl -sL http://localhost:8000/metrics/ | grep aois_incidents
```

### OTel Collector log shows "connection refused" to tempo:4317

Tempo hasn't started yet, or its internal gRPC port isn't listening. Check:

```bash
docker compose logs tempo | grep "Starting GRPC server"
# Expected: level=info ... msg="Starting GRPC server" ... endpoint=0.0.0.0:4317
```

If Tempo is healthy but the Collector still fails, verify the Collector's `otlp/tempo` endpoint uses the Docker service name `tempo:4317`, not `localhost:4317` (containers have separate network namespaces).

### Grafana datasource "Prometheus" shows "Data source connected and labels found" but no AOIS metrics

Prometheus hasn't scraped yet. Default scrape interval is 15s. Wait 30 seconds after starting, then refresh.

Also verify Prometheus targets:
```bash
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys,json
r = json.load(sys.stdin)
for t in r['data']['activeTargets']:
    print(t['labels']['job'], t['health'], t.get('lastError',''))
"
```

Expected: `aois-app up` and `aois-otel up`. If `aois-app` shows "connection refused", AOIS is not reachable at `aois:8000` — check Docker network or if the container is healthy.

### OTel Collector config silently drops a pipeline

**Symptom:** AOIS emits spans with no errors, but Tempo shows no traces. `docker compose logs otelcol` shows the Collector started successfully but no trace export activity.

**Cause:** A YAML indentation error in the Collector config silently disables a pipeline. The Collector validates and starts, but the `traces` pipeline is absent from the running config.

**Fix:** Validate the config explicitly before starting:

```bash
docker run --rm \
  -v $(pwd)/otel/otelcol-config.yaml:/etc/otel/config.yaml \
  otel/opentelemetry-collector-contrib:0.100.0 \
  validate --config /etc/otel/config.yaml
# Expected: 2024/... Validation result: Valid configuration
```

Also inspect the running Collector's debug endpoint to confirm all pipelines loaded:

```bash
curl -s http://localhost:55679/debug/pipelinez | grep -A5 "traces"
# Expected: traces pipeline listed with receiver=otlp and exporter=otlp/tempo
# If the traces section is absent, the pipeline did not load
```

The most common cause: mixing 2-space and 4-space indentation in the `service.pipelines` section. YAML is indentation-sensitive; the Collector parser silently skips malformed sections rather than failing at startup.

---

## Connection to Later Phases

**v17 (Kafka)**: Kafka consumer lag, producer errors, and broker metrics will be ingested through the same OTel Collector. The Prometheus exporter gets two new scrapers: Kafka JMX metrics and KEDA consumer lag. The dashboard gains a Kafka panel.

**v19 (Chaos Engineering)**: Chaos Mesh injects failures. The OTel traces from the chaos period become the evidence of blast radius. "How long did p99 latency stay above 5s after we killed worker-3?" — this query is only answerable because v16 exists.

**v20 (Tool use + memory)**: agentic workflows span 10–15 LLM calls per incident. Per-incident cost attribution (flagged in the April 2026 audit) requires threading an `incident_id` attribute through all spans in the agent loop. The tracing infrastructure from v16 is the foundation that makes this possible.

**v16.5 (ClickHouse: Analytics at Scale)**: the OTel stack from v16 answers operational questions — "is AOIS healthy right now?" ClickHouse answers analytical questions — "which incident type has cost the most this month?" Prometheus cannot scan 100 million rows in milliseconds; ClickHouse can. The two coexist: Prometheus for real-time alerting, ClickHouse for analytics and long-term audit. Every analysis event flowing through the OTel Collector is also written to ClickHouse for indefinite retention and columnar queries.

**v29 (Weights & Biases)**: the `aois_llm_cost_usd_total` counter and `aois_llm_duration_ms` histogram produce the baseline metrics for every model. W&B tracks how these change across model versions. The eval results from v15 + the live metrics from v16 are the two inputs to W&B experiment tracking.

---

## Mastery Checkpoint

You have completed v16 when you can do all of the following:

1. **Explain the difference between traces, metrics, and logs** in one sentence each, with a concrete example from AOIS.

2. **Draw the data pipeline from memory**: AOIS → Collector → three backends → Grafana, with port numbers.

3. **Read the OTel GenAI semantic convention attributes** for any LLM span and state what each attribute tells you.

4. **Fix the three common failures** from symptom alone: Loki permission denied, Tempo config parse error, Collector TLS mismatch.

5. **Add a new metric** to AOIS — for example, a counter tracking the number of blocked outputs (safety layer triggered). You know which file to edit, which Prometheus type to use, and where in the request path to increment it.

6. **Query across all three pillars in Grafana** to answer: "During the latency spike at 14:32, which model was responsible and what did the logs say?" — using Prometheus for the spike, Tempo for the trace, Loki for the log.

7. **Explain why `BatchSpanProcessor` is always used in production** and what breaks if you use `SimpleSpanProcessor` instead.

8. **State what changes in v17** when Kafka is added — specifically, which part of the OTel pipeline changes and what new metrics appear.

9. **Describe the April 2026 audit finding** about per-incident cost attribution and what it requires technically.

10. **State the migration procedure from Prometheus to VictoriaMetrics** in three commands. At what point in the AOIS build roadmap (which phase, which observable symptom) would you decide to switch?

11. **Explain why v16 uses three separate backends** (Tempo, Prometheus, Loki) instead of a single unified system. What does each answer that the others cannot — in one sentence per backend?

**The mastery bar:** given a production AI system with no observability and a cost spiral ("we're spending $400/day on LLM calls but don't know why"), you can instrument it from scratch, stand up the OTel Collector + Prometheus + Grafana stack, and within one day answer: which model, which endpoint, which traffic pattern is responsible.

---

*Phase 6 has begun. v17 brings Kafka — real log streaming into AOIS. The observability stack you built here will watch the Kafka pipeline too.*

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### OpenTelemetry (OTel)

| Layer | |
|---|---|
| **Plain English** | A universal standard for collecting metrics, logs, and traces from your application — so you can send observability data to any monitoring tool without rewriting your instrumentation code when you change tools. |
| **System Role** | OTel is the instrumentation layer for all of AOIS. Every LLM call, every FastAPI request, every cache hit generates OTel spans and metrics. The OTel Collector receives this data and fans it out to Prometheus (metrics), Loki (logs), and Tempo (traces). Change the backend — the AOIS code doesn't change. |
| **Technical** | OTel SDK instruments the application: `trace.get_tracer()` creates spans, `meter.create_counter()` creates metrics. The `OTLPExporter` sends data to the Collector via gRPC on port 4317. The Collector's pipeline: `receivers → processors → exporters`. AOIS uses the GenAI semantic conventions: `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` — standardised attribute names for LLM spans across all vendors. |
| **Remove it** | Without OTel, you write Prometheus-specific metric code, Datadog-specific trace code, and vendor-specific log shipping config — and rewrite everything when you change backends. OTel is the reason "instrument once, send anywhere" is real. Removing it means either vendor lock-in or no observability — and you cannot improve a system you cannot measure. |

**Say it at three levels:**
- *Non-technical:* "OTel is like a universal adapter for monitoring. Instead of buying a different cable for every device, you use one standard connector and it works with everything."
- *Junior engineer:* "`from opentelemetry import trace` then `with tracer.start_as_current_span('llm.call') as span: span.set_attribute('gen_ai.request.model', model)`. The OTel Collector config defines where the data goes — change the `exporters` section, the app code stays the same. FastAPI auto-instrumentation: `FastAPIInstrumentor().instrument_app(app)` adds spans for every request automatically."
- *Senior engineer:* "OTel's GenAI semantic conventions are a 2024 addition — not yet stable as of early 2026 but converging fast. Standardised token/cost attributes mean Langfuse, Grafana, and Datadog all read the same span attributes. The Collector is the operationally important component: it buffers, retries, and batches exports — losing the Collector doesn't lose spans immediately because the SDK buffers in-process. The Collector also does tail-based sampling (sample only traces with errors or high latency) which head-based SDK sampling cannot do."

---

### Prometheus

| Layer | |
|---|---|
| **Plain English** | A monitoring system that regularly asks your application "how many requests did you handle? how much did the last LLM call cost?" and stores the answers as time-series data you can query and graph. |
| **System Role** | Prometheus scrapes AOIS's `/metrics` endpoint every 15 seconds and stores `aois_incidents_total`, `aois_llm_duration_ms`, `aois_llm_cost_usd_total`, and `aois_llm_token_usage_total`. These counters and histograms power the Grafana dashboard. Without Prometheus, the LLM cost spiral that kills production AI systems is invisible until the invoice arrives. |
| **Technical** | AOIS exposes metrics via `prometheus_client` in the Pull model: Prometheus initiates the scrape, the app serves the current metric values. The OTel Collector can also push to Prometheus's remote write endpoint (Push model). Histograms bucket latency observations — `aois_llm_duration_ms_bucket{le="500"}` counts calls under 500ms. `rate()` in PromQL converts cumulative counters to per-second rates for dashboards. |
| **Remove it** | Without Prometheus, you have no answer to "which model tier is slowest?" or "how much did yesterday's Kafka consumer spike cost in LLM calls?" You also lose alerting — Alertmanager reads Prometheus rules and fires when `aois_llm_cost_usd_total` rate exceeds your budget threshold. This is the difference between knowing about a cost problem on Monday morning and knowing about it the moment it starts. |

**Say it at three levels:**
- *Non-technical:* "Prometheus is the pulse monitor. Every 15 seconds it checks AOIS's vital signs — cost, latency, error rate — and records them. Grafana turns those recordings into charts."
- *Junior engineer:* "`from prometheus_client import Counter, Histogram` then `incidents_total = Counter('aois_incidents_total', 'Count', ['severity','tier'])`. Increment with `incidents_total.labels(severity='P1', tier='premium').inc()`. The `/metrics` endpoint is mounted via `make_asgi_app()`. Prometheus scrape config: `scrape_configs: [{job_name: aois, static_configs: [{targets: ['aois:8000']}]}]`."
- *Senior engineer:* "Cardinality is the Prometheus operational risk. Each unique label combination creates a separate time series. `aois_llm_cost_usd_total{tier, severity, model}` is safe — bounded cardinality. Never label with unbounded values (user IDs, request IDs, log content). High cardinality kills Prometheus memory. VictoriaMetrics handles 10× higher cardinality than Prometheus at the same hardware — the migration path when AOIS telemetry volume grows past Prometheus's comfortable range."

---

### Grafana

| Layer | |
|---|---|
| **Plain English** | The dashboard layer — connects to Prometheus, Loki, and Tempo and turns raw numbers and logs into visual panels, graphs, and alerts that humans can actually read and act on. |
| **System Role** | Grafana is AOIS's observability UI. The pre-provisioned AOIS LLM dashboard shows: requests/sec by severity, cost per tier over time, P95 latency per model, cache hit rate, and token usage. In v19, Grafana shows the chaos experiment results. In v26, the React frontend replaces Grafana for end-user views — but Grafana stays for operational monitoring. |
| **Technical** | Grafana datasources connect to Prometheus (metrics), Loki (logs), and Tempo (traces). Provisioning via YAML in `/etc/grafana/provisioning/` means datasources and dashboards are configured as code — no clicking through the UI to set up a new environment. Dashboard JSON models are checked into the repo. Panels use PromQL, LogQL, and TraceQL respectively. |
| **Remove it** | Without Grafana, observability data exists in Prometheus/Loki/Tempo but requires knowing the query language for each to extract anything useful. Grafana is not optional — it's the interface that makes the data actionable for both engineers and stakeholders who don't know PromQL. Replacing it requires building a custom dashboard (v26 does this for the user-facing surface — Grafana stays for the ops surface). |

**Say it at three levels:**
- *Non-technical:* "Grafana turns numbers into pictures. Prometheus stores the data. Grafana makes it into graphs you can actually look at during an incident and understand immediately."
- *Junior engineer:* "Grafana datasource provisioning: YAML in `/etc/grafana/provisioning/datasources/` with `type: prometheus`, `url: http://prometheus:9090`. Dashboards provisioned from JSON in `/etc/grafana/provisioning/dashboards/`. A panel pointing at AOIS cost: PromQL `rate(aois_llm_cost_usd_total[5m])` gives cost per second, multiply by 3600 for hourly rate."
- *Senior engineer:* "Grafana's value in a multi-signal setup (metrics + logs + traces) is unified correlation. Click a spike in the cost panel → jump to Loki logs at that timestamp → click a trace ID in the log → Tempo shows the full request trace including which LLM call was slow. This full-stack correlation is what separates a monitoring setup from an observability setup. Provisioning-as-code is non-negotiable for reproducibility — the first thing lost in a 'we just click around in Grafana' setup is the ability to recreate the environment after a cluster rebuild."

---

### Tempo

| Layer | |
|---|---|
| **Plain English** | A distributed tracing backend that stores the complete timeline of every request — every service it touched, every function it called, how long each step took — so you can pinpoint exactly where time was lost in a specific request. |
| **System Role** | Tempo receives traces from the OTel Collector via OTLP gRPC and stores them. When a Grafana Loki log entry contains a trace ID, clicking it opens the full span tree in Tempo. This links "what did the log say?" to "what did the system actually do?" Every LLM call span (`gen_ai.chat groq/llama-3.1-8b-instant`) is visible in the trace tree with its exact duration and GenAI attributes. |
| **Technical** | Tempo stores traces as blocks in object storage (local filesystem in dev, S3 in production). It does not index span attributes — trace lookup is by trace ID or by TraceQL query (e.g., `{ .aois.tier = "premium" && duration > 5s }`). The `metrics_generator` component can synthesise RED metrics (Request/Error/Duration) from traces, producing Prometheus-compatible metrics without app-level instrumentation. |
| **Remove it** | Without Tempo: Prometheus tells you P99 latency spiked at 14:32. Loki shows which log lines appeared during that window. But you cannot answer "which specific LLM call was slow" — you need the span tree. The histogram shows the aggregate; the trace shows one example. Both are required to debug a latency incident. |

**Say it at three levels:**
- *Non-technical:* "If Prometheus is the camera that shows average traffic patterns, Tempo is the replay button for a single request. You pick one and watch every step it went through, with timestamps."
- *Junior engineer:* "Query in Grafana: Explore → Tempo → TraceQL: `{ .aois.tier = \"premium\" && duration > 5s }`. This finds all premium-tier AOIS requests over 5 seconds. Each trace shows: HTTP span → gen_ai.chat span → cache check span. The gen_ai span attributes (`gen_ai.request.model`, `aois.cost_usd`) are visible in the span detail panel."
- *Senior engineer:* "Tempo's no-attribute-index design is the right tradeoff at AOIS scale. Jaeger with Elasticsearch indexes every attribute — powerful but expensive. Tempo stores traces in object storage with only trace ID and a few tags indexed. At high volume the Tempo metrics_generator becomes valuable: it synthesises a service graph (AOIS → Claude API → Groq → Kafka) from trace data without requiring Prometheus instrumentation on external services. In production, Tempo runs behind a query-frontend for parallelised queries on large trace volumes."

---

### Loki

| Layer | |
|---|---|
| **Plain English** | A log aggregation system built by Grafana Labs to work the way Prometheus works for metrics — but for logs. Instead of indexing every word in every log line (like Elasticsearch), it indexes only labels (service name, severity, tier) and compresses the actual log text — dramatically cheaper at the cost of full-text search speed. |
| **System Role** | Loki receives structured JSON logs from the OTel Collector and stores them with labels derived from OTel resource attributes (`job=aois`, `tier=fast`, `severity=P1`). The Grafana AOIS dashboard queries Loki to show the live log stream. Log entries that include a trace ID are linked to Tempo — one click from a log line to the full request trace. |
| **Technical** | Log ingestion via the Loki push API at `/loki/api/v1/push`. Logs are chunked per label-set and compressed with GZIP. LogQL has two parts: the stream selector `{job="aois"}` uses the index (fast); the filter `|= "OOMKilled"` scans compressed chunks (slower). The OTel Collector Loki exporter maps OTel attributes to Loki labels — low-cardinality fields only. Never use `trace_id` as a label: one stream per trace ID would exhaust Loki's index memory. |
| **Remove it** | Without Loki: logs exist only in container stdout. `kubectl logs pod-xyz` shows the current pod's last N lines. Historical logs (3-day-old P1 incidents), cross-pod queries (all AOIS replicas), and structured field filtering (`severity="P1" and cost > 0.01`) are impossible. Debugging a production incident from Tuesday requires accessing each pod's filesystem — not viable when pods come and go. |

**Say it at three levels:**
- *Non-technical:* "Loki is a searchable archive for log messages. Instead of 'where is the log file for Tuesday's incident?', you type 'show me all P1 incidents from Tuesday' and Loki finds them across every container."
- *Junior engineer:* "LogQL: `{job=\"aois-app\"} | json | severity=\"P1\" | cost_usd > 0.01`. Labels in `{}` use the index — always start there. After `| json`, all structured fields become filterable. Pipeline stages: `| json` (parse), `| severity=\"P1\"` (filter), `| line_format \"{{.model}} {{.severity}} {{.cost_usd}}\"` (reshape output for the panel)."
- *Senior engineer:* "Loki's label cardinality is the critical operational constraint. Labels must be low-cardinality — AOIS uses `job`, `tier` (fast/premium/local), `severity` (P1–P4). Adding `request_id` as a label creates a stream per request (millions of streams), exhausting Loki's in-memory index. Trace IDs belong in the log body where they are queryable via `|= \"trace_id\"` but not indexed. In production, Loki runs in distributed mode (ingester, querier, compactor separated) on object storage. Single-binary dev mode scales to ~50GB/day ingestion before performance degrades."

---

### VictoriaMetrics

| Layer | |
|---|---|
| **Plain English** | A faster, more storage-efficient drop-in replacement for Prometheus — designed for environments where Prometheus would run out of memory or disk, while keeping full backwards compatibility with PromQL queries and Grafana dashboards. |
| **System Role** | VictoriaMetrics is the migration path when AOIS telemetry grows beyond what Prometheus handles comfortably. In Phase 7, autonomous agents generate 10–15 LLM spans per incident. At production volume, this can exceed Prometheus's comfortable cardinality range. Switching requires changing one service in `docker-compose.yml` and one URL in Grafana — every dashboard, alert rule, and PromQL query works unchanged. |
| **Technical** | VictoriaMetrics replaces Prometheus's TSDB storage engine with a custom columnar engine using ZSTD compression (5–10× better ratio than Prometheus's LZ4) and lock-free ingestion designed for high-concurrency writes. It implements the Prometheus HTTP API and accepts `remote_write` — existing scrapers, Alertmanager, and Grafana datasources require no reconfiguration. `--retentionPeriod=90d` extends retention to 90 days. Cluster mode adds `vminsert`/`vmselect` for horizontal scaling. |
| **Remove it** | Without VictoriaMetrics as an option: when Prometheus runs out of memory on a busy AOIS deployment, the paths are Prometheus federation (complex), Thanos (complex), or Cortex (complex). VictoriaMetrics is the single-binary answer that covers 90% of scale problems without adding distributed system complexity. Removing it from your toolkit means reaching for much heavier solutions the first time Prometheus struggles. |

**Say it at three levels:**
- *Non-technical:* "VictoriaMetrics is a faster car with the same road rules. Your dashboards don't know the difference — it works with all the same tools. You switch when your current car starts struggling with the load."
- *Junior engineer:* "Migration: (1) change `image: prom/prometheus` to `image: victoriametrics/victoria-metrics:v1.100.0`, (2) replace Prometheus flags with `--storageDataPath=/storage --retentionPeriod=90d --httpListenAddr=:8428`, (3) update Grafana datasource URL from `:9090` to `:8428`. Your `prometheus.yml` scrape config is reused unchanged — VictoriaMetrics reads it natively via the Prometheus-compatible API."
- *Senior engineer:* "VictoriaMetrics supports both pull (Prometheus-compatible scraping) and push (via remote_write). This matters for agent workflows with short-lived pods: a pod that exits before the 15s scrape fires loses its final metrics. With remote_write to VictoriaMetrics, metrics are pushed at each update. The cardinality limiter is the key production feature: VictoriaMetrics can reject series above a threshold, preventing a runaway agent from creating millions of time series and exhausting storage. This is the safety valve that Prometheus does not have."
