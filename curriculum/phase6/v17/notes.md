# v17 — Kafka: Real Log Streaming

⏱ **Estimated time: 4–6 hours**

*Phase 6 — Full SRE Observability Stack. v16 made every LLM call visible. v17 makes every log event flow.*

---

## What This Version Builds

Every previous version of AOIS receives logs via HTTP POST — one log, one request, one response. That is a pull model: the caller decides when to analyze. Production does not work that way. Production systems emit thousands of events per second. You cannot fire thousands of synchronous HTTP requests per second and expect AOIS to hold up. Requests back up, timeouts fire, events are lost, and there is no way to replay the ones that were dropped.

The correct model is push: infrastructure fires log events into a durable stream, AOIS consumers read them continuously, and the number of AOIS instances scales automatically with the backlog. When AOIS is down for 30 minutes for a deploy, the log events pile up in the stream. When AOIS comes back, it picks up exactly where it left off. Not one event is lost.

Kafka is how this works at Netflix, Cloudflare, Uber, and every company running SRE at scale.

By the end of v17:
- **Local**: Kafka in Docker Compose (`apache/kafka:3.7.0`, KRaft mode — no ZooKeeper dependency)
- **Producer**: `kafka/producer.py` — simulates infrastructure emitting SRE log events to `aois-logs` at a configurable rate, complete with a library of realistic log templates from all the failure categories AOIS is trained to handle
- **Consumer**: `kafka/consumer.py` — long-lived worker that reads from `aois-logs` and `aois-security`, calls `analyze()`, publishes structured results to `aois-results`, handles graceful shutdown
- **k8s**: Strimzi operator + Kafka 4.1.0 cluster on Hetzner k3s — `aois-logs` and `aois-results` topics as `KafkaTopic` CRDs, managed declaratively by ArgoCD
- **KEDA**: ScaledObject updated from CPU trigger to Kafka consumer lag trigger — AOIS pods scale when unprocessed messages pile up, idle when the queue is empty

---

## Prerequisites

Verify all of these before starting. Do not proceed if any fail.

```bash
# Docker Compose stack from v16 is running
docker compose ps | grep -E 'kafka|aois'
```

Expected:
```
aois-system-aois-1      running   0.0.0.0:8000->8000/tcp
aois-system-kafka-1     running   0.0.0.0:9094->9094/tcp
```

```bash
# Hetzner cluster is reachable
kubectl get nodes
```

Expected:
```
NAME   STATUS   ROLES                  AGE   VERSION
aois   Ready    control-plane,master   Xd    v1.30.x
```

```bash
# kafka-python-ng library installed
python3 -c "from kafka import KafkaProducer; print('kafka-python-ng ok')"
```

Expected:
```
kafka-python-ng ok
```

```bash
# KEDA is running on the cluster
kubectl get pods -n keda | grep keda-operator
```

Expected:
```
keda-operator-xxxxxxxxx-xxxxx   2/2   Running   0   Xd
```

```bash
# ArgoCD managing AOIS (from v8)
kubectl get application aois -n argocd -o jsonpath='{.status.sync.status}'
```

Expected: `Synced`

---

## Learning Goals

By the end of v17 you will be able to:

- Explain why Kafka is used instead of HTTP for high-volume log streaming, and name the three guarantees that matter for AOIS
- Describe the producer-consumer-topic model and what consumer groups enable — partition assignment, parallel processing, fan-out
- Configure a Kafka consumer with correct `auto_offset_reset`, `group_id`, commit strategy, and error handling — the pattern that survives restarts and crashes
- Explain the dual-listener networking pattern and reproduce it from memory — without it, host Python clients cannot reach Kafka running inside Docker
- Deploy a Kafka cluster to Kubernetes using the Strimzi operator, declare topics as `KafkaTopic` CRDs, and verify the cluster is ready
- Switch KEDA from CPU-based to Kafka-consumer-lag-based autoscaling and explain the math: how `lagThreshold` determines desired replica count
- Build and observe the complete pipeline end-to-end: produce logs → consume → analyze with LLM routing → publish results → verify in `aois-results`

---

## Part 1: Why Kafka for AOIS

The HTTP model breaks at scale in three distinct ways:

**Backpressure**: if AOIS takes 800ms per analysis (a fast call with caching) and you want to process 100 events per second, you need 80 parallel AOIS pods. Every HTTP POST ties up a thread for the full round trip. You cannot scale threads linearly — eventually the OS and network stack become the bottleneck.

**Durability**: an HTTP POST to a pod that crashes mid-request is a silent loss. The caller gets a connection error, the log event is gone, and no one knows. There is no replay.

**Coordination**: if you want multiple AOIS pods to share the work without processing the same log twice, you need a coordination layer. HTTP has none — you would have to build your own distributed queue on top.

Kafka solves all three:

**Durability**: every event written to `aois-logs` is persisted to disk. It does not disappear if the broker restarts, a consumer crashes, or a pod is evicted. The default retention is 24 hours — you have a 24-hour replay window.

**Consumer groups**: multiple AOIS pods in the same consumer group (`aois-workers`) share the work. Kafka assigns partitions to group members — with 3 partitions and 3 pods, each pod owns one partition. Adding more pods increases throughput up to the partition count.

**Replay**: consumer lag is a first-class metric. When AOIS is down for 30 minutes, 30 minutes of logs pile up in the topic. When AOIS comes back, it reads from the last committed offset. Not one event is lost, just delayed. This is the fundamental difference between a demo system and a production SRE tool.

### Where Kafka Sits in the AOIS Architecture

```
Infrastructure / Applications
         │
         │  (log events, security alerts)
         ▼
    aois-logs topic ────── Kafka Broker ────── aois-security topic
         │                      │                      │
         ▼                      │                      ▼
  AOIS Consumer pods ◄──────────┘              AOIS Consumer pods
  (aois-workers group)                         (same group)
         │
         │  (structured analysis results)
         ▼
  aois-results topic
         │
         ▼
  Downstream: dashboard, alerting, ClickHouse, further processing
```

The AOIS HTTP API (for direct `/analyze` calls) still exists — it serves the dashboard and external callers. Kafka serves the streaming pipeline. These are complementary, not competing.

---

## Part 2: Kafka in Docker Compose — KRaft Mode

KRaft (Kafka Raft) is Kafka 3.x's replacement for ZooKeeper. Previously, Kafka required a separate ZooKeeper cluster to manage metadata — broker elections, partition assignments, topic configurations. This meant two systems to deploy, monitor, and upgrade. KRaft moves all of this into Kafka itself: nodes elect a controller using the Raft consensus algorithm, and metadata is stored in a Kafka topic named `__cluster_metadata`.

