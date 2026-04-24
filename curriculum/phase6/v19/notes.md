# v19 — Chaos Engineering: Breaking AOIS on Purpose

⏱ **Estimated time: 6–8 hours**

---

## Prerequisites

k3s running on Hetzner with Strimzi Kafka, KEDA, Falco, and the full v18 pipeline.

```bash
# Cluster is healthy
sudo kubectl get nodes --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME   STATUS   ROLES           AGE   VERSION
# aois   Ready    control-plane   ...   v1.34.6+k3s1

# AOIS pods are running
sudo kubectl get pods -n aois --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                    READY   STATUS    RESTARTS
# aois-xxxxxxxxxx-xxxxx   1/1     Running   0

# Kafka pipeline is healthy
sudo kubectl get pods -n kafka --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                                         READY   STATUS
# aois-kafka-dual-role-0                       1/1     Running
# strimzi-cluster-operator-xxxxxxxxxx-xxxxx    1/1     Running

# Falco is running
sudo kubectl get pods -n falco --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                                   READY   STATUS
# falco-xxxxx                            2/2     Running

# KEDA is active
sudo kubectl get scaledobject -n aois --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME   SCALETARGETKIND   SCALETARGETNAME   MIN   MAX   TRIGGERS   READY
# aois   Deployment        aois              1     5     kafka      True

# Helm is available
helm version --short
# v3.x.x
```

---

## Learning Goals

By the end you will be able to:

- Explain what chaos engineering is and why "hoping nothing breaks" is not a reliability strategy
- Install Chaos Mesh on k3s and verify the CRDs and controller are healthy
- Define and enforce an SLO for AOIS using a measurable, alertable metric
- Run five distinct chaos experiments targeting pods, network, CPU, and upstream dependencies
- Use Prometheus and Grafana to observe system behaviour *during* chaos, not just after
- Measure MTTR (mean time to recovery) with a repeatable methodology
- Explain the difference between breaking a system accidentally and breaking it deliberately
- Run a structured game day and produce a written incident report from it

---

## The Problem This Solves

You have built a system that claims to detect and respond to incidents faster than a human. That claim has never been tested under adversarial conditions.

Every system works in the happy path. Staging environments, demos, dev clusters — all of these confirm the happy path. What they do not confirm is whether your system degrades gracefully, recovers automatically, and alerts correctly when things actually go wrong.

The uncomfortable truth about SRE work: you will find out how your system fails one of two ways.

1. **In production**, at 3am, with users affected, because some combination of events you did not anticipate caused cascading failure.
2. **In a chaos session**, during business hours, deliberately, with metrics running, so you can observe and fix it before users experience it.

Netflix coined this practice "chaos engineering" and ran it on their production cluster. Kubernetes itself was chaos-tested before it was stable. Every system that claims to be resilient has either been deliberately broken or is resilient only by assumption.

Chaos Mesh gives you option 2.

---

## What Chaos Mesh Is

Chaos Mesh is a cloud-native chaos engineering platform built for Kubernetes. It installs as a set of CRDs (Custom Resource Definitions) and controllers into your cluster. To run a chaos experiment, you apply a YAML manifest — the same workflow you use for any k8s resource. Chaos Mesh reads the manifest, targets the specified pods or network path, and injects the failure.

### What Chaos Mesh Can Inject

| Experiment Type | What It Does | Kubernetes Kind |
|---|---|---|
| **PodChaos** | Kill, pause, or kill-and-restart pods | `PodChaos` |
| **NetworkChaos** | Inject latency, packet loss, bandwidth limits, corruption | `NetworkChaos` |
| **StressChaos** | Drive CPU or memory consumption | `StressChaos` |
| **IOChaos** | Inject disk I/O latency or errors | `IOChaos` |
| **DNSChaos** | Return wrong DNS responses | `DNSChaos` |
| **TimeChaos** | Skew the system clock | `TimeChaos` |
| **HTTPChaos** | Inject HTTP errors, delays, body corruption | `HTTPChaos` |

For AOIS in v19 you will use PodChaos, NetworkChaos, and StressChaos — the three most common failure modes in production Kubernetes.

### The Chaos Mesh Architecture

```
┌─────────────────────────────────────┐
│              Your Cluster            │
│                                     │
│  kubectl apply chaos-experiment.yaml│
│          ↓                          │
│  ┌─────────────────────┐            │
│  │  Chaos Mesh CRDs    │            │
│  │  (PodChaos, etc.)   │            │
│  └──────────┬──────────┘            │
│             ↓                       │
│  ┌─────────────────────┐            │
│  │  Chaos Controller   │  ← reads CRDs, executes experiments
│  │  (chaos-controller  │
│  │   -manager pod)     │            │
│  └──────────┬──────────┘            │
│             ↓                       │
│  ┌─────────────────────┐            │
│  │  Chaos Daemon       │  ← runs on each node, does the actual injection
│  │  (DaemonSet)        │
│  └─────────────────────┘            │
│                                     │
│  Target pods: aois, kafka, falco    │
└─────────────────────────────────────┘
```

The controller reads your experiment spec, validates it, then instructs the daemon on the relevant node to inject the failure. When the experiment ends (either via `duration` field or `kubectl delete`), the daemon restores the original state.

---

## SLO Definition: What You Are Protecting

Before you break anything, define what "working correctly" means. Without a precise definition, chaos results are observations without conclusions. "It seemed slower" is not a metric. "P99 latency exceeded 30 seconds for 3 minutes" is.

