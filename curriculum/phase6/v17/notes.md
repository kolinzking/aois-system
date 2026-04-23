# v17 — Kafka: Real Log Streaming
⏱ **Estimated time: 4–6 hours**

*Phase 6 — Full SRE Observability Stack. v16 made every LLM call visible. v17 makes every log event flow.*

---

## What this version builds

Every previous version of AOIS receives logs via HTTP POST — one log, one request, one response. That's a pull model: the caller decides when to analyze. Production doesn't work that way. Production systems emit thousands of events per second. The right model is push: infrastructure fires log events into a stream, AOIS consumes them continuously, and the number of AOIS instances scales with the backlog.

Kafka is how this works at Netflix, Cloudflare, Uber, and every company running SRE at scale. Kafka is a distributed commit log: producers append events, consumers read at their own pace, and every message is durably stored with a configurable retention window. The consumer can fall behind, catch up, replay from any offset, and the producer never blocks.

At the end of v17:
- **Local**: Kafka in Docker Compose (apache/kafka:3.7.0, KRaft mode — no ZooKeeper)
- **Producer**: `kafka/producer.py` — simulates infrastructure emitting SRE log events to `aois-logs` at configurable rate
- **Consumer**: `kafka/consumer.py` — long-lived worker that reads from `aois-logs`, calls `analyze()`, publishes results to `aois-results`
- **k8s**: Strimzi operator + Kafka 4.1.0 cluster on Hetzner k3s — `aois-logs` and `aois-results` topics, managed by KafkaTopic CRDs
- **KEDA**: ScaledObject updated from CPU trigger to Kafka consumer lag trigger — AOIS pods scale when unprocessed messages pile up, idle when the queue is empty

---

## Prerequisites

```bash
# Docker Compose running (from v16)
docker compose ps | grep kafka
# Expected: aois-system-kafka-1 ... Up

# Hetzner cluster reachable
kubectl get nodes
# Expected: ubuntu-8gb-nbg1-1   Ready   control-plane

# kafka-python-ng installed
python3 -c "from kafka import KafkaProducer; print('ok')"
# Expected: ok

# KEDA running on cluster
kubectl get pods -n keda | grep keda-operator
# Expected: keda-operator-...   1/1   Running
```

---

## Learning Goals

By the end of v17 you will be able to:

- Explain why Kafka is used instead of HTTP for high-volume log streaming
- Describe the producer-consumer-topic model and what consumer groups enable
- Configure a Kafka consumer with correct `auto_offset_reset`, `group_id`, and error handling
- Deploy a Kafka cluster to Kubernetes using Strimzi operator (declare-and-forget pattern)
- Switch KEDA from CPU-based to Kafka-consumer-lag-based autoscaling
- Explain what `lagThreshold` means and how it determines the desired replica count
- Test the full pipeline end-to-end: produce logs → consume → analyze → publish results

---

## Part 1: Why Kafka for AOIS

The HTTP model breaks at scale. Consider 10,000 log events per minute:
- HTTP model: 10,000 POST requests per minute. Each request ties up a thread in AOIS. Rate limits kick in. Retries need coordination. If AOIS restarts, in-flight requests are lost.
- Kafka model: 10,000 events appended to `aois-logs`. AOIS consumers read at their own pace. If AOIS restarts mid-batch, it resumes from the last committed offset. No messages lost.

Three Kafka guarantees that matter for AOIS:

**Durability**: every event written to `aois-logs` is persisted to disk and replicated. It does not disappear if the broker restarts or a consumer crashes.

**Consumer groups**: multiple AOIS pods can be in the same consumer group (`aois-workers`). Kafka assigns partitions to group members. With 3 partitions and 3 pods, each pod owns one partition. Adding more AOIS pods increases throughput up to the partition count.

**Replay**: consumer lag is a first-class metric. When AOIS is down for 30 minutes, 30 minutes of logs pile up in the topic. When AOIS comes back, it reads from where it left off. No events are lost, just delayed.

---

## Part 2: Kafka in Docker Compose (KRaft Mode)