The result: one process instead of two. The `apache/kafka:3.7.0` image runs in KRaft mode by default.

### The Dual-Listener Pattern (Read This Carefully)

This is the most common Kafka networking mistake in local development. It will cost you an hour if you do not understand it before touching anything.

When a Kafka client connects to the broker, the broker returns a list of **advertised listener addresses** — the addresses the client should use for subsequent connections. If the advertised address is `kafka:9092` (the Docker internal hostname), a Python process running on your host machine receives that address, tries to connect to `kafka:9092`, and fails — because `kafka` is not resolvable outside the Docker network.

The fix: configure two separate listeners on two separate ports with two separate advertised addresses.

```yaml
# docker-compose.yml — Kafka environment variables
environment:
  KAFKA_PROCESS_ROLES: broker,controller
  KAFKA_NODE_ID: 1
  KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
  KAFKA_LISTENERS: INTERNAL://:9092,EXTERNAL://:9094,CONTROLLER://:9093
  KAFKA_ADVERTISED_LISTENERS: INTERNAL://kafka:9092,EXTERNAL://localhost:9094
  KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
  KAFKA_INTER_BROKER_LISTENER_NAME: INTERNAL
  KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
  KAFKA_AUTO_CREATE_TOPICS_ENABLE: "false"
  KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
  KAFKA_LOG_RETENTION_HOURS: 24
```

**INTERNAL://kafka:9092** — used by container-to-container traffic. AOIS running inside Docker uses this. The broker advertises `kafka:9092`, which resolves correctly within the Docker network.

**EXTERNAL://localhost:9094** — used by host traffic. Your Python scripts use this. The broker advertises `localhost:9094`, which resolves correctly on the host machine.

**CONTROLLER://:9093** — the Raft metadata port. Not exposed externally. Kafka nodes use this to elect a controller.

Rule: container clients use port 9092. Host clients use port 9094. Never mix them.

### Why `KAFKA_AUTO_CREATE_TOPICS_ENABLE: "false"`

With auto-creation enabled, a producer that misspells a topic name silently creates a new topic with default settings (often 1 partition, 1 hour retention). The misspelled topic fills up with messages no one reads. The consumer reads from the correctly-spelled empty topic and processes nothing. The bug is invisible.

With auto-creation disabled, a producer targeting a non-existent topic gets an error immediately. Fail fast, fail loud.

### `api_version=(3, 7, 0)` — Why You Must Specify This

`kafka-python-ng` auto-detects the broker's Kafka API version by sending a probe request on connect. This auto-detection fails against Kafka 3.7+ because the handshake protocol changed in a way that the library does not handle correctly. The result: `NodeNotReadyError` or a hang on connection.

The fix is to specify `api_version` explicitly on every client — producer, consumer, and admin. Providing the version bypasses the detection step entirely and connects immediately.

```python
# Always pass api_version explicitly
producer = KafkaProducer(
    bootstrap_servers="localhost:9094",
    api_version=(3, 7, 0),
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)
```

---

## ▶ STOP — do this now: Verify Kafka and Create Topics

Start the full stack and verify Kafka is reachable:

```bash
docker compose up -d
docker compose ps kafka
```

Expected:
```
NAME                    STATUS
aois-system-kafka-1     running
```

Create both topics and verify they exist:

```bash
docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic aois-logs \
  --partitions 3 \
  --replication-factor 1 \
  --if-not-exists

docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic aois-results \
  --partitions 3 \
  --replication-factor 1 \
  --if-not-exists

docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list
```

Expected:
```
Created topic aois-logs.
Created topic aois-results.
aois-logs
aois-results
```

Describe one topic to confirm partition layout:

```bash
docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic aois-logs
```

Expected:
```
Topic: aois-logs    TopicId: xxx    PartitionCount: 3    ReplicationFactor: 1
  Topic: aois-logs    Partition: 0    Leader: 1    Replicas: 1    Isr: 1
  Topic: aois-logs    Partition: 1    Leader: 1    Replicas: 1    Isr: 1
  Topic: aois-logs    Partition: 2    Leader: 1    Replicas: 1    Isr: 1
```

Now send 5 test messages from the host (using port 9094):

```bash
python3 kafka/producer.py --count 5 --rate 5
```

Expected:
```
Connected to Kafka at localhost:9094
Publishing to 'aois-logs' at 5.0 msg/sec, total 5
Done. Sent 5 messages to 'aois-logs'.
```

Verify they landed in the topic (using port 9092, from inside Docker):

```bash
docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic aois-logs \
  --from-beginning \
  --max-messages 5 \
  --timeout-ms 5000
```

Expected — five JSON objects, one per line:
```
{"id": "3f7a1b2c", "log": "OOMKilled: container aois-api exceeded memory limit 512Mi, exit code 137", "source": "aois-producer", "ts": 1714000000.0}
{"id": "9d4e8f1a", "log": "CrashLoopBackOff: auth-service failed 5 times in 10 minutes, last exit code 1", "source": "aois-producer", "ts": 1714000001.0}
...
```

You have just verified the dual-listener pattern is working: the Python producer wrote to port 9094 (host listener), the CLI consumer inside Docker reads on port 9092 (internal listener), and the messages are identical.

---

## Part 3: The Producer — `kafka/producer.py`

The producer is straightforward. Its purpose is to simulate infrastructure emitting log events at a configurable rate. The key design decisions:

### The Log Library

`kafka/producer.py` contains 30+ realistic log templates across every category AOIS handles: OOM kills, CrashLoopBackOff, disk pressure, network/DNS failures, TLS expiry, 5xx spikes, CPU throttling, database errors, security alerts. Each template has `{n}` placeholders that are replaced with realistic random values via the `vary()` function.

This matters for testing: you want a realistic mix of P1, P2, P3, and P4 incidents so you can observe AOIS's tier routing (OOMKilled goes to Claude, DNS timeout goes to Groq) and verify KEDA scales proportionally to the lag, not to a uniform synthetic load.

### Event Schema

Each event published to `aois-logs` is a JSON object:

```json
{
  "id": "3f7a1b2c",
  "log": "OOMKilled: container aois-api exceeded memory limit 512Mi, exit code 137",
  "source": "aois-producer",
  "ts": 1714000000.123
}
```

The `id` is an 8-character UUID prefix — short enough to read in logs, unique enough for deduplication. The consumer passes `id` through to `aois-results` so you can correlate input events to output results.

### Rate Control