**AOIS SLO for v19:**

```
SLO 1 — Analysis Latency
  99.5% of P1/P2 incidents must be analyzed within 30 seconds
  Measured by: aois_llm_duration_ms histogram (p99 bucket)
  Alert threshold: p99 > 30000ms for more than 60 seconds

SLO 2 — Pipeline Availability
  The Kafka consumer must process at least one message every 5 minutes
  Measured by: time since last aois_incidents_total increment
  Alert threshold: no increment for > 300 seconds

SLO 3 — Error Rate
  Less than 5% of analysis requests may return an error (non-200, exception, timeout)
  Measured by: aois_incidents_total with result="error" label
  Alert threshold: error_rate > 0.05 over 5-minute window
```

These three SLOs define the chaos experiment success criteria. An experiment is "survived" if all three stay within bounds throughout. An experiment "reveals a gap" if any SLO is violated — which means you learned something, and you have a fix to make.

### Adding Prometheus Alerting Rules

Create `k8s/prometheus-rules.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: aois-slo-alerts
  namespace: monitoring
  labels:
    app: kube-prometheus-stack
    release: prometheus
spec:
  groups:
  - name: aois.slo
    interval: 30s
    rules:
    - alert: AOISHighAnalysisLatency
      expr: |
        histogram_quantile(0.99,
          rate(aois_llm_duration_ms_bucket[5m])
        ) > 30000
      for: 1m
      labels:
        severity: critical
        component: aois
      annotations:
        summary: "AOIS P99 analysis latency exceeds 30s SLO"
        description: "P99 LLM analysis latency is {{ $value }}ms (SLO: 30000ms)"

    - alert: AOISPipelineStalled
      expr: |
        increase(aois_incidents_total[5m]) == 0
      for: 5m
      labels:
        severity: warning
        component: aois
      annotations:
        summary: "AOIS Kafka pipeline stalled — no incidents processed in 5 minutes"

    - alert: AOISHighErrorRate
      expr: |
        rate(aois_incidents_total{result="error"}[5m]) /
        rate(aois_incidents_total[5m]) > 0.05
      for: 2m
      labels:
        severity: warning
        component: aois
      annotations:
        summary: "AOIS error rate exceeds 5% SLO"
        description: "Current error rate: {{ $value | humanizePercentage }}"
```

Note: if you are running Prometheus via Docker Compose rather than the kube-prometheus-stack operator, apply alert rules via the Prometheus config file directly. The PrometheusRule CRD requires the operator. For the Hetzner single-node cluster, Prometheus is running in the OTel stack from v16 — use the Prometheus `rule_files` config instead:

```yaml
# otel/prometheus.yml — add rules section
rule_files:
  - /etc/prometheus/rules/*.yml

# then create otel/rules/aois-slo.yml with the raw Prometheus rule format:
```

```yaml
# otel/rules/aois-slo.yml
groups:
  - name: aois.slo
    interval: 30s
    rules:
      - alert: AOISHighAnalysisLatency
        expr: >
          histogram_quantile(0.99,
            rate(aois_llm_duration_ms_bucket[5m])
          ) > 30000
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "AOIS P99 analysis latency exceeds 30s SLO"

      - alert: AOISPipelineStalled
        expr: increase(aois_incidents_total[5m]) == 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "AOIS Kafka pipeline stalled"

      - alert: AOISHighErrorRate
        expr: >
          rate(aois_incidents_total{result="error"}[5m]) /
          rate(aois_incidents_total[5m]) > 0.05
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "AOIS error rate exceeds 5%"
```

---

## Installing Chaos Mesh

Chaos Mesh installs via Helm. It requires its own namespace.

```bash
# Add the Chaos Mesh Helm repo
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update
# Hang tight while we grab the latest from your chart repositories...
# ...Successfully got an update from the "chaos-mesh" chart repository

# Inspect what you're about to install
helm show values chaos-mesh/chaos-mesh | head -60
# (large values file — confirms the chart is reachable)

# Install into chaos-mesh namespace
# runtime=containerd because k3s uses containerd, not docker
sudo helm install chaos-mesh chaos-mesh/chaos-mesh \
  --namespace chaos-mesh \
  --create-namespace \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/k3s/containerd/containerd.sock \
  --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME: chaos-mesh
# LAST DEPLOYED: ...
# NAMESPACE: chaos-mesh
# STATUS: deployed
# NOTES:
#   Chaos Mesh is successfully installed...
```

Wait for all pods to reach Running:

```bash
sudo kubectl get pods -n chaos-mesh --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                                        READY   STATUS    RESTARTS
# chaos-controller-manager-xxxxxxxxxx-xxxxx   3/3     Running   0
# chaos-daemon-xxxxx                          1/1     Running   0
# chaos-dashboard-xxxxxxxxxx-xxxxx            1/1     Running   0
```

Three components:
- **chaos-controller-manager**: reads your chaos experiment CRDs and orchestrates injection
- **chaos-daemon**: the per-node DaemonSet that actually injects failures (network rules, kill signals)
- **chaos-dashboard**: web UI — you will not use this in v19, but it exists for visualization

Verify the CRDs are registered:

```bash
sudo kubectl get crd | grep chaos-mesh --kubeconfig /etc/rancher/k3s/k3s.yaml
# iochaos.chaos-mesh.org                     2026-...
# networkchaos.chaos-mesh.org                2026-...
# podchaos.chaos-mesh.org                    2026-...
# stresschaos.chaos-mesh.org                 2026-...
# timechaos.chaos-mesh.org                   2026-...
# (8+ CRDs listed)
```