KRaft (Kafka Raft) is Kafka 3.x's replacement for ZooKeeper. Instead of a separate ZooKeeper cluster managing metadata, Kafka nodes elect a controller among themselves using the Raft consensus algorithm. The result: one process instead of two, simpler configuration, faster startup.

The `apache/kafka:3.7.0` image runs in KRaft mode by default. Key environment variables:

```yaml
KAFKA_PROCESS_ROLES: broker,controller        # this node is both broker and controller
KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093  # one voter: node 1 at kafka:9093
KAFKA_LISTENERS: INTERNAL://:9092,EXTERNAL://:9094,CONTROLLER://:9093
KAFKA_ADVERTISED_LISTENERS: INTERNAL://kafka:9092,EXTERNAL://localhost:9094
```

**Two listener pattern** — the key networking detail for local development:

Container-to-container traffic (AOIS → Kafka in Docker Compose) uses `INTERNAL://kafka:9092`. The Docker network resolves `kafka` to the broker container.

Host traffic (your Python scripts) uses `EXTERNAL://localhost:9094`. When a Python client connects to `localhost:9094`, Kafka redirects metadata requests to the advertised listener for that connection. Without this split, the Python client connects on port 9092 but gets told "your broker is at `kafka:9092`" — which fails because `kafka` isn't resolvable outside Docker.

This is the most common Kafka networking mistake. The symptom: producer says "connected" but messages never appear in the topic.

---

## ▶ STOP — do this now

Start the full stack and verify Kafka is reachable:

```bash
docker compose up -d
docker compose ps kafka
```

Expected: `STATUS: Up`

Create topics and verify:

```bash
docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic aois-logs --partitions 3 --replication-factor 1 --if-not-exists

docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list
```

Expected:
```
Created topic aois-logs.
aois-logs
aois-results
```

Send 5 test messages and verify they land:

```bash
python3 kafka/producer.py --count 5 --rate 5
```

Expected:
```
Connected to Kafka at localhost:9094
Publishing to 'aois-logs' at 5.0 msg/sec, total 5
Done. Sent 5 messages to 'aois-logs'.
```

```bash
docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic aois-logs --from-beginning --max-messages 5 --timeout-ms 5000
```

Expected: 5 JSON lines, each with `id`, `log`, `source`, `ts` fields.

---

## Part 3: The Consumer

`kafka/consumer.py` is the heart of v17. It's a long-lived process with four responsibilities:

**1. Connect with retry** — Kafka may not be ready at container startup. The consumer retries 12 times (60 seconds total) before giving up. This is the correct pattern for any service that depends on Kafka being available.

**2. Read, analyze, publish** — for each message on `aois-logs`:
```python
event = message.value           # {"id": "abc123", "log": "OOMKilled...", ...}
result = analyze(event["log"], tier)
output = {"id": event["id"], "severity": result.severity, ...}
producer.send("aois-results", value=output)
```

**3. Smart tier selection** — `get_tier_for_log()` does a quick pre-filter: logs containing "OOMKilled", "CrashLoop", "NotReady", "503" get routed to `premium` (Claude). Everything else goes to `fast` (Groq). This avoids the overhead of a two-pass analysis for most events.

**4. Graceful shutdown** — `SIGTERM` and `SIGINT` handlers set `running = False`, which exits the loop, flushes the producer, and closes the consumer. Clean shutdown means committed offsets are correct and no duplicate processing on restart.

**`api_version=(3, 7, 0)`**: `kafka-python-ng` auto-detects Kafka version by probing the broker API. This auto-detection fails against Kafka 3.7+ because the handshake protocol changed. Providing the version explicitly bypasses the detection step and connects immediately.

---

## ▶ STOP — do this now

Run the full end-to-end pipeline:

```bash
# Terminal 1: start the consumer
python3 kafka/consumer.py
```

Expected:
```
{"level":"INFO","logger":"aois.kafka","message":"Connected to Kafka at localhost:9094"}
{"level":"INFO","logger":"aois.kafka","message":"Consuming from 'aois-logs' → publishing to 'aois-results'"}
```

```bash
# Terminal 2: send a burst of messages
python3 kafka/producer.py --count 10 --rate 5
```