```bash
python3 kafka/producer.py --rate 1       # 1 msg/sec, continuous (default)
python3 kafka/producer.py --rate 10      # 10 msg/sec burst
python3 kafka/producer.py --count 100    # exactly 100 messages then exit
python3 kafka/producer.py --rate 50 --count 500  # backlog test: fill the queue faster than AOIS can drain it
```

The `--rate 50 --count 500` combination is how you test KEDA: produce 500 messages faster than AOIS can analyze them, watch consumer lag climb, watch KEDA scale up pods.

---

## Part 4: The Consumer — `kafka/consumer.py`

`kafka/consumer.py` is the heart of v17. It is a long-lived process with five responsibilities:

### 1. Connect with Retry

Kafka may not be ready when the consumer starts, especially in Docker Compose where service startup order is not strictly enforced. The consumer retries 12 times at 5-second intervals (60 seconds total) before giving up. This is the correct pattern for any service that depends on Kafka:

```python
for attempt in range(12):
    try:
        consumer = KafkaConsumer(
            *INPUT_TOPICS,
            bootstrap_servers=BOOTSTRAP_SERVERS,
            group_id=CONSUMER_GROUP,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
            consumer_timeout_ms=1000,
            api_version=(3, 7, 0),
        )
        break
    except NoBrokersAvailable:
        logger.warning(f"Kafka not ready (attempt {attempt+1}/12), retrying in 5s...")
        time.sleep(5)
else:
    logger.error("Could not connect to Kafka after 60s — exiting")
    sys.exit(1)
```

### 2. Dual-Topic Subscription

The consumer subscribes to both `aois-logs` (SRE log events) and `aois-security` (Falco runtime security alerts from v18). A single consumer loop handles both — distinguishing them by the presence of `rule` and `priority` fields:

```python
INPUT_TOPICS = ["aois-logs", "aois-security"]

# Inside the message loop:
is_falco = "rule" in event and "priority" in event
if is_falco:
    log_text, tier = extract_from_falco(event)
else:
    log_text = event.get("log", "")
    tier = event.get("tier") or get_tier_for_log(log_text)
```

### 3. Smart Tier Selection

`get_tier_for_log()` does a quick keyword scan before routing to the LLM tier:

```python
def get_tier_for_log(log: str) -> str:
    p1_keywords = ["OOMKilled", "CrashLoop", "NotReady", "production down", "data loss", "503"]
    if any(kw.lower() in log.lower() for kw in p1_keywords):
        return "premium"  # → Claude
    return "fast"         # → Groq
```

The intent: P1 incidents get the best model. Everything else gets the fastest/cheapest model. This avoids sending every routine DNS timeout to Claude at $0.016/call when Groq handles it for $0.000001.

The `extract_from_falco()` function does the same for security alerts: `ERROR` and `CRITICAL` priority Falco alerts go to Claude, `WARNING` alerts go to Groq.

### 4. Analyze and Publish

For each message:

```python
result = analyze(log_text, tier)  # same analyze() from main.py

output = {
    "id": event_id,
    "source_topic": message.topic,
    "log": log_text,
    "tier": tier,
    "summary": result.summary,
    "severity": result.severity,
    "suggested_action": result.suggested_action,
    "confidence": result.confidence,
    "provider": result.provider,
    "cost_usd": result.cost_usd,
    "duration_ms": round(duration_ms, 1),
    "kafka_offset": message.offset,
    "kafka_partition": message.partition,
}
producer.send(OUTPUT_TOPIC, value=output)
```

The output includes `kafka_offset` and `kafka_partition` — this allows downstream consumers to seek back to specific messages in `aois-logs` if reprocessing is needed.

### 5. Graceful Shutdown

SIGTERM and SIGINT handlers set `running = False`, which exits the message loop, flushes the producer (ensures all sent messages are acknowledged), and closes the consumer (commits the current offset). Without graceful shutdown, the last batch of offsets may not be committed — the next consumer start will reprocess those messages.

```python
running = True
def _stop(sig, frame):
    nonlocal running
    logger.info("Shutting down consumer...")
    running = False
signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)
```

### The `consumer_timeout_ms=1000` Pattern

`KafkaConsumer` iterates with `for message in consumer`. Without a timeout, this loop blocks forever when the topic is empty. With `consumer_timeout_ms=1000`, the iterator raises `StopIteration` after 1 second of no messages, the `for` loop exits, and the outer `while running:` loop repeats. This is what keeps the shutdown signal check responsive — without it, the consumer would be stuck inside the `for message in consumer` loop until the next message arrived.

---

## ▶ STOP — do this now: Run the Full End-to-End Pipeline

Open two terminals.

**Terminal 1 — start the consumer:**
```bash
python3 kafka/consumer.py
```

Expected:
```
{"time":"2026-04-24 10:00:00","level":"INFO","logger":"aois.kafka","message":"Connected to Kafka at localhost:9094"}
{"time":"2026-04-24 10:00:00","level":"INFO","logger":"aois.kafka","message":"Consuming from ['aois-logs', 'aois-security'] → publishing to 'aois-results'"}
```

**Terminal 2 — send a burst of 10 messages:**
```bash
python3 kafka/producer.py --count 10 --rate 5
```

Expected output in **Terminal 1** (one structured log line per analysis):
```
{"time":"...","level":"INFO","logger":"aois.kafka","message":"[3f7a1b2c] P1 — container aois-api exceeded memory limit, OOM kill at 512Mi (premium, 1823ms, $0.016000)"}
{"time":"...","level":"INFO","logger":"aois.kafka","message":"[9d4e8f1a] P3 — DNS resolution failure for Redis service in cluster (fast, 334ms, $0.000001)"}
{"time":"...","level":"INFO","logger":"aois.kafka","message":"[7c2d5e9b] P2 — disk usage at 94% on /var/lib/docker (fast, 298ms, $0.000001)"}
...
```

Note the tier routing in action: OOMKilled events go to `premium` (Claude) with ~1800ms latency and $0.016 cost. DNS and disk events go to `fast` (Groq) with ~300ms latency and $0.000001 cost.

**Terminal 2 — verify results appeared in `aois-results`:**
```bash
docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic aois-results \
  --from-beginning \
  --max-messages 5 \
  --timeout-ms 5000
```

Expected — one JSON result per line, each containing severity, summary, cost, duration:
```json
{"id": "3f7a1b2c", "source_topic": "aois-logs", "severity": "P1", "summary": "Container aois-api killed by OOM at 512Mi limit", "suggested_action": "Increase memory limit to 1Gi, add VPA policy", "confidence": 0.95, "provider": "claude", "cost_usd": 0.016, "duration_ms": 1823.4, "kafka_offset": 0, "kafka_partition": 1}
```