### Important: The containerd Socket Path

k3s uses containerd as its container runtime, but the socket is at a k3s-specific path: `/run/k3s/containerd/containerd.sock`. The default Chaos Mesh install assumes Docker at `/var/run/docker.sock`. If you omit the `socketPath` override, chaos-daemon will fail to communicate with the runtime and experiments will appear to apply but do nothing.

**Verify this is correct:**

```bash
sudo ls -la /run/k3s/containerd/containerd.sock
# srw-rw---- 1 root root 0 ... /run/k3s/containerd/containerd.sock
# (socket file must exist — if absent, k3s is not running)
```

---

## ▶ STOP — do this now

Install Chaos Mesh and verify all three pods are Running. Then confirm the CRDs are registered:

```bash
sudo kubectl get crd | grep chaos | wc -l --kubeconfig /etc/rancher/k3s/k3s.yaml
# 8
# (or more — as long as podchaos, networkchaos, stresschaos are present)
```

If `chaos-daemon` is in CrashLoopBackOff, check its logs:

```bash
sudo kubectl logs -n chaos-mesh -l app.kubernetes.io/component=chaos-daemon --kubeconfig /etc/rancher/k3s/k3s.yaml | tail -20
# Look for: "failed to dial containerd" — means wrong socket path
# Fix: helm upgrade with correct --set chaosDaemon.socketPath=...
```

---

## The Five Experiments

The manifests in `k8s/chaos/` define five experiments targeting different layers of the AOIS stack. Run each one individually. Observe. Measure. Record findings before moving to the next.

### Before Each Experiment: Start the Background Load

Every experiment must run against a live pipeline — not a cold cluster. Start the Kafka producer before each experiment:

```bash
cd /home/collins/aois-system
python3 kafka/producer.py --rate 1 --duration 600
# Publishing 1 log/second for 10 minutes
# [00:00] Published: pod OOMKilled exit code 137 → aois-logs
# [00:01] Published: 502 Bad Gateway upstream error → aois-logs
# ...
```

Keep this running in a separate terminal throughout the experiment. The consumer (running in k8s via KEDA) will be processing these continuously.

Also open a Grafana tab to `http://localhost:3000` (or the Docker Compose port). The AOIS LLM dashboard from v16 shows real-time throughput, latency, and cost. You want this visible while chaos runs.

---

### Experiment 1: Pod Kill

**What it does:** kills one AOIS pod every cycle. Tests whether k8s reschedules it and whether the Kafka consumer reconnects without manual intervention.

**What you expect to see:** brief gap in `aois_incidents_total` (consumer offline during kill), then automatic recovery as the replacement pod starts and reconnects to Kafka.

**What would reveal a gap:** consumer not reconnecting, Kafka consumer group stuck in rebalancing, KEDA not respecting the minimum replica count.

```bash
# Apply the experiment
sudo kubectl apply -f k8s/chaos/pod-kill-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# podchaos.chaos-mesh.org/aois-pod-kill created

# Watch the AOIS pods in real time
sudo kubectl get pods -n aois -w --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                    READY   STATUS    RESTARTS   AGE
# aois-xxxxxxxxxx-xxxxx   1/1     Running   0          5m
# aois-xxxxxxxxxx-xxxxx   0/1     Terminating   0       5m    ← chaos kills it
# aois-xxxxxxxxxx-yyyyy   0/1     Pending       0       0s    ← k8s reschedules
# aois-xxxxxxxxxx-yyyyy   1/1     Running       0       8s    ← recovery complete

# Record the recovery time (Terminating → Running)
# Expected: under 30 seconds on a healthy single-node cluster
```

**Measure MTTR for pod kill:**

```bash
# In Prometheus (http://localhost:9090 or port-forwarded), run:
# time since last aois_incidents_total increment:
# absent_over_time(aois_incidents_total[1m]) * time()
# This gives you the timestamps of any processing gaps > 1 minute
```

Clean up:

```bash
sudo kubectl delete -f k8s/chaos/pod-kill-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# podchaos.chaos-mesh.org "aois-pod-kill" deleted
```

---

### Experiment 2: Network Latency

**What it does:** injects 500ms latency (±100ms jitter) on all traffic leaving AOIS pods for 5 minutes. This affects: outbound calls to the Claude/Groq API, Kafka produce calls (publishing to `aois-results`), Redis calls.

**What you expect to see:** `aois_llm_duration_ms` p99 rises significantly (baseline ~2s → spikes to ~2.5s+). The SLO of 30s analysis time is not threatened — 500ms is noticeable but manageable if there are no retries amplifying the delay.

**What would reveal a gap:** LLM client timeout set shorter than 500ms (causing errors instead of slow responses), missing retry logic causing permanent failures, SLO breach when 500ms × N hops exceeds 30s.

```bash
sudo kubectl apply -f k8s/chaos/network-delay-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# networkchaos.chaos-mesh.org/aois-network-delay created
```

Verify the delay is real from outside:

```bash
# Exec into the AOIS pod and measure
AOIS_POD=$(sudo kubectl get pod -n aois -l app=aois -o jsonpath='{.items[0].metadata.name}' --kubeconfig /etc/rancher/k3s/k3s.yaml)

sudo kubectl exec -n aois $AOIS_POD --kubeconfig /etc/rancher/k3s/k3s.yaml -- \
  curl -o /dev/null -s -w "time_total: %{time_total}\n" https://api.anthropic.com/v1/messages \
  -X POST -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5-20251001","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}'
# time_total: 2.854
# (baseline without chaos is ~1.8s — the extra ~500ms is the injected delay)
```