Expected in Terminal 1 (one line per message analyzed):
```
[abc123] P1 — aois-api container exceeded memory limit and was killed (premium, 1823ms, $0.016000)
[def456] P3 — DNS resolution failed for Redis service in cluster (fast, 334ms, $0.000001)
...
```

Verify results in `aois-results`:

```bash
docker exec aois-system-kafka-1 /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic aois-results --from-beginning --max-messages 5 --timeout-ms 5000
```

Expected: JSON objects with `severity`, `summary`, `cost_usd`, `duration_ms` fields.

---

## Part 4: Strimzi — Kafka on Kubernetes

Running Kafka yourself on Kubernetes is complex: stateful sets, pod disruption budgets, rolling upgrades, storage management, topic management. Strimzi wraps all of this in a Kubernetes operator.

The operator pattern: you declare what you want (`kind: Kafka`, `kind: KafkaTopic`), Strimzi reconciles the actual state to match. Rolling upgrades? Strimzi handles them. Topic with wrong partition count? Strimzi fixes it. This is the same pattern as cert-manager for TLS and KEDA for autoscaling — the Kubernetes operator model applied to Kafka.

**Strimzi resource hierarchy:**
```
KafkaNodePool     — describes a group of nodes (broker+controller in KRaft mode)
Kafka             — cluster declaration: version, listeners, config
KafkaTopic        — individual topic with retention, partitions, replication
KafkaUser         — ACLs and authentication (not used in this version)
```

**KRaft mode** removes ZooKeeper from the equation entirely. In Strimzi, enable it with:
```yaml
metadata:
  annotations:
    strimzi.io/node-pools: enabled
    strimzi.io/kraft: enabled
```

**Version pinning**: Strimzi `latest` moves quickly. The Strimzi release installed in April 2026 supports Kafka 4.1.0, 4.1.1, 4.2.0. Kafka 3.7.0 is not supported. Always check `kubectl describe kafka aois-kafka -n kafka` if the cluster won't start — the error message lists supported versions explicitly.

---

## ▶ STOP — do this now

Verify Kafka is running on the Hetzner cluster:

```bash
kubectl get pods -n kafka
```

Expected:
```
NAME                                          READY   STATUS    RESTARTS   AGE
aois-kafka-combined-0                         1/1     Running   0          Xm
aois-kafka-entity-operator-...               1/1     Running   0          Xm
strimzi-cluster-operator-...                 1/1     Running   0          Xm
```

Verify topics:

```bash
kubectl get kafkatopics -n kafka
```

Expected:
```
NAME           CLUSTER      PARTITIONS   REPLICATION FACTOR   READY
aois-logs      aois-kafka   3            1                    True
aois-results   aois-kafka   3            1                    True
```

Verify KEDA ScaledObject uses Kafka trigger:

```bash
kubectl get scaledobject aois -n aois
```

Expected: `TRIGGERS` column shows `kafka`, `READY` is `True`.

---

## Part 5: KEDA Kafka Trigger — Event-Driven Autoscaling

The original KEDA ScaledObject used a CPU trigger: "scale up when CPU exceeds 60%." CPU is a lagging indicator — by the time CPU spikes, the queue is already full.

The Kafka trigger is a leading indicator: "scale up when consumer lag exceeds 50 messages per replica." Scale-up happens before AOIS falls behind, not after.

How KEDA calculates desired replicas with the Kafka trigger:

```
desired_replicas = ceil(consumer_lag / lagThreshold)
```

With `lagThreshold=50`:
- Lag = 0: desired = 0 (or minReplicas if set to 1)
- Lag = 50: desired = 1
- Lag = 200: desired = 4
- Lag = 250: desired = 5 (capped at maxReplicas)

This is **event-driven autoscaling**: the workload itself determines the scale, not a proxy metric like CPU. This is the correct pattern for queue-processing workloads, AI analysis pipelines, and any system where the job is "drain this queue."

`minReplicas: 1` keeps one pod alive (AOIS serves HTTP as well as Kafka). Setting `minReplicas: 0` would scale-to-zero — valid if AOIS was Kafka-only, but wrong here since `/analyze` HTTP needs to be available.

---

## Common Mistakes

### 1. Messages never appear in topic despite producer saying "Connected"