You have now observed the full streaming pipeline: `producer → kafka → consumer → LLM → aois-results`. The HTTP API still works for direct calls. The Kafka pipeline handles continuous streaming.

---

## Part 5: Strimzi — Kafka on Kubernetes

Running Kafka yourself on Kubernetes is genuinely complex: StatefulSets with stable network identities, PodDisruptionBudgets to prevent simultaneous broker evictions, rolling upgrades that restart brokers one at a time to maintain availability, ConfigMaps and init containers for bootstrap configuration, PersistentVolumeClaims for log storage, and headless Services for peer-to-peer broker communication.

Without an operator, this is at least a week of work and ongoing operational burden. The Strimzi operator encodes all of it into a reconciliation loop.

### The Operator Pattern

The Kubernetes operator pattern: you declare what you want (a `Kafka` custom resource), an operator watches for those resources and reconciles the actual cluster state to match. The operator knows how to handle rolling upgrades, broker scaling, topic management, certificate rotation — everything you would otherwise write scripts for.

Strimzi is the most mature Kafka operator for Kubernetes. It is used in production at major enterprises including Red Hat (which sponsors it) and was accepted as a CNCF sandbox project.

### Strimzi Resource Hierarchy

```
KafkaNodePool     — one or more groups of Kafka nodes, each with a resource profile
Kafka             — the cluster: version, listeners, config, KRaft/ZooKeeper mode
KafkaTopic        — an individual topic with retention, partitions, replication factor
KafkaUser         — ACLs and authentication (not used in this version, covered in production hardening)
```

### KRaft Mode in Strimzi

KRaft support in Strimzi requires two annotations on the `Kafka` resource:

```yaml
metadata:
  annotations:
    strimzi.io/node-pools: enabled    # enables KafkaNodePool resources
    strimzi.io/kraft: enabled         # activates KRaft metadata mode
```

Without these annotations, Strimzi creates a ZooKeeper-based cluster by default.

### The Cluster Manifest

```yaml
# k8s/kafka/kafka-nodepool.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: combined
  namespace: kafka
  labels:
    strimzi.io/cluster: aois-kafka
spec:
  replicas: 1
  roles:
    - controller
    - broker
  storage:
    type: ephemeral           # use emptyDir — no PVC needed for single-node dev cluster
  resources:
    requests:
      memory: 512Mi
    limits:
      memory: 768Mi
  jvmOptions:
    -Xms: 256m
    -Xmx: 512m
```

**Why `type: ephemeral`**: k3s on Hetzner does not have a StorageClass configured for dynamic PVC provisioning by default. Using `type: ephemeral` (backed by `emptyDir`) avoids the PVC dependency. The trade-off: logs do not survive pod restarts. For a single-node development cluster, this is acceptable. For production, use `type: persistent-claim` with a configured StorageClass.

**Why explicit JVM heap (`-Xms256m -Xmx512m`)**: without explicit heap settings, Kafka uses the container's memory limit as a guide and sets the JVM heap to approximately 25% of it. With a 768Mi limit, that gives ~192Mi heap — too small for any meaningful workload. The JVM starts aggressively GCing, latency spikes, and in extreme cases the container is OOM-killed by the kernel before the JVM can GC. Setting explicit heap values prevents this.

**Why explicit resource `requests` and `limits`**: without these, the Strimzi operator creates pods with no resource constraints. On a 16GB Hetzner node that also runs AOIS, Prometheus, Grafana, Loki, Tempo, and KEDA, an unconstrained Kafka pod can consume all available memory and trigger the OOM killer on other pods.

```yaml
# k8s/kafka/kafka-cluster.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: aois-kafka
  namespace: kafka
  annotations:
    strimzi.io/node-pools: enabled
    strimzi.io/kraft: enabled
spec:
  kafka:
    version: 4.1.0
    metadataVersion: "4.1"
    replicas: 1
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
    config:
      offsets.topic.replication.factor: 1
      transaction.state.log.replication.factor: 1
      transaction.state.log.min.isr: 1
      log.message.format.version: "4.1"
      log.retention.hours: "24"
      auto.create.topics.enable: "false"
  entityOperator:
    topicOperator: {}
    userOperator: {}
```

The `entityOperator` section deploys two sub-operators: the **Topic Operator** watches `KafkaTopic` CRDs and reconciles actual Kafka topic configuration to match, and the **User Operator** watches `KafkaUser` CRDs and manages ACLs.

```yaml
# k8s/kafka/kafka-topics.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: aois-logs
  namespace: kafka
  labels:
    strimzi.io/cluster: aois-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: "86400000"    # 24 hours
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: aois-results
  namespace: kafka
  labels:
    strimzi.io/cluster: aois-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: "86400000"
    cleanup.policy: delete
```

### Deploying Strimzi

```bash
# Install the Strimzi operator via Helm
helm repo add strimzi https://strimzi.io/charts/
helm repo update

helm install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
  --namespace kafka \
  --create-namespace \
  --set watchNamespaces="{kafka}" \
  --version 0.44.0
```

Wait for the operator to be ready:

```bash
kubectl rollout status deployment/strimzi-cluster-operator -n kafka
```

Expected:
```
deployment "strimzi-cluster-operator" successfully rolled out
```

Apply the cluster resources in order:

```bash
kubectl apply -f k8s/kafka/kafka-nodepool.yaml
kubectl apply -f k8s/kafka/kafka-cluster.yaml
```

Wait for the cluster to be ready (2–5 minutes for the broker to start):

```bash
kubectl get kafka aois-kafka -n kafka -w
```

Expected (once ready):
```
NAME         DESIRED KAFKA REPLICAS   READY KAFKA REPLICAS   WARNINGS
aois-kafka   1                        1                       <none>
```

Apply the topic CRDs:

```bash
kubectl apply -f k8s/kafka/kafka-topics.yaml
```

---

## ▶ STOP — do this now: Verify the k8s Kafka Cluster

Check all Kafka pods are running:

```bash
kubectl get pods -n kafka
```

Expected:
```
NAME                                          READY   STATUS    RESTARTS   AGE
aois-kafka-combined-0                         1/1     Running   0          5m
aois-kafka-entity-operator-xxxxxxxxxx-xxxxx   2/2     Running   0          3m
strimzi-cluster-operator-xxxxxxxxxx-xxxxx     1/1     Running   0          8m
```

Verify topics are ready:

```bash
kubectl get kafkatopics -n kafka
```

Expected:
```
NAME           CLUSTER      PARTITIONS   REPLICATION FACTOR   READY
aois-logs      aois-kafka   3            1                    True
aois-results   aois-kafka   3            1                    True
```

Run a quick produce-consume test inside the cluster:

```bash
# Produce a test message
kubectl exec -n kafka aois-kafka-combined-0 -- \
  /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic aois-logs \
  --property "parse.key=false" <<EOF
{"id":"test001","log":"OOMKilled: test pod killed","source":"manual","ts":0}
EOF

# Consume it back
kubectl exec -n kafka aois-kafka-combined-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic aois-logs \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 5000
```

Expected:
```
{"id":"test001","log":"OOMKilled: test pod killed","source":"manual","ts":0}
Processed a total of 1 messages
```

---

## Part 6: KEDA Kafka Trigger — Event-Driven Autoscaling

The original KEDA ScaledObject from v9 used a CPU trigger: "scale up when CPU exceeds 60%." CPU is a lagging indicator. By the time AOIS pods are burning CPU, the `aois-logs` queue has already been backed up for minutes. Incidents are waiting for analysis. The SRE team is looking at delayed alerts.

The Kafka consumer lag trigger is a leading indicator: "scale up when more than N unprocessed messages are waiting per replica." Scale-up happens *before* AOIS falls behind, not after CPU spikes.

### The Math

KEDA calculates desired replicas for the Kafka trigger as:

```
desired_replicas = ceil(total_consumer_lag / lagThreshold)
```

Where `total_consumer_lag` is the sum of lag across all partitions for the consumer group, and `lagThreshold` is your configured per-replica message budget.

With `lagThreshold=50` and `maxReplicas=5`:

| Consumer Lag | Calculation | Desired Replicas |
|---|---|---|
| 0 | ceil(0/50) | 0 (but `minReplicas=1` keeps 1 running) |
| 30 | ceil(30/50) | 1 |
| 55 | ceil(55/50) | 2 |
| 150 | ceil(150/50) | 3 |
| 200 | ceil(200/50) | 4 |
| 300+ | ceil(300/50) = 6 → capped | 5 |

This is **event-driven autoscaling**: the queue depth itself determines the scale, not a proxy metric. This is the correct pattern for any queue-processing workload.

### Why `minReplicas: 1`

Setting `minReplicas: 0` would scale AOIS to zero pods when there are no messages in `aois-logs`. This is valid if AOIS served only Kafka consumers. But AOIS also serves the HTTP `/analyze` API for the dashboard, direct calls, and the eval runner. Zero pods means the HTTP API is unavailable until a message arrives and KEDA wakes up a pod. Keep `minReplicas: 1`.

### The ScaledObject

The KEDA ScaledObject is defined in the Helm chart at `charts/aois/templates/scaledobject.yaml`. The v9 CPU trigger is replaced with a Kafka trigger:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: aois
  namespace: {{ .Release.Namespace }}
spec:
  scaleTargetRef:
    name: aois
  minReplicaCount: 1
  maxReplicaCount: 5
  cooldownPeriod: 60         # seconds after scale-down before scaling down further
  pollingInterval: 15        # KEDA checks consumer lag every 15 seconds
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: aois-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092
        consumerGroup: aois-workers
        topic: aois-logs
        lagThreshold: "50"   # must be a string in KEDA Kafka trigger
        offsetResetPolicy: latest
```

The bootstrap server address follows the Strimzi naming convention: `<cluster-name>-kafka-bootstrap.<namespace>.svc.cluster.local:9092`.

### Observing KEDA Scale-Up

With the ScaledObject applied, KEDA creates a Horizontal Pod Autoscaler (HPA) named `keda-hpa-aois`. KEDA owns the HPA — do not edit it directly.

```bash
kubectl get scaledobject aois -n aois
```

Expected:
```
NAME   SCALETARGETKIND      SCALETARGETNAME   MIN   MAX   TRIGGERS   READY   ACTIVE   FALLBACK   AGE
aois   apps/v1.Deployment   aois              1     5     kafka      True    False    False      2m
```

`ACTIVE: False` means consumer lag is currently below `lagThreshold` — no scale-up needed. `ACTIVE: True` means KEDA is actively scaling based on lag.

---

## ▶ STOP — do this now: Trigger KEDA Scale-Up

This exercise produces enough messages to build consumer lag and force KEDA to scale up AOIS pods.

First, confirm the AOIS consumer is **not** running in the cluster (let lag build):

```bash
kubectl scale deployment aois -n aois --replicas=0
```

Then produce a backlog:

```bash
# From the Hetzner node, use the internal bootstrap server
# Or: produce from local Docker Compose pointing to the k8s cluster via NodePort
# For simplicity, produce directly inside the cluster:
kubectl run kafka-producer --rm -it \
  --image=apache/kafka:3.7.0 \
  --restart=Never \
  -n kafka \
  -- /opt/kafka/bin/kafka-producer-perf-test.sh \
    --topic aois-logs \
    --num-records 300 \
    --record-size 200 \
    --throughput 50 \
    --producer-props bootstrap.servers=localhost:9092
```

Expected:
```
300 records sent, 50.0 records/sec, 0.010 MB/sec
```

Check consumer lag:

```bash
kubectl exec -n kafka aois-kafka-combined-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group aois-workers \
  --describe