Watch the Grafana panel `aois_llm_duration_ms` rise during this window. The 5-minute `duration` field in the manifest auto-stops the experiment. Or delete it manually:

```bash
sudo kubectl delete -f k8s/chaos/network-delay-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# networkchaos.chaos-mesh.org "aois-network-delay" deleted
```

---

### Experiment 3: Kafka Pod Kill

**What it does:** kills the Kafka broker pod. The Strimzi operator manages Kafka via a StatefulSet, so it will reschedule the broker. During the gap, the AOIS consumer cannot receive new logs.

**What you expect to see:** consumer loses connection, logs "connection refused" or "broker unavailable", Strimzi brings the broker back up (1–2 minutes on a single-node cluster), consumer reconnects and resumes.

**What would reveal a gap:** AOIS consumer crashing permanently instead of reconnecting, Kafka producer on the application side dropping messages without buffering, KEDA ScaledObject reporting errors because it cannot query consumer lag.

```bash
sudo kubectl apply -f k8s/chaos/pod-kill-kafka.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# podchaos.chaos-mesh.org/kafka-pod-kill created

# Watch the Kafka pod restart
sudo kubectl get pods -n kafka -w --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                         READY   STATUS
# aois-kafka-dual-role-0       1/1     Running
# aois-kafka-dual-role-0       0/1     Terminating  ← chaos kills it
# aois-kafka-dual-role-0       0/1     Pending
# aois-kafka-dual-role-0       0/1     ContainerCreating
# aois-kafka-dual-role-0       1/1     Running      ← Strimzi recovers it

# Check AOIS consumer logs during the outage
sudo kubectl logs -n aois $AOIS_POD --follow --kubeconfig /etc/rancher/k3s/k3s.yaml | grep -E "error|kafka|reconnect"
# ERROR: NoBrokersAvailable: [Errno 111] Connection refused
# INFO:  Attempting reconnect to Kafka in 5s...
# INFO:  Kafka consumer connected — resuming processing
```

Measure the full outage window: time from broker kill to "Kafka consumer connected" log.

```bash
sudo kubectl delete -f k8s/chaos/pod-kill-kafka.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
```

---

### Experiment 4: Packet Loss

**What it does:** drops 30% of all packets entering AOIS pods for 5 minutes. Unlike latency injection, packet loss causes TCP retransmits — the connection stays up but throughput degrades unpredictably. LLM API calls that depend on streaming responses are particularly sensitive to this.

**What you expect to see:** some requests succeed (70% of packets get through), latency increases due to retransmits, error rate may tick up slightly. The Claude client and Groq client should retry on transient failures.

**What would reveal a gap:** error rate exceeding the 5% SLO, no retry logic on transient failures, streaming responses that do not handle mid-stream packet loss.

```bash
sudo kubectl apply -f k8s/chaos/packet-loss-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# networkchaos.chaos-mesh.org/aois-packet-loss created
```

Query the error rate in Prometheus during the 5 minute window:

```
rate(aois_incidents_total{result="error"}[2m]) /
rate(aois_incidents_total[2m])
```

A healthy result: this stays below 0.05 (5%) even under 30% packet loss, because the HTTP client retries transparently. If you see it spike above 0.05, your LLM client timeout is too short — requests fail instead of retrying.

```bash
sudo kubectl delete -f k8s/chaos/packet-loss-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
```

---

### Experiment 5: CPU Stress

**What it does:** spawns 2 stress workers consuming 80% CPU on one AOIS pod for 5 minutes. Tests whether: (a) KEDA scales out to distribute load, (b) latency degrades gracefully under CPU throttling, (c) the pod hits its CPU limit of 1000m and gets throttled by the kernel.

**What you expect to see:** the stressed pod's CPU approaches its limit, cgroup CPU throttling kicks in, response times on that pod rise. If KEDA is watching CPU utilisation (it was watching Kafka lag from v17/v18 — confirm your current trigger), it may scale out a second pod.

**What would reveal a gap:** KEDA not scaling out (if CPU trigger is configured), analysis latency breaching the 30s SLO due to CPU starvation, pod getting OOMKilled (memory, not CPU — indicates the stress config is misconfigured).

```bash
sudo kubectl apply -f k8s/chaos/cpu-stress-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# stresschaos.chaos-mesh.org/aois-cpu-stress created

# Watch CPU in real time
sudo kubectl top pods -n aois --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                    CPU(cores)   MEMORY(bytes)
# aois-xxxxxxxxxx-xxxxx   847m         312Mi
# (approaching 1000m limit — getting throttled)

# Check if KEDA scaled out a second pod
sudo kubectl get pods -n aois --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                    READY   STATUS    RESTARTS
# aois-xxxxxxxxxx-xxxxx   1/1     Running   0
# aois-xxxxxxxxxx-yyyyy   1/1     Running   0  ← KEDA scaled out
```

```bash
sudo kubectl delete -f k8s/chaos/cpu-stress-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
```

---

## ▶ STOP — do this now

Run experiments 1 and 5 back to back (with a 2-minute break in between). For each:
1. Record: time to inject (seconds after apply), time to detect in Grafana, time to recover
2. Check whether any SLO was violated
3. Note the pod count before and after

Fill in this table before proceeding:

```
Experiment 1 (Pod Kill):
  Recovery time: ___s
  SLO 1 (latency) violated: yes / no
  SLO 2 (pipeline availability) violated: yes / no
  Notes:

Experiment 5 (CPU Stress):
  Peak CPU observed: ___m
  KEDA scaled out: yes / no
  SLO 1 violated: yes / no
  Notes:
```

---

## Running the Game Day

A game day is a structured, time-boxed session in which you deliberately apply chaos to the system and measure how it performs. It differs from running individual experiments in that you combine experiments, run them consecutively, and produce a written report.

### Game Day Runbook

**Duration:** 60 minutes  
**Participants:** you (operator + observer)  
**Goal:** apply all five chaos experiments in sequence, measure MTTR for each, identify any SLO violations, and produce a written incident report

**Setup (T-10 minutes before start):**

```bash
# 1. Start the background load generator
python3 kafka/producer.py --rate 2 --duration 4800 &
PRODUCER_PID=$!

# 2. Open three terminals:
#    Terminal A: kubectl get pods -n aois -w (watch pod lifecycle)
#    Terminal B: kubectl logs -n aois <pod> -f (watch consumer logs)
#    Terminal C: experiment apply/delete commands

# 3. Open Grafana to the AOIS LLM dashboard
#    Note baseline metrics before starting:
echo "Baseline check at $(date)"
sudo kubectl exec -n aois $AOIS_POD --kubeconfig /etc/rancher/k3s/k3s.yaml -- \
  curl -s http://localhost:8000/health
# {"status": "healthy"}
```

**T+00:00 — Experiment 1: Pod Kill**

```bash
date && sudo kubectl apply -f k8s/chaos/pod-kill-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# Record: experiment start time
# Watch: pod lifecycle in terminal A
# Measure: time from Terminating to Running
# Expected recovery: < 30s
```

**T+05:00 — Clean up Experiment 1, brief observation period**

```bash
sudo kubectl delete -f k8s/chaos/pod-kill-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# Wait 3 minutes, confirm pipeline throughput returned to baseline
```

**T+08:00 — Experiment 2: Network Latency**

```bash
date && sudo kubectl apply -f k8s/chaos/network-delay-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# Experiment auto-stops after 5 minutes (duration: "5m" in manifest)
# Record: p99 latency peak from Grafana
# Record: any error rate change
```

**T+15:00 — Observation period + Experiment 3: Kafka Kill**

```bash
date && sudo kubectl apply -f k8s/chaos/pod-kill-kafka.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# Watch: kafka pod lifecycle, AOIS consumer reconnect log
# Measure: time from broker kill to "Kafka consumer connected"
# Expected: < 2 minutes (Strimzi + consumer reconnect)
```

**T+20:00 — Clean up Experiment 3**

```bash
sudo kubectl delete -f k8s/chaos/pod-kill-kafka.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
```

**T+25:00 — Experiment 4: Packet Loss**

```bash
date && sudo kubectl apply -f k8s/chaos/packet-loss-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# Auto-stops after 5 minutes
# Record: error rate (should stay under 5% SLO)
# Record: p99 latency change (should be modest — TCP retransmit adds latency, not failure)
```

**T+35:00 — Experiment 5: CPU Stress**

```bash
date && sudo kubectl apply -f k8s/chaos/cpu-stress-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# Auto-stops after 5 minutes
# Record: peak CPU (kubectl top pods -n aois)
# Record: whether KEDA scaled out
# Record: p99 latency change under CPU pressure
```

**T+42:00 — Composite test: Latency + CPU simultaneously**

This is the adversarial condition. Real outages rarely have one cause.

```bash
date
sudo kubectl apply -f k8s/chaos/network-delay-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
sudo kubectl apply -f k8s/chaos/cpu-stress-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
# Both run for 5 minutes
# Record: is the combined effect additive? Does p99 > 30s?
# Record: error rate under combined failure
```

**T+50:00 — Clean up all, recovery observation**

```bash
sudo kubectl delete -f k8s/chaos/network-delay-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml
sudo kubectl delete -f k8s/chaos/cpu-stress-aois.yaml --kubeconfig /etc/rancher/k3s/k3s.yaml

# Wait 5 minutes, confirm full recovery:
#   - aois_incidents_total incrementing at pre-chaos rate
#   - p99 latency back to baseline
#   - no pods in Terminating or Error state
# Kill the load generator
kill $PRODUCER_PID
```

**T+60:00 — Game day complete. Write the incident report.**

---

## Game Day Incident Report Template

After every game day, write a brief report. This is the artifact that distinguishes SRE discipline from "ran some tests."

```markdown
# AOIS Chaos Game Day — [DATE]

## Experiments Run
1. Pod Kill (aois) — T+00:00 to T+08:00
2. Network Latency 500ms — T+08:00 to T+15:00
3. Kafka Broker Kill — T+15:00 to T+20:00
4. 30% Packet Loss — T+25:00 to T+33:00
5. CPU Stress 80% — T+35:00 to T+43:00
6. Composite: Latency + CPU — T+42:00 to T+50:00

## Findings

| Experiment | MTTR | SLO 1 (latency) | SLO 2 (pipeline) | SLO 3 (errors) |
|---|---|---|---|---|
| Pod Kill | ___s | PASS/FAIL | PASS/FAIL | PASS/FAIL |
| Network Latency | N/A (no outage) | PASS/FAIL | PASS | PASS/FAIL |
| Kafka Kill | ___s | N/A | PASS/FAIL | PASS |
| Packet Loss | N/A | PASS/FAIL | PASS | PASS/FAIL |
| CPU Stress | N/A | PASS/FAIL | PASS | PASS |
| Composite | ___s | PASS/FAIL | PASS | PASS/FAIL |

## Action Items

- [ ] [If pod kill MTTR > 30s]: investigate k8s scheduling time, reduce readiness probe delay
- [ ] [If packet loss error rate > 5%]: add retry with exponential backoff to LLM client
- [ ] [If Kafka kill MTTR > 120s]: tune Strimzi operator reconciliation interval
- [ ] [If composite fails latency SLO]: reduce LLM request timeout on non-P1 tiers

## What AOIS Detected

Did AOIS detect the chaos it was subjected to?
- Falco: did it fire any alerts on the chaos-daemon's pod manipulation?
- Kafka consumer: did it log the outage with sufficient detail for diagnosis?
- Prometheus: did the SLO alerts fire within 1 minute of each experiment starting?
```