**Symptom**: producer prints "Connected" and "Done. Sent N messages" but the topic has 0 messages.

**Cause**: Kafka's advertised listener mismatch. The broker tells clients "connect to `kafka:9092`" but the client is running on the host where `kafka` isn't resolvable.

**Fix**: dual-listener pattern. Expose a separate EXTERNAL listener on a host-accessible port (9094) with `EXTERNAL://localhost:9094` as the advertised address.

```yaml
KAFKA_LISTENERS: INTERNAL://:9092,EXTERNAL://:9094,CONTROLLER://:9093
KAFKA_ADVERTISED_LISTENERS: INTERNAL://kafka:9092,EXTERNAL://localhost:9094
```

Host clients use `localhost:9094`. Container clients use `kafka:9092`.

### 2. `kafka.errors.NodeNotReadyError` on KafkaAdminClient

**Symptom**: Python `KafkaAdminClient` crashes immediately with `NodeNotReadyError`.

**Cause**: `kafka-python-ng` tries to auto-detect the broker's API version by connecting and probing. This probe fails against Kafka 3.7+ due to protocol changes.

**Fix**: specify `api_version` explicitly on every client — producer, consumer, admin:

```python
consumer = KafkaConsumer(..., api_version=(3, 7, 0))
producer = KafkaProducer(..., api_version=(3, 7, 0))
```

For topic creation, use the Kafka CLI inside the container instead of `KafkaAdminClient`:
```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic my-topic --partitions 3 --replication-factor 1
```

### 3. Strimzi Kafka cluster stuck in `NotReady` with version error

**Symptom**: `kubectl describe kafka aois-kafka -n kafka` shows `Unsupported Kafka.spec.kafka.version: 3.7.0`.

**Cause**: Strimzi `latest` is installed, which only supports recent Kafka versions. The version you specified is too old.

**Fix**: check supported versions from the error message, update the manifest:
```yaml
spec:
  kafka:
    version: 4.1.0       # match what the installed Strimzi supports
    metadataVersion: "4.1"
```

### 4. KEDA ScaledObject stays on old trigger after Helm update

**Symptom**: `helm template` renders Kafka trigger, but `kubectl get scaledobject` still shows `cpu`.

**Cause**: ArgoCD reads from the git remote. If you haven't pushed, it reads old values. Even after pushing, ArgoCD may have a cached diff and not detect the change.

**Fix**: push first, then force ArgoCD sync:
```bash
git push origin main
kubectl -n argocd patch application aois --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD","syncStrategy":{"hook":{}}}}}'
```

### 5. Consumer picks up no messages from existing topic

**Symptom**: consumer connects cleanly but logs only show "Connected" and "Consuming" — no analysis output.

**Cause**: the consumer group already committed offsets from a previous run (even one that processed zero messages). With `auto_offset_reset=earliest`, the consumer only uses "earliest" for groups with no committed offset. If the group exists with offsets already at the latest position, new `earliest` consumers still start at the committed position.

**Fix for testing**: use a fresh `group_id` each test run, or reset offsets:
```bash
docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group aois-workers \
  --topic aois-logs \
  --reset-offsets --to-earliest --execute
```

---

## Troubleshooting

### Strimzi pod never starts after `kubectl apply`

```bash
kubectl get events -n kafka --sort-by='.lastTimestamp' | tail -10
kubectl describe kafkanodepool combined -n kafka
```

Common causes: insufficient memory on the node (Kafka needs ~1GB), PVC provisioner not available (use ephemeral storage for k3s), wrong Kafka version.

### KEDA `READY: False` after switching to Kafka trigger

```bash
kubectl describe scaledobject aois -n aois | grep -A5 "Conditions"
```

Common cause: KEDA can't reach the Kafka broker. The bootstrap server must be reachable from the KEDA namespace. Internal service name format: `<cluster>-kafka-bootstrap.<namespace>.svc.cluster.local:9092`.

```bash
# Test connectivity from within the cluster
kubectl run -it --rm nettest --image=busybox --restart=Never -n keda -- \
  wget -q aois-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092 -O- 2>&1 | head -3
```

### Consumer lag not decreasing despite AOIS pods running

Check that the consumer is actually joined to the group:

```bash
kubectl exec -n kafka aois-kafka-combined-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group aois-workers --describe
```

If the group shows no members, the consumer is connecting to a different bootstrap server or group ID.

---

## Connection to Later Phases

**v18 (eBPF + Falco)**: Falco detects unexpected syscalls, network connections, and process behaviors. These Falco alerts are SRE log events — they will be published to `aois-logs` and consumed by the AOIS worker, giving you AI-analyzed security telemetry.

**v19 (Chaos Engineering)**: Chaos Mesh injects failures. After a node kill, the consumer lag in `aois-logs` will spike as events pile up — KEDA scales AOIS to drain the backlog. The Kafka consumer lag metric in Grafana shows the before/after clearly.

**v20 (Tool use + agents)**: the consumer loop becomes an agent trigger. Instead of just analyzing and publishing, AOIS will kick off a full investigation workflow when it receives a P1 event on `aois-logs`. The agent's findings go to `aois-results` alongside the structured analysis. Kafka is the event bus for the autonomous SRE loop.

---

## Mastery Checkpoint

You have completed v17 when you can do all of the following:

1. **Explain the dual-listener pattern** and reproduce it from memory: why two listeners, what each advertises, which port each client uses.

2. **Describe the KEDA Kafka trigger math**: given `lagThreshold=50`, `maxReplicas=5`, and `lag=180`, state the desired replica count and explain why.

3. **Fix the "connected but no messages" bug** from symptom alone: producer says success, topic is empty, consumer gets nothing.

4. **Deploy Strimzi to a fresh cluster** from scratch: install operator, apply KafkaNodePool + Kafka + KafkaTopic manifests, verify `kubectl get kafkatopics` shows `READY: True`.

5. **Write a new consumer** for a different topic — say, Falco alerts to `aois-security-logs`. You know the pattern: retry connect, read, call `analyze()`, publish result, handle errors, graceful shutdown.

6. **Observe consumer lag in real time**: while the consumer is stopped, send 100 messages, then start the consumer and watch KEDA scale up.

7. **Explain KRaft mode** vs ZooKeeper: what changed, what it removes, and why Strimzi requires the `strimzi.io/kraft: enabled` annotation.

8. **State the v20 connection**: how the Kafka consumer loop becomes the trigger for autonomous investigation, and what the `aois-results` topic contains in an agent workflow.

**The mastery bar:** given a new AI service with a queue of work (model inference requests, document processing, alert triage), you can wire up Kafka + KEDA so the service scales automatically on queue depth, zero-to-N and back to zero. That is an infrastructure pattern worth $50k in annual compute savings at scale.

---

*Phase 6 continues. v18 brings eBPF and Falco — kernel-level observability and runtime security alerts, consumed by the Kafka pipeline you just built.*

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### Apache Kafka

| Layer | |
|---|---|
| **Plain English** | A high-throughput message queue where producers write events and consumers read them — designed to handle millions of events per second and retain them for days, so nothing is lost even if consumers are temporarily offline. |
| **System Role** | Kafka is AOIS's real-time log ingestion backbone. Applications publish log events to the `aois-logs` topic. The AOIS consumer reads them, calls the LLM, and publishes results to `aois-results`. Falco publishes security alerts to `aois-security`. Kafka decouples event production from analysis — a spike in log volume doesn't overwhelm AOIS, it builds up in the topic and KEDA scales consumers to drain it. |
| **Technical** | Kafka is a distributed commit log. Topics are partitioned — each partition is an ordered, immutable sequence of records with a monotonically increasing offset. Consumers track their offset independently — multiple consumer groups can read the same topic at different positions. KRaft mode (used here) replaces ZooKeeper with Kafka's own Raft-based metadata consensus. Retention is time-based (`log.retention.hours=24`) or size-based. |
| **Remove it** | Without Kafka, AOIS receives logs via direct HTTP POST — synchronous, lossy, and unbuffered. A 10× traffic spike means either dropped logs or a queue in memory that dies with the process. Kafka's durability guarantee: a log event written to a topic is retained for 24 hours regardless of what happens to consumers or AOIS pods. This is the difference between a demo system and a production SRE tool. |