```

Expected (with lag accumulating while AOIS is scaled to 0):
```
GROUP         TOPIC      PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
aois-workers  aois-logs  0          0               100             100
aois-workers  aois-logs  1          0               100             100
aois-workers  aois-logs  2          0               100             100
```

Now scale AOIS back up and watch KEDA react:

```bash
kubectl scale deployment aois -n aois --replicas=1
# Then watch the ScaledObject status
kubectl get scaledobject aois -n aois -w
```

Within 15–30 seconds (KEDA polling interval), you should see:
```
NAME   SCALETARGETKIND      SCALETARGETNAME   TRIGGERS   READY   ACTIVE
aois   apps/v1.Deployment   aois              kafka      True    True
```

Check the HPA to see the target replica count:

```bash
kubectl get hpa keda-hpa-aois -n aois
```

Expected (with 300 messages lag, lagThreshold=50):
```
NAME            REFERENCE         TARGETS         MINPODS   MAXPODS   REPLICAS
keda-hpa-aois   Deployment/aois   300/50 (avg)    1         5         5
```

KEDA calculated `ceil(300/50) = 6`, capped at `maxReplicas=5`. Watch the pods scale up:

```bash
kubectl get pods -n aois -w
```

As AOIS pods drain the `aois-logs` backlog, lag decreases, and KEDA will scale back down after the `cooldownPeriod` (60 seconds).

---

## Common Mistakes

### 1. Messages Never Appear in Topic Despite Producer Saying "Connected"

**Symptom**: producer prints `Connected to Kafka at localhost:9094` and `Done. Sent N messages` but the topic has 0 messages. Consumer gets nothing.

**Exact error** (if you look at producer logs closely):
```
WARN  [kafka.client] Unable to update metadata after 60000ms
```

Or the producer appears to succeed but the broker is rejecting writes silently.

**Cause**: the `KAFKA_ADVERTISED_LISTENERS` are wrong. The broker tells clients "reconnect to `kafka:9092`" but that hostname is only resolvable inside Docker. The host client connects, gets this metadata response, tries to reconnect to `kafka:9092`, fails, and the message is never delivered.

**Fix**:
```yaml
KAFKA_LISTENERS: INTERNAL://:9092,EXTERNAL://:9094,CONTROLLER://:9093
KAFKA_ADVERTISED_LISTENERS: INTERNAL://kafka:9092,EXTERNAL://localhost:9094
```

Then: container clients must use `kafka:9092`. Host clients must use `localhost:9094`. Mixing them causes exactly this symptom.

### 2. `NoBrokersAvailable` on First Connection

**Exact error**:
```
kafka.errors.NoBrokersAvailable: NoBrokersAvailable
```

**Cause**: `kafka-python-ng` tries to auto-detect the broker API version. This fails against Kafka 3.7+ because the version probe protocol changed.

**Fix**: specify `api_version` explicitly on every client:
```python
KafkaProducer(..., api_version=(3, 7, 0))
KafkaConsumer(..., api_version=(3, 7, 0))
```

### 3. Strimzi Kafka Cluster Stuck in `NotReady` — Version Error

**Exact error** (from `kubectl describe kafka aois-kafka -n kafka`):
```
Message: Kafka version 3.7.0 is not supported. Supported versions are: [4.1.0, 4.1.1, 4.2.0]
```

**Cause**: the Strimzi version you installed supports only recent Kafka versions. The manifest specifies an older version.

**Fix**: check the error message for supported versions. Update the manifest:
```yaml
spec:
  kafka:
    version: 4.1.0
    metadataVersion: "4.1"
```

### 4. KEDA ScaledObject Stays on Old Trigger After Helm Update

**Symptom**: `helm template` renders the Kafka trigger correctly but `kubectl get scaledobject` still shows `cpu`.

**Cause**: ArgoCD reads from the git remote. You updated the Helm chart locally but have not pushed. ArgoCD is still rendering the old chart from the last commit.

**Fix**: push first, then force sync:
```bash
git push origin main
argocd app sync aois --force
```

### 5. Consumer Processes Nothing From Existing Topic

**Symptom**: consumer starts cleanly, logs show "Connected" and "Consuming", but no analysis output appears even though messages are in the topic.

**Cause**: the consumer group `aois-workers` already has committed offsets from a previous run. Even with `auto_offset_reset="earliest"`, the consumer only uses "earliest" for groups with **no committed offset**. If the group already committed offsets at position N, the consumer starts at position N — even if that is the end of the topic.

**Fix** (for testing): reset offsets to the beginning:
```bash
# Stop the consumer first, then:
docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group aois-workers \
  --topic aois-logs \
  --reset-offsets --to-earliest --execute
```

Or use a fresh group ID for each test run:
```python
consumer = KafkaConsumer(
    *INPUT_TOPICS,
    group_id=f"aois-test-{int(time.time())}",  # unique per run
    auto_offset_reset="earliest",
    ...
)
```

### 6. Strimzi JVM OOM — Pod Restarting

**Exact error** (from `kubectl logs aois-kafka-combined-0 -n kafka`):
```
java.lang.OutOfMemoryError: Java heap space
```

Or the pod exits with exit code 137 (OOM killed by kernel).

**Cause**: no JVM heap limits set. Strimzi allocates heap proportional to container memory limit. With the default proportions and a small container, the heap is insufficient for Kafka's metadata operations.

**Fix**: add explicit JVM options to the `KafkaNodePool`:
```yaml
spec:
  jvmOptions:
    -Xms: 256m
    -Xmx: 512m
  resources:
    requests:
      memory: 512Mi
    limits:
      memory: 768Mi
```

---

## Troubleshooting

### Strimzi Pod Never Starts After `kubectl apply`

```bash
kubectl get events -n kafka --sort-by='.lastTimestamp' | tail -20
kubectl describe kafkanodepool combined -n kafka
kubectl describe kafka aois-kafka -n kafka
```

Common causes:
- Insufficient memory on the node — Kafka needs at least 768Mi, check `kubectl describe node aois`
- PVC provisioner not available — use `type: ephemeral` in `KafkaNodePool.spec.storage`
- Wrong Kafka version — the error message in `describe kafka` lists exactly which versions are supported

### KEDA ScaledObject `READY: False` After Switching to Kafka Trigger

```bash
kubectl describe scaledobject aois -n aois | grep -A 10 "Conditions"
```

Look for:
```
Message: error querying kafka: unable to reach any broker
```

This means KEDA cannot reach the Kafka bootstrap server. The bootstrap server in the ScaledObject must be the cluster-internal address:

```
aois-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092
```

Test connectivity from within the cluster:
```bash
kubectl run nettest --rm -it \
  --image=busybox --restart=Never -n keda \
  -- wget -q aois-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092 -O- 2>&1 | head -5
```

If this fails, the Kafka service is not reachable from the `keda` namespace. Check that the `aois-kafka-kafka-bootstrap` Service exists in the `kafka` namespace and has endpoints:

```bash
kubectl get svc aois-kafka-kafka-bootstrap -n kafka
kubectl get endpoints aois-kafka-kafka-bootstrap -n kafka
```

### Consumer Lag Not Decreasing Despite AOIS Pods Running

First, confirm the consumer is actually joined to the group:

```bash
kubectl exec -n kafka aois-kafka-combined-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group aois-workers \
  --describe
```

If the group shows no members (`CONSUMER-ID` column empty), the consumer is connecting to a different bootstrap server or using a different group ID.

If members are listed but lag is constant (not decreasing), the consumer is throwing analysis errors and not committing. Check AOIS pod logs:

```bash
kubectl logs -n aois -l app=aois --tail=50 | grep -i error
```

### `kafka-python-ng` Module Not Found in Container

```bash
# Confirm it's in requirements.txt (not kafka-python — that package is abandoned)
grep kafka requirements.txt
# kafka-python-ng>=2.2.3