---

## ▶ STOP — do this now

Run the full game day. It takes approximately 60 minutes. Then fill in the incident report template above. This is not optional. The game day *is* v19 — everything before was setup.

Save your completed report to `docs/gameday-v19.md` in the repo.

---

## MTTR: Measuring Recovery Time Correctly

MTTR is meaningless without a precise start and end:

- **Start**: the moment the failure is injected (experiment apply timestamp)
- **End**: the moment the system returns to full function (not just "pod is Running" but "SLO metrics are back within bounds")

"Pod is Running" is a lagging indicator. The pod might be up but the Kafka consumer not yet connected, or the LLM client still waiting for a timeout to clear. Use the metrics, not the pod status:

```bash
# Prometheus query: time of last aois_incidents_total increment (pipeline liveness)
# In Prometheus UI at http://localhost:9090:

# Query 1: see when incidents were last processed
increase(aois_incidents_total[30s])
# When this goes to 0, the pipeline stalled
# When it returns non-zero, recovery is complete

# Query 2: p99 latency recovery
histogram_quantile(0.99, rate(aois_llm_duration_ms_bucket[1m]))
# When this returns to baseline, latency SLO is restored
```

For the pod kill experiment specifically, you can calculate MTTR precisely from k8s events:

```bash
sudo kubectl get events -n aois --sort-by='.lastTimestamp' --kubeconfig /etc/rancher/k3s/k3s.yaml | tail -20
# LAST SEEN   TYPE      REASON      OBJECT                    MESSAGE
# 2m          Normal    Killing     pod/aois-xxxxxx-xxxxx     Stopping container aois
# 2m          Normal    Scheduled   pod/aois-xxxxxx-yyyyy     Successfully assigned
# 1m50s       Normal    Pulled      pod/aois-xxxxxx-yyyyy     Container image already present
# 1m49s       Normal    Started     pod/aois-xxxxxx-yyyyy     Started container aois
# 1m45s       Normal    Readiness   pod/aois-xxxxxx-yyyyy     Readiness probe passed
```

The MTTR for a pod kill is from `Killing` timestamp to `Readiness probe passed` timestamp.

---

## What AOIS Detects About Its Own Chaos

An interesting question: does AOIS detect the chaos it is subjected to?

**Falco** is watching kernel syscalls. When the chaos-daemon kills a pod, it sends SIGKILL. Falco's rules watch for unexpected process termination — depending on your rule configuration, this may or may not fire. Check:

```bash
sudo kubectl logs -n falco -l app.kubernetes.io/name=falco --kubeconfig /etc/rancher/k3s/k3s.yaml | grep -i "chaos\|kill\|terminated"
# If Falco fires on chaos-daemon activity, the alert goes through:
# Falco → Sidekick → aois-security Kafka topic → AOIS consumer → Claude analysis
```

**The Kafka consumer** in `kafka/consumer.py` logs broker reconnects and gaps. During the Kafka kill experiment, these logs are the primary signal that the pipeline is down — AOIS is effectively observing its own pipeline degradation.

**Prometheus alerts** from the SLO rules defined earlier will fire during sustained failures. If you have the Alertmanager configured, these reach a webhook or notification channel. If not, they appear in the Prometheus `/alerts` page.

This is the recursive proof that AOIS works: a system that can observe and report on its own failures has genuine reliability value. A system that only reports on other systems' failures, and goes dark when it fails itself, is not production-grade.

---

## Common Mistakes

### 1. Wrong containerd socket path on k3s

**Symptom:** Chaos Mesh installs successfully but experiments apply and nothing happens. No failures injected.

```bash
sudo kubectl logs -n chaos-mesh -l app.kubernetes.io/component=chaos-daemon --kubeconfig /etc/rancher/k3s/k3s.yaml | grep -i "socket\|containerd\|error"
# Error: failed to dial containerd: context deadline exceeded
# connect /var/run/containerd/containerd.sock: no such file or directory
```

**Fix:**

```bash
sudo helm upgrade chaos-mesh chaos-mesh/chaos-mesh \
  --namespace chaos-mesh \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/k3s/containerd/containerd.sock \
  --kubeconfig /etc/rancher/k3s/k3s.yaml
```

---

### 2. Chaos experiment applies but targets wrong pods

**Symptom:** `kubectl apply` succeeds, no failures visible.

**Diagnosis:**

```bash
sudo kubectl describe podchaos aois-pod-kill -n chaos-mesh --kubeconfig /etc/rancher/k3s/k3s.yaml | grep -A5 "Status\|Message\|Selected"
# Selected Pods: 0  ← the selector matched nothing
```

