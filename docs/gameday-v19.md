# AOIS Chaos Game Day — v19

**Date:** [fill in when you run it]  
**Operator:** Collins  
**Duration:** 60 minutes  
**Cluster:** Hetzner 46.225.235.51 (k3s, 8 vCPU / 16GB RAM)

---

## Experiments Run

| # | Experiment | Start | End | Duration |
|---|---|---|---|---|
| 1 | Pod Kill (AOIS) | T+00:00 | T+08:00 | 8 min |
| 2 | Network Latency 500ms | T+08:00 | T+15:00 | 5 min (auto) |
| 3 | Kafka Broker Kill | T+15:00 | T+20:00 | 5 min |
| 4 | 30% Packet Loss | T+25:00 | T+33:00 | 5 min (auto) |
| 5 | CPU Stress 80% | T+35:00 | T+43:00 | 5 min (auto) |
| 6 | Composite: Latency + CPU | T+42:00 | T+50:00 | 5 min (auto) |

---

## Baseline Metrics (Pre-Chaos)

Record these before any experiment starts:

- `aois_incidents_total` rate (per minute): ___
- `aois_llm_duration_ms` p99 (ms): ___
- `aois_incidents_total{result="error"}` rate: ___
- AOIS pod count: ___
- Kafka consumer lag (aois-logs): ___

---

## Results

### Experiment 1: Pod Kill (AOIS)

| Metric | Value |
|---|---|
| Time to Terminating (seconds after apply) | ___ |
| Time to Running (new pod) | ___ |
| Time to Readiness probe passed | ___ |
| Time to SLO restored (incidents resuming) | ___ |
| **MTTR (failure to SLO-restored)** | **___s** |
| SLO 1 — Analysis Latency (< 30s p99) | PASS / FAIL |
| SLO 2 — Pipeline Availability | PASS / FAIL |
| SLO 3 — Error Rate (< 5%) | PASS / FAIL |

Notes:

---

### Experiment 2: Network Latency 500ms

| Metric | Value |
|---|---|
| Peak p99 latency during experiment (ms) | ___ |
| Baseline p99 latency (ms) | ___ |
| Error rate during experiment (%) | ___ |
| SLO 1 — Analysis Latency | PASS / FAIL |
| SLO 3 — Error Rate | PASS / FAIL |

Notes:

---

### Experiment 3: Kafka Broker Kill

| Metric | Value |
|---|---|
| Time broker pod Terminating | ___ |
| Time Strimzi restored broker (Running) | ___ |
| Time AOIS consumer reconnected | ___ |
| **MTTR (broker kill to pipeline restored)** | **___s** |
| SLO 2 — Pipeline Availability | PASS / FAIL |

Notes:

---

### Experiment 4: Packet Loss 30%

| Metric | Value |
|---|---|
| Error rate during experiment (%) | ___ |
| p99 latency change (ms) | ___ |
| SLO 1 — Analysis Latency | PASS / FAIL |
| SLO 3 — Error Rate | PASS / FAIL |

Notes:

---

### Experiment 5: CPU Stress 80%

| Metric | Value |
|---|---|
| Peak CPU observed (millicores) | ___ |
| KEDA scaled out? (yes/no) | ___ |
| p99 latency under CPU pressure (ms) | ___ |
| SLO 1 — Analysis Latency | PASS / FAIL |

Notes:

---

### Experiment 6: Composite (Latency + CPU)

| Metric | Value |
|---|---|
| Peak p99 latency (ms) | ___ |
| Error rate (%) | ___ |
| SLO 1 — Analysis Latency | PASS / FAIL |
| SLO 3 — Error Rate | PASS / FAIL |

Notes:

---

## Summary Table

| Experiment | MTTR | SLO 1 (latency) | SLO 2 (pipeline) | SLO 3 (errors) |
|---|---|---|---|---|
| Pod Kill | ___s | PASS/FAIL | PASS/FAIL | PASS/FAIL |
| Network Latency | N/A | PASS/FAIL | PASS | PASS/FAIL |
| Kafka Kill | ___s | N/A | PASS/FAIL | PASS |
| Packet Loss | N/A | PASS/FAIL | PASS | PASS/FAIL |
| CPU Stress | N/A | PASS/FAIL | PASS | PASS |
| Composite | N/A | PASS/FAIL | PASS | PASS/FAIL |

---

## Did AOIS Detect Its Own Chaos?

- Falco fired on chaos-daemon activity: yes / no
- Security alerts reached `aois-security` Kafka topic: yes / no
- AOIS analyzed the Falco alerts: yes / no
- Prometheus SLO alerts fired within 1 minute of each experiment: yes / no

---

## Action Items

| # | Finding | Fix | Priority |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |

---

## Conclusion

[Write 2–3 sentences: overall verdict on AOIS resilience, most important finding, what changes before Phase 7.]