# Rebuild the image if you added it after building
docker compose build aois
```

---

## Connection to Later Phases

**v18 (eBPF + Falco)**: Falco detects unexpected syscalls, network connections, and container behaviors at the kernel level. These Falco alerts will be published to the `aois-security` Kafka topic via Falco Sidekick. The consumer you built in v17 already subscribes to `aois-security` and handles Falco's JSON format via `extract_from_falco()`. You are building the consumer before the producer here — v18 completes the circuit.

**v19 (Chaos Engineering)**: Chaos Mesh kills pods and injects network failures. After a pod kill, consumer lag in `aois-logs` spikes as events pile up with no consumer to drain them. When AOIS recovers, KEDA scales up pods to drain the backlog. The Grafana dashboard (v16) shows the lag curve — a visible sawtooth pattern of accumulate-drain-accumulate.

**v20 (Agent Tool Use)**: the consumer loop in `consumer.py` becomes an agent trigger. Instead of only analyzing and publishing a structured result, a P1 event arriving on `aois-logs` will kick off a full LangGraph investigation: retrieve pod logs, describe the node, check metrics, formulate a hypothesis. The Kafka event is the trigger; the agent investigation is the response. The result goes to `aois-results` as a full investigation report, not just a severity classification.

**v23.5 (Agent Evals)**: the golden dataset includes log events of every category in the producer's library. The `analyze()` function called by the consumer is the same function under test. Improving the agent's accuracy on the eval dataset directly improves what the consumer produces in production. The Kafka pipeline and the eval pipeline share the same analysis logic.

---

## Mastery Checkpoint

You have completed v17 when you can do all of the following:

1. **Explain the dual-listener pattern** without looking at the notes. Reproduce the four environment variables from memory: `KAFKA_LISTENERS`, `KAFKA_ADVERTISED_LISTENERS`, which port container clients use, which port host clients use, and why mixing them causes the silent message loss bug.

2. **Describe the KEDA Kafka trigger math**: given `lagThreshold=50`, `maxReplicas=5`, and current consumer lag of 180 messages, state the desired replica count, show the calculation, and explain what `minReplicas=1` prevents.

3. **Fix the "connected but no messages" bug from symptom alone**: the producer prints success, the topic appears empty in the console consumer, the AOIS consumer processes nothing. Walk through the diagnosis and the exact fix without referring to these notes.

4. **Deploy Strimzi to a fresh cluster** from scratch: install operator, apply `KafkaNodePool` + `Kafka` + `KafkaTopic` manifests in the correct order, wait for `kubectl get kafkatopics` to show `READY: True`. Explain why the `KafkaNodePool` must be applied before the `Kafka` resource.

5. **Write a new consumer** for a new topic — say, `aois-db-events` for PostgreSQL slow query alerts. Define the event schema, the tier selection logic, the retry-on-connect pattern, and the graceful shutdown handler from scratch. You know all the pieces.

6. **Produce a backlog and observe KEDA scale-up**: stop the AOIS consumer, produce 300 messages, check consumer lag with `kafka-consumer-groups.sh`, then restart the consumer and watch `kubectl get hpa keda-hpa-aois -n aois` show decreasing lag and decreasing replica count.

7. **Explain KRaft mode** vs ZooKeeper to a junior engineer: what did ZooKeeper do, what does KRaft replace it with, and why does Strimzi require the `strimzi.io/kraft: enabled` annotation?

8. **State the v20 connection** precisely: what changes in `consumer.py` when AOIS gets agent tools, what new field appears in the `aois-results` output, and what role Kafka plays in the autonomous SRE loop.

**The mastery bar:** given a new AI service with a queue of work — model inference requests, document processing, alert triage — you can design and deploy a Kafka + KEDA autoscaling pipeline: producer, consumer, topic config, ScaledObject, all in under 2 hours. That is an infrastructure pattern worth $50,000 per year in compute savings at scale, and it is the architecture pattern behind every high-throughput AI pipeline in production today.

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### Apache Kafka

| Layer | Question |
|---|---|
| **Plain English** | A high-throughput message queue where producers write events and consumers read them — designed to handle millions of events per second and retain them for days. If consumers fall behind or crash, events pile up but are never lost. When consumers catch up, they replay from exactly where they stopped. |
| **System Role** | Kafka is AOIS's real-time log ingestion backbone. Applications publish log events to the `aois-logs` topic. The AOIS consumer reads them, calls the LLM, and publishes structured results to `aois-results`. Falco publishes security alerts to `aois-security`. Kafka decouples event production from analysis — a spike in log volume builds consumer lag, KEDA scales consumers to drain it, and no events are lost regardless of how long AOIS is down. |
| **Technical** | Kafka is a distributed commit log. Topics are partitioned — each partition is an ordered, immutable sequence of records identified by monotonically increasing offsets. Consumers track their offset per-partition, per-consumer-group. Multiple consumer groups can read the same topic independently at different positions. KRaft mode replaces ZooKeeper with Kafka's own Raft-based metadata consensus — one process instead of two. Retention is configurable: time-based (`log.retention.hours`) or size-based (`log.retention.bytes`). |
| **Remove it** | Without Kafka, AOIS receives logs via HTTP POST — synchronous, lossy, unbuffered. A 10× traffic spike means either dropped logs, a saturated AOIS process, or a memory queue that dies with the pod. A 30-minute deploy window means 30 minutes of lost log events. Kafka's durability guarantee: a log event written to a topic is retained regardless of what happens to consumers or AOIS pods. This is the architectural difference between a demo system and a production SRE tool. |

**Say it at three levels:**

- *Non-technical:* "Kafka is a conveyor belt for data. One part of the system places events on the belt; another part picks them up. If the second part slows down or stops, the events just queue up on the belt — they do not fall off. When it restarts, it picks up exactly where it left off."

- *Junior engineer:* "Producer: `KafkaProducer(bootstrap_servers='localhost:9094', api_version=(3, 7, 0))` then `producer.send('aois-logs', value=json.dumps(event).encode())`. Consumer: `KafkaConsumer('aois-logs', group_id='aois-workers', bootstrap_servers='localhost:9094', api_version=(3, 7, 0))` then `for msg in consumer`. Consumer groups: two consumers in the same `group_id` split the partitions — horizontal scaling. Two consumers in different `group_id`s each receive every message — fan-out. Consumer lag = log-end-offset minus current-offset — the backlog KEDA watches."

- *Senior engineer:* "Kafka's performance comes from sequential disk I/O — producers append to partition logs, consumers read sequentially from an offset. Random I/O is avoided entirely. Consumer lag is the production health signal: `kafka-consumer-groups.sh --describe` shows per-partition lag per consumer group. KEDA's Kafka scaler reads this via the Kafka AdminClient API and feeds it into the HPA. The AOIS setup (ephemeral storage, single broker, replication factor 1) is dev-grade — production requires persistent volumes, `replication.factor=3`, `min.insync.replicas=2`, and rack-aware partition assignment. The absence of these in dev is a deliberate trade-off, not an oversight."

---

### Strimzi Operator

| Layer | Question |
|---|---|
| **Plain English** | A Kubernetes add-on that lets you manage Kafka using the same `kubectl apply` workflow you use for everything else — instead of running complex Kafka administration commands manually or writing StatefulSet YAML from scratch. |
| **System Role** | Strimzi is how Kafka runs on the Hetzner k3s cluster. Without Strimzi, deploying Kafka to Kubernetes requires authoring StatefulSets, headless Services, init containers, and PodDisruptionBudgets manually — a week of work with ongoing operational burden. With Strimzi, `kubectl apply -f kafka-cluster.yaml` creates a production-configured Kafka cluster. ArgoCD manages Strimzi resources with the same GitOps flow it uses for AOIS. |
| **Technical** | Strimzi installs Custom Resource Definitions: `Kafka`, `KafkaNodePool`, `KafkaTopic`, `KafkaUser`. The `strimzi-cluster-operator` pod watches these CRDs and reconciles actual Kafka StatefulSets to match the declared spec. `KafkaNodePool` (Strimzi 0.36+) replaced the monolithic `spec.kafka` node configuration — it enables different resource profiles for broker vs. controller roles and is required for KRaft mode. Kafka version upgrades: change `spec.kafka.version` in the CR and Strimzi performs a rolling restart, one broker at a time. |
| **Remove it** | Without Strimzi, Kafka on Kubernetes is a hand-maintained StatefulSet. Rolling upgrades require manual coordination. Broker scaling requires updating the StatefulSet replica count and rebalancing partitions by hand. Topic management requires SSH-ing to a broker and running `kafka-topics.sh`. The operator encodes five years of Kafka-on-Kubernetes operational knowledge into a reconciliation loop. The trade-off: debugging requires understanding both Kafka internals and the operator's reconciliation state machine. |

**Say it at three levels:**

- *Non-technical:* "Strimzi is the automatic manager for Kafka on Kubernetes. You describe what you want — one Kafka cluster, these settings, these topics — and Strimzi handles all the details of making it happen and keeping it running, including upgrades."

- *Junior engineer:* "`kubectl apply -f kafka-cluster.yaml` creates a `Kafka` CR. The operator sees it and creates the StatefulSet, Services, and ConfigMaps. Add a topic: `kubectl apply -f kafka-topics.yaml` with a `KafkaTopic` CR — the Topic Operator creates it in Kafka automatically. Check status: `kubectl get kafka aois-kafka -n kafka`. If something is wrong: `kubectl describe kafka aois-kafka -n kafka` — the `Conditions` section has the error."

- *Senior engineer:* "Strimzi's KRaft support requires KafkaNodePool (introduced in 0.36) — the combined controller+broker role is declared there. The resource gap to watch: Strimzi does not set JVM heap options by default — add explicit `-Xms`/`-Xmx` in `KafkaNodePool.spec.jvmOptions`, otherwise Kafka sizes its own heap proportional to the container limit and gets it wrong for small containers. Reconciliation loop is 2 minutes — a CR change takes up to 2 minutes plus rolling restart time to apply. For the entity operator: `topicOperator` and `userOperator` are separate pods — if either crashes, topic/user CRD changes stop being reconciled but the Kafka cluster itself continues running."

---

### KEDA (Kafka Trigger)

| Layer | Question |
|---|---|
| **Plain English** | KEDA watches how many unprocessed messages are waiting in the Kafka queue. When the backlog grows, it adds more AOIS pods to drain it faster. When the queue is empty, it removes extra pods. AOIS only runs as many pods as the current workload actually needs. |
| **System Role** | KEDA sits between the Kafka consumer lag metric and the Kubernetes Deployment. It reads consumer lag from Kafka every 15 seconds and adjusts the AOIS replica count according to the `lagThreshold` formula. The CPU-based trigger from v9 is replaced — consumer lag is a better signal for a queue-processing workload than CPU utilization. |
| **Technical** | KEDA's Kafka scaler connects to the Kafka broker using the AdminClient API, queries the consumer group offset and log-end offset for the configured topic, computes lag, and feeds it to the Horizontal Pod Autoscaler as a custom metric. The HPA then scales the Deployment. Formula: `desired = ceil(totalLag / lagThreshold)`, clamped to `[minReplicaCount, maxReplicaCount]`. The `cooldownPeriod` prevents rapid scale-down oscillation after a traffic burst. |
| **Remove it** | Without KEDA Kafka trigger: AOIS scales on CPU. Consumer lag can be 500 messages and CPU can be at 10% — because the bottleneck is LLM API latency, not CPU. The CPU trigger never fires. AOIS stays at one pod. The backlog grows. Incidents sit unanalyzed for minutes. With the Kafka lag trigger, AOIS scales up the moment the queue starts building — before CPU is affected at all. |

**Say it at three levels:**

- *Non-technical:* "KEDA is a traffic manager for AOIS. When work piles up, it opens more lanes (adds pods). When work is light, it closes lanes (removes pods). You pay only for what you actually use."

- *Junior engineer:* "The ScaledObject defines: `minReplicaCount: 1`, `maxReplicaCount: 5`, and a Kafka trigger with `lagThreshold: '50'`. KEDA creates an HPA named `keda-hpa-aois`. Check current state: `kubectl get scaledobject aois -n aois`. See the HPA target: `kubectl get hpa keda-hpa-aois -n aois`. Watch scaling: `kubectl get pods -n aois -w`."

- *Senior engineer:* "KEDA's Kafka scaler polls every `pollingInterval` seconds (default 30, configured to 15 in AOIS). The `lagThreshold` is per-replica, not total — KEDA divides total lag by the current replica count to compute average lag per replica, then calculates how many replicas are needed to bring per-replica lag below the threshold. For multi-partition topics, lag is summed across all partitions. The `offsetResetPolicy: latest` means if there is no existing consumer group offset, KEDA starts from the latest — it does not count historical messages that predate the consumer group as lag."