**Fix:** verify the label on your AOIS pods matches the `labelSelectors` in the manifest:

```bash
sudo kubectl get pods -n aois --show-labels --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                    LABELS
# aois-xxxxxxxxxx-xxxxx   app=aois,...
# (confirm app=aois is present)
```

If AOIS pods have `app.kubernetes.io/name=aois` instead of `app=aois`, update the labelSelector in the manifest accordingly.

---

### 3. Running experiments without background load

**Symptom:** all SLOs show PASS trivially because there are no requests being processed, so no SLO metrics are being emitted.

**Fix:** always confirm the producer is running before applying any experiment:

```bash
sudo kubectl get kafkatopicpartition -n kafka --kubeconfig /etc/rancher/k3s/k3s.yaml | grep aois-logs
# If offset is incrementing, messages are flowing
# OR check consumer logs for "Published" lines from the producer
```

---

### 4. Forgetting to delete experiments

**Symptom:** next experiment shows odd results because a previous experiment is still running.

**Fix:** always explicitly delete before moving to the next experiment, and confirm:

```bash
sudo kubectl get podchaos,networkchaos,stresschaos -n chaos-mesh --kubeconfig /etc/rancher/k3s/k3s.yaml
# No resources found in chaos-mesh namespace.
# (clean state before next experiment)
```

---

### 5. MTTR measured from "pod Running" instead of "SLO restored"

**Symptom:** your recorded MTTR of 15 seconds is technically true for pod restart time, but the consumer did not reconnect to Kafka for another 45 seconds. You report a misleading number.

**Fix:** MTTR ends when the first incident processes successfully after the failure, not when the pod shows Running. Use `increase(aois_incidents_total[30s]) > 0` as the recovery signal.

---

## Troubleshooting

### Chaos Mesh webhook errors on experiment apply

```
Error from server: error when creating "k8s/chaos/pod-kill-aois.yaml":
admission webhook "mpodchaos.kb.io" denied the request: ...
```

The admission webhook (chaos-controller-manager) is not reachable. This usually means the controller pods are not yet Ready, or the webhook TLS certificate has not been issued.

```bash
sudo kubectl get pods -n chaos-mesh --kubeconfig /etc/rancher/k3s/k3s.yaml
# If chaos-controller-manager is not 3/3 Ready, wait
sudo kubectl describe pod -n chaos-mesh -l app.kubernetes.io/component=controller-manager --kubeconfig /etc/rancher/k3s/k3s.yaml | grep -A5 "Events"
```

---

### NetworkChaos applies but no latency observed

```bash
# Verify tc rules are present on the node:
sudo ip netns list
# chaos experiments use network namespaces — you can inspect them:
sudo tc qdisc show
# Look for netem rules that weren't there before
```

If tc rules are absent, the chaos-daemon could not apply them — usually the containerd socket issue again.

---

### Kafka consumer does not reconnect after broker kill

```bash
sudo kubectl logs -n aois $AOIS_POD --kubeconfig /etc/rancher/k3s/k3s.yaml | tail -30
# Look for:
# kafka.errors.NoBrokersAvailable: ...
# If the consumer is stuck in error state rather than retrying, check:
# kafka/consumer.py — the reconnect loop in the exception handler
```

If the consumer process exited (rather than retrying), k8s will restart the pod (restartPolicy: Always). MTTR in this case includes pod restart time.

---

### StressChaos pod shows Running but no CPU pressure

```bash
sudo kubectl top pods -n aois --kubeconfig /etc/rancher/k3s/k3s.yaml
# If CPU shows < 200m under a "cpu stress 80%" experiment:
sudo kubectl describe stresschaos aois-cpu-stress -n chaos-mesh --kubeconfig /etc/rancher/k3s/k3s.yaml
# Look for events or conditions explaining why workers did not start
```

The stress workers run inside the target container's cgroup. If the container's resource limits are very low (`cpu: 100m`), the stress workers are immediately throttled and appear ineffective. In values.prod.yaml AOIS has a 1000m CPU limit — there is headroom for stress workers.

---

## Connection to Later Phases

### To Phase 7 (v20+): Autonomous Agents Under Chaos

When AOIS gets tools in v20 (`get_pod_logs`, `describe_node`, `list_events`), chaos experiments become more interesting: the agent should autonomously investigate the chaos it observes, propose remediations, and present them for human approval — without you in the loop.

The SLOs defined in v19 become the agent's acceptance criteria: an investigation is not complete until it has diagnosed the root cause and the pipeline returns to within SLO bounds.

The MTTR methodology you built here is the metric that proves whether autonomous remediation is better than human response. You will measure it again in v23 (LangGraph agent) and v25 (E2B sandboxed remediation).

### To v23.5 (Agent Evaluation)

The game day incident report template you wrote here is the precursor to the agent evaluation framework in v23.5. The same structure — golden input, expected action, measured outcome, SLO pass/fail — applies to evaluating agent decisions. Chaos engineering teaches you to define "correct system behaviour under stress" before you automate the response to it.

### To v34.5 (AI SRE Capstone)

The capstone game day is chaos engineering at scale: coordinated failures across model API, Kafka, agent loops, and security alerts simultaneously. The methodology you practiced in v19 — structured runbook, MTTR measurement, incident report — is the same discipline applied to the full system. The difference is that in v34.5, AOIS itself handles the chaos response, and you evaluate whether it met its SLOs.

---

## Mastery Checkpoint

Complete all nine before marking v19 done.

