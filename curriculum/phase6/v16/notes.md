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

---

## Connection to Later Phases

**v17 (Kafka)**: Kafka consumer lag, producer errors, and broker metrics will be ingested through the same OTel Collector. The Prometheus exporter gets two new scrapers: Kafka JMX metrics and KEDA consumer lag. The dashboard gains a Kafka panel.

**v19 (Chaos Engineering)**: Chaos Mesh injects failures. The OTel traces from the chaos period become the evidence of blast radius. "How long did p99 latency stay above 5s after we killed worker-3?" — this query is only answerable because v16 exists.

**v20 (Tool use + memory)**: agentic workflows span 10–15 LLM calls per incident. Per-incident cost attribution (flagged in the April 2026 audit) requires threading an `incident_id` attribute through all spans in the agent loop. The tracing infrastructure from v16 is the foundation that makes this possible.

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

**The mastery bar:** given a production AI system with no observability and a cost spiral ("we're spending $400/day on LLM calls but don't know why"), you can instrument it from scratch, stand up the OTel Collector + Prometheus + Grafana stack, and within one day answer: which model, which endpoint, which traffic pattern is responsible.

---

*Phase 6 has begun. v17 brings Kafka — real log streaming into AOIS. The observability stack you built here will watch the Kafka pipeline too.*