**Say it at three levels:**
- *Non-technical:* "Kafka is a conveyor belt for data. Events are placed on the belt by one part of the system and picked up by another — at whatever speed each side can manage. The belt holds the events until they're consumed, so nothing falls off if one side is slow."
- *Junior engineer:* "Producer: `KafkaProducer(bootstrap_servers='...')` then `producer.send('aois-logs', value=json.dumps(event).encode())`. Consumer: `KafkaConsumer('aois-logs', group_id='aois-analyzer', bootstrap_servers='...')` then loop over messages with `for msg in consumer`. Consumer groups: two consumers in the same `group_id` split the partitions — horizontal scaling. Two consumers in different `group_id`s both get every message — fan-out."
- *Senior engineer:* "Kafka's performance comes from sequential disk I/O — producers append to the end of partition logs, consumers read sequentially. Random I/O is avoided entirely. Consumer lag is the production health metric: `kafka-consumer-groups.sh --describe` shows how far behind each consumer group is. KEDA's Kafka trigger scales AOIS pods on `lagThreshold` — when lag exceeds 50 messages per partition, a new pod is provisioned. The AOIS setup (ephemeral storage, single partition) is dev-grade — production requires persistent volumes, replication factor ≥ 3, and rack-aware partition assignment."

---

### Strimzi Operator

| Layer | |
|---|---|
| **Plain English** | A Kubernetes add-on that lets you manage Kafka using the same `kubectl apply` workflow you use for everything else — instead of managing Kafka separately with its own tooling. |
| **System Role** | Strimzi is how Kafka runs on the Hetzner k3s cluster. Without Strimzi, deploying Kafka to Kubernetes requires writing StatefulSets, Services, ConfigMaps, and init containers manually — a week of work. With Strimzi, `kubectl apply -f kafka-cluster.yaml` creates a production-configured Kafka cluster. ArgoCD manages Strimzi resources the same way it manages AOIS. |
| **Technical** | Strimzi installs CRDs: `Kafka`, `KafkaNodePool`, `KafkaTopic`, `KafkaUser`. The `strimzi-cluster-operator` pod watches these CRDs and reconciles the actual Kafka StatefulSets to match the desired spec. `KafkaNodePool` (v14+ Strimzi) replaced the monolithic `spec.kafka` for node configuration — it enables different resource profiles for broker vs controller roles. Kafka version upgrades are handled by changing `spec.kafka.version` and letting the operator roll the cluster. |
| **Remove it** | Without Strimzi, Kafka on Kubernetes is a manual StatefulSet that doesn't handle rolling upgrades, broker scaling, TLS cert rotation, or user management. The operator encodes 5+ years of Kafka-on-Kubernetes operational knowledge into a reconciliation loop. The trade-off: Strimzi adds a layer of abstraction — debugging requires understanding both Kafka internals and the operator's reconciliation state. The `kubectl get kafka -o yaml` status conditions are the debugging entry point. |

**Say it at three levels:**
- *Non-technical:* "Strimzi is the middle manager for Kafka on Kubernetes. You describe what you want (one Kafka cluster, these settings), and Strimzi figures out all the details of making it happen and keeping it running."
- *Junior engineer:* "`kubectl apply -f kafka-cluster.yaml` creates a `Kafka` CR. The Strimzi operator sees it and creates the StatefulSet, Services, and ConfigMaps automatically. Add a topic: `kubectl apply -f kafka-topics.yaml` with a `KafkaTopic` CR. Check status: `kubectl get kafka aois-kafka -n kafka -o jsonpath='{.status.conditions}'`. The operator handles the Kafka broker startup sequence — you never run `kafka-server-start.sh` manually."
- *Senior engineer:* "Strimzi's KRaft support (Kafka 3.3+) eliminates ZooKeeper — the operator manages the combined controller+broker nodes via `KafkaNodePool`. The resource management gap we hit on AOIS: Strimzi doesn't set JVM options or resource limits by default — the operator creates pods with unbounded memory. Always add `jvmOptions` and `resources` to `KafkaNodePool.spec` before running in any environment where memory contention is possible. The operator reconciles on a 2-minute loop — changes to the CR take up to 2 minutes plus rolling restart time to apply."