1. Install Chaos Mesh on your k3s cluster using the correct containerd socket path. Verify all three pods (controller, daemon, dashboard) are Running and that `kubectl get crd | grep chaos | wc -l` returns 8 or more.

2. Define the three AOIS SLOs in precise, measurable terms. For each: state the metric name, the threshold, and the Prometheus expression that evaluates it. Do not state them as "fast" or "available" — state them as numbers.

3. Run Experiment 1 (pod kill). Record the MTTR from Terminating to SLO-restored (not just pod-Running). Is it under 30 seconds?

4. Run Experiment 3 (Kafka kill). The Strimzi operator restores the broker. The AOIS consumer reconnects. How long does the full pipeline recovery take? What is the maximum acceptable recovery time before the pipeline SLO is violated?

5. Run the composite experiment (latency + CPU simultaneously). Does the combined failure violate the p99 latency SLO? If yes, identify the specific failure mode (timeout too short, no retry, CPU throttle amplifying latency).

6. Explain, in plain English to a non-technical person, what chaos engineering is and why a system that works fine in testing might still fail in production.

7. Explain, to a junior engineer, the difference between "MTTR measured from pod Running" and "MTTR measured from SLO-restored". Why does the distinction matter in production SRE?

8. Explain, to a senior engineer: why does Chaos Mesh inject network failures at the kernel (tc/netem) level rather than at the application level? What class of failures does this catch that application-level mocking misses?

9. Complete the full game day runbook. Write and commit your incident report to `docs/gameday-v19.md`. The report must include the experiment timeline, MTTR for each failure, SLO pass/fail for each, and at least one action item from a SLO violation (or document explicitly that all SLOs passed and explain why you trust that result).

**The mastery bar:** you can stand in front of a team, run a live chaos experiment on the AOIS cluster, narrate what is happening in the metrics in real time, and write the incident report from the results — without referring to these notes. Chaos engineering is a practice, not a concept.

---

## 4-Layer Tool Understanding

### Chaos Mesh

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Production systems break in ways staging never predicts. Chaos Mesh lets you break things deliberately, during business hours, so you find the failure modes before your users do. |
| **System Role** | Where does it sit in AOIS? | Chaos Mesh runs as a set of controllers and a DaemonSet in the `chaos-mesh` namespace. It reaches into the `aois` and `kafka` namespaces to kill pods, inject network rules, and drive CPU stress — entirely from Kubernetes-native YAML manifests. |
| **Technical** | What is it, precisely? | A cloud-native chaos engineering platform that implements failure injection as Kubernetes CRDs. It uses Linux `tc/netem` for network failures, cgroup manipulation for CPU/memory stress, and SIGKILL for pod termination. The chaos-daemon on each node performs the actual injection; the controller translates CRD specs into daemon instructions. |
| **Remove it** | What breaks, and how fast? | Remove Chaos Mesh → chaos experiments stop applying (CRDs and controllers gone). The system itself is not affected — Chaos Mesh only injects failure when experiments are active. What you lose is the ability to validate system resilience before real failures expose it. Without regular chaos testing, resilience assumptions accumulate silently and fail in production. |

---

### SLOs (Service Level Objectives)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | "The system is working" is not actionable. An SLO is a precise, measurable statement of what "working" means — 99.5% of P1 incidents analyzed in under 30 seconds. With an SLO, you know exactly when the system is degraded and by how much. |
| **System Role** | Where does it sit in AOIS? | SLOs are defined as Prometheus alert rules and Grafana panels. They observe the metrics emitted by AOIS (OTel instrumentation from v16) and fire alerts when thresholds are crossed. They are not inside the application — they are a measurement layer around it. |
| **Technical** | What is it, precisely? | A Service Level Objective is a target value for a Service Level Indicator (SLI). An SLI is a metric: p99 latency, error rate, availability. The SLO is the threshold: p99 < 30s, error rate < 5%. Prometheus alert rules enforce SLOs continuously against real traffic. An SLA (Service Level Agreement) is what you commit to externally, usually weaker than the internal SLO. |
| **Remove it** | What breaks, and how fast? | Remove SLO definitions → chaos experiments have no objective criteria for pass/fail. You are left with subjective judgements ("seemed okay"). Gradual degradation goes undetected because there is no baseline to compare against. In production, this means latency creep and silent error rate increases ship unremarked until a user complains. |

---

### MTTR (Mean Time to Recovery)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | After something breaks, how quickly does it fix itself? MTTR answers that question with a number. Lower is better. Knowing your MTTR tells you whether your automation is faster than a human, and whether it is fast enough to stay within SLO. |
| **System Role** | Where does it sit in AOIS? | MTTR is calculated from Prometheus metrics. The failure start is the experiment apply timestamp. Recovery end is when `aois_incidents_total` resumes incrementing (pipeline liveness) and p99 latency returns to baseline. MTTR = recovery_time - failure_start. |
| **Technical** | What is it, precisely? | The arithmetic mean of recovery durations across incidents. MTTR = sum(recovery_durations) / count(incidents). It measures the detection-to-resolution window. In the chaos context, since detection is instantaneous (you applied the experiment), MTTR equals the time-to-recovery only. In production, MTTR includes detection time, which can add minutes if alerts are not configured. |
| **Remove it** | What breaks, and how fast? | Without MTTR measurement, you cannot compare "AOIS automated remediation" against "human on-call response". You cannot prove improvement over time. The system may be recovering in 3 minutes or 30 minutes — without measurement, you do not know. In v23 (LangGraph autonomous agent), MTTR is the primary metric proving the agent adds value. |
