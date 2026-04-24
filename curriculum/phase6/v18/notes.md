# v18 — eBPF, Falco, and Runtime Security

⏱ **Estimated time: 5–7 hours**

---

## Prerequisites

k3s running on Hetzner with Strimzi Kafka and KEDA from v17.

```bash
sudo kubectl get nodes --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                STATUS   ROLES           AGE   VERSION
# aois   Ready    control-plane   ...   v1.34.6+k3s1

sudo kubectl get kafkatopic -n kafka --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME            CLUSTER      PARTITIONS   READY
# aois-logs       aois-kafka   3            True
# aois-results    aois-kafka   3            True
# aois-security   aois-kafka   3            True

sudo kubectl get pods -n falco --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                                   READY   STATUS    RESTARTS
# falco-xxxxx                            2/2     Running   0
# falco-falcosidekick-xxxxxxxxx-xxxxx    1/1     Running   0
# falco-falcosidekick-xxxxxxxxx-xxxxx    1/1     Running   0
```

---

## Learning Goals

By the end you will be able to:

- Explain what eBPF is, why it exists, and what makes it different from traditional kernel modules
- Deploy Falco on k3s using the modern eBPF probe (no kernel headers required)
- Write custom Falco rules targeting specific containers and behaviours
- Explain what Cilium is, what kube-proxy is, and what replacing one with the other means
- Wire Falco alerts into the AOIS Kafka pipeline so security events get AI analysis
- Explain why `minimumpriority=warning` matters and what happens to Notice/Info events
- Read a Falco alert JSON and extract the fields that matter for incident response

---

## The Problem This Solves

AOIS in v17 ingests SRE logs from applications. Those logs are intentional — a service publishes what it thinks is worth reporting. That is a blind spot.

What about what services are *doing* at the kernel level — what processes they spawn, what files they write, what network connections they make — regardless of whether they log it?

That is runtime security. And the gap between "what an application says it's doing" and "what it's actually doing at the kernel level" is exactly where intrusions, prompt injection, and misconfigured containers hide.

---

## eBPF: The Technology Underneath

### What eBPF Is

eBPF stands for extended Berkeley Packet Filter. The name is misleading — it started as a packet filter but became something much larger: **a way to run safe, sandboxed programs inside the Linux kernel without modifying kernel source or loading kernel modules**.

Before eBPF, if you wanted to observe what the kernel was doing — every `open()`, every `execve()`, every TCP connection — you had two bad options:
1. **Kernel module**: write C code that runs in kernel space, where a bug crashes the machine
2. **Audit logging**: coarse, high-overhead, not real-time, burns CPU

eBPF gives you a third option: attach small verified programs to kernel hooks (syscalls, network events, function calls) that run when the kernel does something. The kernel verifier checks the program before loading it — no infinite loops, no memory corruption. If it passes, it runs in kernel space with near-zero overhead.

### What This Means in Practice

Every time a process calls `execve()` (spawning a new process), eBPF can intercept it. Every time a process opens a file, every TCP connection — observable, in real time, at the kernel level. No application cooperation required. The container doesn't know it's being watched.

This is why eBPF is called the "superpower of observability." Falco, Cilium, Tetragon, Pixie — they all run on top of eBPF.

### eBPF vs Kernel Modules

| | Kernel Module | eBPF |
|---|---|---|
| Safety | Bug = kernel panic | Verifier rejects unsafe programs |
| Distribution | Requires kernel headers, dkms | Loads at runtime |
| Stability | Breaks on kernel updates | Kernel ABI stable for eBPF programs |
| Use cases | Full kernel access | Observability, networking, security |

For Falco specifically, the modern eBPF probe (kernel 5.8+) uses BTF (BPF Type Format) — the kernel ships with its own type information, so no kernel headers needed on the node. Ubuntu 24.04 with kernel 6.8 satisfies this.

---

## Falco: Runtime Security for Kubernetes

Falco is a CNCF project that uses eBPF to watch kernel syscalls and apply rules to them. When a rule matches, Falco fires an alert.

The mental model: Falco is to containers what an IDS is to network traffic. It watches the behaviour, not the content.

### What Falco Can Detect

- A shell spawned inside a container (`bash`, `sh`, `zsh`) — almost never legitimate in production
- A file written in `/etc` — configuration tampering
- An unexpected outbound network connection — data exfiltration or C2 beaconing
- A privilege escalation attempt (`sudo`, `su`)
- A package manager running at runtime (`apt-get`, `pip`) — attacker installing tools
- A process reading `/etc/shadow` or `/proc/1/mem` — credential dumping

These are behaviours that no amount of application-level logging catches, because the attacker is operating below the application layer.

### The OWASP LLM Connection

AOIS accepts untrusted log data. If an attacker embeds instructions in a log line (prompt injection), and that injection somehow caused AOIS to execute a command — Falco would catch it. Not from the application logs (which the attacker controls), but from the kernel's view of what processes actually spawned.

v5 added an output blocklist (reactive — blocks bad output). Falco adds a detection layer (observational — catches bad behaviour). These are different layers of the same defence.

---

## Falco Architecture

```
Kernel layer
  └─ eBPF probe intercepts syscalls
       └─ Falco engine evaluates rules against events
            └─ Falco fires alerts (stdout + gRPC + webhook)
                 └─ Falco Sidekick receives alerts and fans them out
                      └─ Kafka, Slack, PagerDuty, Elasticsearch, ...
```

Falco has two components:
1. **falco** — the engine (DaemonSet, one pod per node), loads the eBPF probe, evaluates rules
2. **falcosidekick** — the fanout layer (Deployment), receives alerts from falco via HTTP and forwards to configured outputs

Sidekick is what makes Falco pluggable. Without it, Falco only writes to stdout. With it, one alert goes to as many places as you configure.

---

## Installing Falco on k3s

### Driver choice: why modern eBPF

Falco supports three drivers:
- `kernel_module` — traditional, needs kernel headers on every node
- `ebpf` — classic eBPF probe, still needs kernel headers
- `modern_ebpf` — uses BTF, no kernel headers, kernel 5.8+ required

Ubuntu 24.04 with kernel 6.8 satisfies modern eBPF. Use it:

```bash
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm repo update

helm install falco falcosecurity/falco \
  --namespace falco \
  --create-namespace \
  --kubeconfig /etc/rancher/k3s/k3s.yaml \
  --set driver.kind=modern_ebpf \
  --set falcosidekick.enabled=true \
  --set "falcosidekick.config.kafka.hostport=aois-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092" \
  --set falcosidekick.config.kafka.topic=aois-security \
  --set falcosidekick.config.kafka.minimumpriority=warning \
  --values k8s/falco/custom-rules.yaml
```

### Verify

```bash
sudo kubectl get pods -n falco --kubeconfig /etc/rancher/k3s/k3s.yaml
# NAME                                   READY   STATUS    RESTARTS
# falco-f94db                            2/2     Running   0        ← falco + falco-driver-loader
# falco-falcosidekick-7c569997f5-82lv9   1/1     Running   0
# falco-falcosidekick-7c569997f5-wwf9r   1/1     Running   0        ← 2 sidekick replicas

sudo kubectl logs -n falco --kubeconfig /etc/rancher/k3s/k3s.yaml \
  -l app.kubernetes.io/name=falco -c falco --tail=5
# Opening 'syscall' source with modern BPF probe.
# One ring buffer every '2' CPUs.
```

The `2/2` ready count means the falco container AND the falco-driver-loader init container both completed. The last log line confirms the eBPF probe is open on real syscalls.

### What `minimumpriority=warning` means

Falco priorities from lowest to highest: `debug`, `info`, `notice`, `warning`, `error`, `critical`, `emergency`, `alert`.

With `minimumpriority=warning`, Sidekick only forwards `warning` and above. Notice-level events (e.g., "container talking to k8s API" — noisy, expected from Strimzi) are suppressed. You pay for signal, not noise.

▶ **STOP — do this now**

Check what priority the built-in rules fire at and understand which will reach your Kafka topic:

```bash
sudo kubectl exec -n falco --kubeconfig /etc/rancher/k3s/k3s.yaml \
  -l app.kubernetes.io/name=falco -c falco -- \
  grep -E "priority:" /etc/falco/falco_rules.yaml | sort | uniq -c | sort -rn | head -10
```

Count how many rules fire at notice vs warning vs error. This tells you how much of the default ruleset reaches Sidekick vs stays in Falco stdout only.

---

## Writing Custom Falco Rules

Falco rules live in YAML. Every rule has the same shape:

```yaml
- rule: Name of the rule
  desc: One sentence describing what it detects
  condition: >
    <boolean expression using Falco fields and macros>
  output: >
    Human-readable alert string with field interpolation
  priority: WARNING
  tags: [category, mitre_technique_id]
```

### Key Falco fields

| Field | What it holds |
|---|---|
| `proc.name` | Name of the process |
| `proc.pname` | Name of the parent process |
| `proc.cmdline` | Full command line |
| `container.name` | Container name |
| `container.image.repository` | Image repo (e.g., `ghcr.io/kolinzking/aois`) |
| `fd.name` | File descriptor name (file path or socket) |
| `fd.rip` | Remote IP for network connections |
| `fd.rport` | Remote port |
| `user.name` | Username inside the container |
| `evt.type` | Syscall type (`execve`, `open`, `connect`, ...) |

### Key Falco macros (pre-built conditions)

| Macro | What it means |
|---|---|
| `spawned_process` | A new process was execve'd |
| `container` | Event happened inside a container (not on the host) |
| `outbound` | An outbound network connection |
| `open_write` | A file was opened for writing |
| `shell_procs` | proc.name is a known shell binary |

### AOIS custom rules

`k8s/falco/custom-rules.yaml` ships five rules targeting AOIS specifically:

**1. Shell spawned in AOIS container** (WARNING)
```yaml
condition: spawned_process and container
  and container.image.repository contains "aois"
  and proc.name in (bash, sh, zsh, dash, ash)
```
A shell inside the AOIS container is almost always an attacker or a misconfigured `kubectl exec`. AOIS should never need a shell in production.

**2. AOIS container writing to /etc** (ERROR)
```yaml
condition: open_write and container
  and container.image.repository contains "aois"
  and fd.name startswith /etc
```
If AOIS writes to `/etc`, something has gone wrong. A prompt injection could theoretically trigger this if AOIS were given file write tools (v20 gives it tools — this rule matters then).

**3. Unexpected outbound from AOIS on non-AI port** (WARNING)
```yaml
condition: outbound and container
  and container.image.repository contains "aois"
  and fd.sport != 443 and fd.sport != 9092
  and fd.sport != 5432 and fd.sport != 6379
```
AOIS should only talk to AI APIs (443), Kafka (9092), Postgres (5432), Redis (6379). Anything else is suspicious.

**4. Privilege escalation attempt** (WARNING)
```yaml
condition: spawned_process and container
  and proc.name in (sudo, su, newgrp)
```
Any container. Privilege escalation in a containerised workload is almost always an attacker.

**5. Package manager at runtime** (WARNING)
```yaml
condition: spawned_process and container
  and proc.name in (apt, apt-get, yum, pip, pip3, npm, curl, wget)
```
An attacker who gains code execution will immediately try to download tools. This catches it.

▶ **STOP — do this now**

Trigger rule 1 manually:

```bash
# This exec spawns sh inside the AOIS container → triggers the rule
sudo kubectl exec -n aois --kubeconfig /etc/rancher/k3s/k3s.yaml deploy/aois \
  -- sh -c "echo trigger"

# Watch Falco catch it
sudo kubectl logs -n falco --kubeconfig /etc/rancher/k3s/k3s.yaml \
  -l app.kubernetes.io/name=falco -c falco --tail=5
# Look for: "Shell spawned in AOIS container"

# Watch Sidekick forward it to Kafka
sudo kubectl logs -n falco --kubeconfig /etc/rancher/k3s/k3s.yaml \
  -l app.kubernetes.io/name=falcosidekick --tail=10
# Expected: Kafka - Publish OK
```

---

## The Falco Alert JSON Format

When Sidekick sends an alert to Kafka, this is the shape:

```json
{
  "uuid": "abc-123",
  "rule": "Shell spawned in AOIS container",
  "priority": "Warning",
  "output": "Shell spawned in AOIS container (user=root container=aois image=ghcr.io/kolinzking/aois proc=sh parent=kubectl cmdline=sh -c echo trigger)",
  "output_fields": {
    "container.name": "aois",
    "container.image.repository": "ghcr.io/kolinzking/aois",
    "proc.name": "sh",
    "proc.pname": "kubectl",
    "proc.cmdline": "sh -c echo trigger",
    "user.name": "root"
  },
  "source": "syscall",
  "hostname": "aois",
  "time": "2026-04-23T20:18:29.000Z",
  "tags": ["aois", "shell", "T1059"]
}
```

The `output` field is a human-readable summary. The `output_fields` has structured key-value pairs for programmatic processing. The `tags` include MITRE ATT&CK technique IDs — `T1059` is "Command and Scripting Interpreter."

---

## Wiring Falco → AOIS Analysis

### Why a separate topic

Falco alerts (`aois-security`) and SRE logs (`aois-logs`) have different shapes. Keeping them in separate topics means:
- Different retention (both 7 days, but could diverge)
- Different consumer lag tracking (KEDA could scale differently per topic)
- Clear audit trail: you can tell which results came from security vs SRE inputs

### What the consumer does

`kafka/consumer.py` now subscribes to both topics. For each message, it detects the format:

```python
is_falco = "rule" in event and "priority" in event
```

Falco alerts always have `rule` and `priority`. SRE log events have `log` and `id`. One check, no ambiguity.

For Falco alerts, `extract_from_falco()` builds the log text:
```
[SECURITY ALERT] Rule: Shell spawned in AOIS container | Shell spawned ... (user=root ...)
```

And sets the tier: `ERROR`/`CRITICAL` → Claude (full reasoning), `WARNING` → Groq (fast triage).

The result published to `aois-results` includes `"source_topic": "aois-security"` so downstream knows which channel the alert came from.

### The full pipeline

```
kubectl exec into AOIS pod
  → kernel: execve(sh)
    → eBPF probe intercepts
      → Falco rule matches "Shell spawned in AOIS container" (WARNING)
        → Falco → Sidekick (HTTP)
          → Sidekick → aois-security (Kafka)
            → consumer.py reads message
              → extract_from_falco() → log_text + tier=fast
                → analyze() → Groq analysis
                  → aois-results (Kafka)
```

▶ **STOP — do this now**

Read messages from `aois-security` directly to see the raw Falco JSON:

```bash
# Run a Kafka console consumer inside the cluster
sudo kubectl run kafka-read --restart=Never --rm -it \
  --image=apache/kafka:3.7.0 \
  --kubeconfig /etc/rancher/k3s/k3s.yaml \
  -n kafka -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server aois-kafka-kafka-bootstrap:9092 \
  --topic aois-security \
  --from-beginning \
  --max-messages 3

# Then trigger another alert in a separate terminal:
sudo kubectl exec -n aois --kubeconfig /etc/rancher/k3s/k3s.yaml deploy/aois \
  -- sh -c "id"
```

You should see the raw Falco JSON appear in the consumer output. That is the message AOIS ingests and analyzes.

---

## Cilium: eBPF Networking (Fresh Cluster Setup)

Cilium is what Falco is for security, but for networking: eBPF-powered, replacing the traditional Linux networking stack inside Kubernetes.

### What kube-proxy does

Every Kubernetes Service (ClusterIP, NodePort, LoadBalancer) needs something to route traffic from the Service IP to the actual pod IPs. By default, that is kube-proxy — a process that watches the k8s API and maintains iptables rules. As cluster size grows, iptables tables grow, and every packet pays the lookup cost.

### What Cilium does instead

Cilium replaces kube-proxy with eBPF. Instead of iptables, Cilium maintains a hash map in kernel memory. A `kubectl get svc` query that used to traverse 500 iptables rules now does one hash lookup. At scale (1000+ services), this is a measurable latency difference.

Beyond kube-proxy replacement, Cilium adds:
- **L7 network policy** — "this pod can only call `/api/v1/analyze` on this service, not any other path"
- **Hubble** — real-time network flow visibility (who is talking to whom, with latency)
- **mTLS between pods** — mutual TLS without Istio
- **DNS-aware policy** — "this pod can talk to `api.anthropic.com` but not `*.amazonaws.com`"

### Why We Didn't Install Cilium on the Live Cluster

Cilium replacing kube-proxy on k3s requires reinstalling k3s with two flags:

```bash
# In /etc/rancher/k3s/config.yaml
flannel-backend: none
disable-kube-proxy: true
```

This means restarting k3s — which briefly removes the CNI from all running pods. Kafka and Strimzi would lose networking for 2–3 minutes. If Cilium fails to come up, the cluster has no CNI and pods can't communicate at all. Recovery requires SSH to the node.

For a learning environment with a running Kafka cluster, that risk isn't worth it. The commands below are what you would run on a fresh cluster — save them for a rebuild.

### Cilium on Fresh k3s (Complete Recipe)

```bash
# 1. Install k3s with Flannel and kube-proxy disabled
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='
  --flannel-backend=none
  --disable-kube-proxy
  --disable-network-policy
  --cluster-cidr=10.244.0.0/16
' sh -

# 2. Install the Cilium CLI
curl -L --remote-name-all \
  https://github.com/cilium/cilium-cli/releases/latest/download/cilium-linux-amd64.tar.gz
sudo tar xzvf cilium-linux-amd64.tar.gz -C /usr/local/bin

# 3. Install Cilium (replace IP with your node IP)
cilium install --version 1.16.0 \
  --set kubeProxyReplacement=true \
  --set k8sServiceHost=46.225.235.51 \
  --set k8sServicePort=6443

# 4. Wait for Cilium to be ready
cilium status --wait
# Expected:
#     /¯¯\
#  /¯¯\__/¯¯\    Cilium:             OK
#  \__/¯¯\__/    Operator:           OK
#  /¯¯\__/¯¯\    Envoy DaemonSet:    OK
#  \__/¯¯\__/    Hubble Relay:       OK
#     \__/        ClusterMesh:        disabled

# 5. Verify kube-proxy replacement
cilium config view | grep KubeProxyReplacement
# KubeProxyReplacement: True

kubectl get pods -A | grep kube-proxy
# (no output — kube-proxy is gone, Cilium handles it)
```

### Hubble: Network Flow Visibility

Once Cilium is running, enable Hubble:

```bash
cilium hubble enable
hubble observe --namespace aois
# Shows: aois-pod → aois-kafka-kafka-bootstrap:9092  (forwarded)
# Shows: aois-pod → api.anthropic.com:443             (forwarded)
```

Every network flow, in real time, with source/destination pod names. No iptables logs, no tcpdump, no packet captures. This is what makes "AOIS made an unexpected outbound connection" detectable at the network layer (Hubble) and at the syscall layer (Falco) simultaneously.

### Cilium Network Policy: L7 Example

Standard k8s NetworkPolicy works at L3/L4 (IP/port). Cilium extends it to L7 (HTTP path):

```yaml
apiVersion: cilium.io/v1alpha1
kind: CiliumNetworkPolicy
metadata:
  name: aois-egress
  namespace: aois
spec:
  endpointSelector:
    matchLabels:
      app: aois
  egress:
  - toFQDNs:
    - matchName: "api.anthropic.com"
    toPorts:
    - ports:
      - port: "443"
        protocol: TCP
  - toEndpoints:
    - matchLabels:
        app.kubernetes.io/name: kafka
    toPorts:
    - ports:
      - port: "9092"
        protocol: TCP
```

This allows AOIS to talk to Anthropic's API (port 443) and Kafka (9092). Everything else is denied. If a prompt injection caused AOIS to call any other host, the packet is dropped at the kernel level — before it leaves the pod.

▶ **STOP — do this now**

Write a CiliumNetworkPolicy for AOIS based on the template above and save it to `k8s/cilium/aois-egress.yaml`. Even though we're not deploying it to the live cluster today, writing it forces you to think through exactly what AOIS legitimately needs to talk to. This is the kind of policy that would be mandatory in a regulated environment.

---

## Tetragon: Process-Level eBPF Tracing

Falco watches for rule violations — you define what is suspicious and Falco alerts when it matches. Tetragon is different: it traces everything, continuously, without requiring rules. Every process start, every network connection, every file access — structured JSON, with full process lineage showing the complete chain of who spawned whom.

Tetragon is a Cilium sub-project. It uses eBPF kprobes to hook into kernel syscalls and emit events to userspace. The distinction from Falco:

| Capability | Falco | Tetragon |
|---|---|---|
| Real-time rule-based alerting | ✓ | Optional (TracingPolicy CRD) |
| Full process lineage (parent chain) | Partial | Full — every event |
| Binary hash of every executed process | No | Yes (`process.binary.hash`) |
| Network flow with process identity | No | Yes |
| Post-incident forensic timeline | Limited | Complete |
| Fanout to Kafka / Slack | Via Sidekick | Via log pipeline |

Use Falco for real-time alerting on known-bad patterns. Use Tetragon for forensic investigation after an alert fires — Tetragon tells you everything that happened, not just what matched a rule.

### Installing Tetragon on k3s

```bash
helm repo add cilium https://helm.cilium.io
helm repo update

helm install tetragon cilium/tetragon \
  --namespace kube-system \
  --kubeconfig /etc/rancher/k3s/k3s.yaml \
  --set tetragon.btf=/sys/kernel/btf/vmlinux
```

The `btf` flag points to the BTF file that k3s exposes on kernel 6.8 — same reason modern eBPF works for Falco without kernel headers.

Verify:
```bash
sudo kubectl get pods -n kube-system \
  --kubeconfig /etc/rancher/k3s/k3s.yaml | grep tetragon
# tetragon-xxxxx   1/1   Running   0
```

### Reading Tetragon Events

```bash
sudo kubectl exec -n kube-system \
  --kubeconfig /etc/rancher/k3s/k3s.yaml \
  -c tetragon \
  $(sudo kubectl get pods -n kube-system \
    -l app.kubernetes.io/name=tetragon \
    --kubeconfig /etc/rancher/k3s/k3s.yaml \
    -o jsonpath='{.items[0].metadata.name}') \
  -- tetra getevents -o compact
```

Expected output (compact mode uses emoji prefixes):
```
🚀 process aois/aois-pod-xxx /usr/local/bin/python3
🔌 connect aois/aois-pod-xxx tcp 10.42.0.15:54321 -> 35.185.44.232:443
📖 read    aois/aois-pod-xxx /var/run/secrets/kubernetes.io/serviceaccount/token
```

The emoji prefix: 🚀 = process start, 🔌 = network connect, 📖 = file read, ✏️ = file write, 🟥 = process killed. Every event includes full process lineage — trace from a network connection back to the exact subprocess that made it.

### TracingPolicy: Targeted Observation

Tetragon's `TracingPolicy` CRD defines which syscalls to trace, scoped to specific namespaces or container images:

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: aois-file-writes
spec:
  kprobes:
  - call: "sys_write"
    syscall: true
    selectors:
    - matchNamespaces:
      - namespace:
          operator: In
          values: ["aois"]
```

This traces every `write()` syscall from the `aois` namespace — complete coverage without rules, useful for post-incident forensics. Scoping to a namespace keeps CPU overhead minimal: Tetragon only processes events from matching pods.

### The Full-Stack Security Picture

Running Falco and Tetragon together on AOIS gives complementary coverage:

```
Event: kubectl exec into AOIS pod → shell spawned
  ↓
Falco fires: "Shell spawned in AOIS container" → Sidekick → aois-security Kafka → AOIS analyzes
  ↓
Tetragon records: process tree (who spawned sh), every command sh ran, every file it read,
                  every network connection it made — timestamped, continuous, forensic
```

Falco tells you "something happened, here is the rule that matched." Tetragon tells you everything that happened, including things that matched no rule. In a security investigation, you start with the Falco alert and use Tetragon to reconstruct the full story.

---

## Common Mistakes

**Falco pod stuck at 1/2 READY**
Symptom: `falco-xxxxx   1/2   Running`
Cause: The driver loader init container (the second container) is still building/loading the eBPF probe.
Fix: Wait 30–60 seconds. Check: `kubectl logs -n falco <pod> -c falco-driver-loader`
If it fails: the kernel doesn't have BTF. Verify with `ls /sys/kernel/btf/vmlinux` — if missing, use `driver.kind=ebpf` and install kernel headers instead.

**Sidekick shows Kafka - ERR instead of Kafka - Publish OK**
Symptom: `Kafka - (1) - ERR`
Cause: Sidekick can't reach the Kafka broker.
Fix: Verify the hostport. The broker must be reachable from the `falco` namespace. Check:
```bash
kubectl run test --restart=Never --rm -it \
  --image=busybox -n falco \
  -- nc -zv aois-kafka-kafka-bootstrap.kafka.svc.cluster.local 9092
# Expected: open
```
If it fails, the service DNS is wrong or Kafka is in a different namespace than expected.

**Custom rules not loading**
Symptom: your rule name doesn't appear in Falco logs at startup.
Cause: YAML syntax error in the rules file, or `customRules` key name mismatch in values.yaml.
Fix: `kubectl logs -n falco <pod> -c falco | grep "schema validation"` — Falco reports the file and whether it passed schema validation.

**Alerts fire but don't reach Kafka (minimumpriority too high)**
Symptom: Falco logs show the alert, Sidekick logs show nothing.
Cause: The alert priority is below `minimumpriority=warning`.
Fix: Lower minimumpriority temporarily: `helm upgrade falco falcosecurity/falco --set falcosidekick.config.kafka.minimumpriority=notice`
Or: raise your rule's priority.

**Shell rule fires on every `kubectl exec`**
This is not a bug. `kubectl exec` spawns a shell. In production, `kubectl exec` into a production pod IS a security event worth knowing about. The alert is correct.

**Tetragon events not appearing for a specific namespace**

Symptom: `tetra getevents --namespace aois` returns no output even though AOIS pods are running and receiving traffic.

Cause: The `--namespace` filter matches the Kubernetes namespace label on the pod, not the network namespace. Verify the filter is correct by checking what namespace the pod reports:

```bash
sudo kubectl get pod -n aois \
  --kubeconfig /etc/rancher/k3s/k3s.yaml \
  -o jsonpath='{.items[0].metadata.namespace}'
# Expected: aois
```

If the namespace is correct but events still don't appear, remove the namespace filter and use `jq` to filter manually — this confirms whether Tetragon is producing events at all:

```bash
kubectl exec -n kube-system -c tetragon <pod> -- \
  tetra getevents -o json \
  | jq 'select(.process.pod.namespace == "aois")'
```

If this returns events, the `--namespace` flag syntax changed between versions. Check `tetra getevents --help` for the current flag name.

---

## Troubleshooting

**`modern BPF probe` fails to open**
```
Error: Failed to open the modern BPF probe
```
Means kernel < 5.8 or BTF missing. Check:
```bash
uname -r        # Must be >= 5.8
ls /sys/kernel/btf/vmlinux  # Must exist
```
If absent, switch to `driver.kind=ebpf` and install `linux-headers-$(uname -r)` on the node.

**Consumer not processing `aois-security` messages**
Check that the consumer group is subscribed to both topics:
```bash
# List all topic subscriptions for the consumer group
sudo kubectl exec -n kafka --kubeconfig /etc/rancher/k3s/k3s.yaml \
  aois-kafka-combined-0 -- \
  bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group aois-workers
```
Should show both `aois-logs` and `aois-security` in the output.

**Falco firing too many alerts (noise)**
The built-in ruleset has hundreds of rules. In production, you tune them:
```bash
# Disable a noisy built-in rule
helm upgrade falco falcosecurity/falco \
  --set "falco.rules[0].rule=Contact K8S API Server From Container" \
  --set "falco.rules[0].enabled=false"
```
Or use a macro to exclude known-good containers from a rule condition.

---

## Connection to Later Phases

**v20 (Tool Use + Agent Memory):** When AOIS gets tools — `get_pod_logs`, `describe_node` — it gains the ability to write. Falco rule 2 ("AOIS container writing to /etc") becomes load-bearing. If a prompt injection causes AOIS to abuse a tool, Falco catches it at the kernel level before the write completes. Security and agent capability are the same concern.

**v23 (LangGraph: Autonomous SRE Loop):** The autonomous investigation loop processes many events. Some will be Falco alerts — a shell spawned in a pod while AOIS was investigating an OOMKilled event is a compound incident. LangGraph's graph structure handles this: the security alert feeds into the same Detect → Investigate → Hypothesize → Remediate loop.

**v25 (E2B Safe Code Execution):** AOIS will be asked to write and run remediation scripts. Falco in the E2B sandbox can watch what those scripts actually do — not just what AOIS intended them to do. That is the difference between trusting the LLM and verifying the execution.

**v33 (Red-teaming and AI Safety):** PyRIT + Garak test AOIS at the application layer. Falco tests it at the kernel layer. Running both simultaneously gives you full-stack adversarial coverage — application-level attacks (prompt injection) AND execution-level effects (unexpected processes, network connections).

---

## Mastery Checkpoint

1. **Explain eBPF to someone who knows Linux but not Kubernetes**: what problem does it solve, what are the two alternatives, and what makes it safe to run in the kernel.

2. **Read a Falco alert JSON** and extract: which rule fired, what process triggered it, which container it ran in, and the MITRE ATT&CK technique ID. State what the attacker was likely trying to do.

3. **Write a new Falco rule** that fires WARNING when any container reads `/proc/1/mem` (credential dumping technique). Include the `condition`, `output`, `priority`, and one MITRE ATT&CK tag.

4. **Explain why `minimumpriority=warning`** means Strimzi's k8s API calls don't reach Kafka, and what you would change if you wanted to capture those too (and why you probably shouldn't).

5. **Trace an alert end-to-end** from `kubectl exec` to a message in `aois-results`: name every component the alert passes through and what format the data is in at each step.

6. **Explain the Cilium vs Flannel tradeoff**: what does replacing Flannel with Cilium cost (operationally) and what do you gain (technically)? When would you pay that cost?

7. **Write the `CiliumNetworkPolicy`** for AOIS (`k8s/cilium/aois-egress.yaml`) that allows only: Anthropic API (443), Groq API (443), Kafka (9092), Postgres (5432), Redis (6379), OTel Collector (4317). Deny everything else. Save it to the repo even though it's not deployed — this is the policy that would ship with a regulated deployment.

8. **Explain the relationship between Falco and v5's output blocklist**: they are both security controls, but they operate at different layers and catch different things. Be specific about what each one catches that the other cannot.

**The mastery bar:** given a new containerised service running on Kubernetes, you can deploy Falco, write targeted rules for that service's expected behaviour, wire alerts into a Kafka-based processing pipeline, and explain to a security team member why the eBPF approach gives you observability that application logging cannot.

---

*Phase 6 is complete. v17 built the Kafka streaming layer. v18 brought runtime security — every process, every file, every connection now visible to AOIS. Phase 7 is next: autonomous agents. v20 gives AOIS tools — and now Falco watches what it does with them.*

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### Falco

| Layer | |
|---|---|
| **Plain English** | A real-time security monitor that watches everything happening inside your containers at the kernel level — processes spawned, files opened, network connections made — and fires an alert the moment something unexpected occurs. |
| **System Role** | Falco is AOIS's runtime security sensor. It watches every pod on the Hetzner cluster. When a container spawns a shell, writes to `/etc`, or makes an unexpected outbound connection, Falco fires a rule, Falco Sidekick publishes the alert to the `aois-security` Kafka topic, and the AOIS consumer analyzes it with Claude (CRITICAL/ERROR) or Groq (WARNING). This closes the loop: AOIS doesn't just analyze logs — it analyzes its own security events. |
| **Technical** | Falco uses a kernel module or eBPF driver to intercept system calls. Rules are written in a YAML DSL: `condition: container and proc.name = bash` triggers on any shell inside a container. The modern eBPF driver uses BTF (BPF Type Format) built into the kernel — no kernel headers needed on Linux 5.8+. Falco Sidekick is a separate process that receives Falco alerts via HTTP and fans them out to 50+ destinations including Kafka, Slack, PagerDuty, and webhooks. |
| **Remove it** | Without Falco, container compromises are only visible in application logs — if the attacker doesn't touch the application. A shell spawned inside an AOIS pod, a curl to an exfiltration endpoint, or a privilege escalation attempt produce zero application-layer logs. Falco catches these at the syscall layer regardless of what the application does or doesn't log. This is the visibility layer that application logging fundamentally cannot provide. |

**Say it at three levels:**
- *Non-technical:* "Falco is a security camera at the kernel level. It doesn't watch what your app decides to report — it watches everything the container actually does at the OS level. An attacker who disables application logging can't disable Falco."
- *Junior engineer:* "Falco rules: `- rule: Shell in container, condition: container and spawned_process and proc.name in (shell_binaries), output: '%container.name shell spawned', priority: WARNING`. Deploy via Helm: `helm install falco falcosecurity/falco --set driver.kind=ebpf`. Falco Sidekick config: `kafka.brokers`, `kafka.topic`, `kafka.minimumpriority`. The AOIS consumer detects Falco format by checking for `rule` and `priority` fields in the JSON."
- *Senior engineer:* "Falco's performance cost is syscall inspection overhead — roughly 2–5% CPU on a busy host. The eBPF driver is lower-overhead than the kernel module and safer (eBPF is verified by the kernel before loading; kernel modules run as ring-0 code). The operational gap: Falco rules require tuning per workload. Default rules generate significant noise on development clusters — every `kubectl exec` fires. AOIS's 5 custom rules are scoped to the actual threat model: unexpected shells, /etc writes, outbound connections not to known endpoints, privilege escalation, package manager execution. This is the minimum viable threat model for a container running untrusted input (log data from potentially compromised services)."

---

### eBPF

| Layer | |
|---|---|
| **Plain English** | A way to run small custom programs inside the Linux kernel — safely, without modifying the kernel or loading risky kernel modules — to observe or control exactly what the system is doing at the lowest possible level. |
| **System Role** | eBPF is the kernel technology that makes Falco's modern driver work. Instead of a loadable kernel module (which can crash the kernel), Falco uses an eBPF program verified by the kernel verifier before execution. eBPF is also the foundation of Cilium (v18 notes) — the same primitive that powers network policy and deep observability without a service mesh. Understanding eBPF is understanding why the next generation of observability and security tools is fundamentally different from the previous one. |
| **Technical** | eBPF programs are compiled to bytecode, verified by the kernel verifier (checks for loops, out-of-bounds access, unsafe operations), then JIT-compiled to native instructions. Programs attach to kernel hooks: kprobes (function entry/exit), tracepoints (static kernel events), XDP (network packet processing). They communicate with userspace via eBPF maps (key-value stores shared between kernel and userspace). Falco attaches eBPF programs to syscall tracepoints — every `open()`, `execve()`, `connect()` call is inspected. |
| **Remove it** | Without eBPF, kernel-level observability requires: (a) kernel modules — risky, kernel-version specific, crash the node if buggy; or (b) application instrumentation — misses anything the application doesn't instrument. eBPF is the reason tools like Falco, Cilium, Datadog's APM, and Pixie can provide deep observability without touching application code. It is the infrastructure primitive that makes the next generation of security and observability tools possible — every tool in this space is converging on eBPF as the mechanism. |

**Say it at three levels:**
- *Non-technical:* "eBPF is a safe way to put a recording device inside the Linux kernel. Previous approaches were like wiring directly into the engine — dangerous and fragile. eBPF is like installing a sensor that the engine itself validates before allowing."
- *Junior engineer:* "You don't write eBPF programs directly in this curriculum — Falco and Cilium handle that. What you need to understand: when Falco says 'eBPF driver', it means a kernel-level program is intercepting syscalls and sending events to Falco userspace via a ring buffer. `bpftool prog list` shows loaded eBPF programs on the node. `sudo kubectl exec -it falco-XXX -- bpftool prog list` shows Falco's programs. The kernel version requirement: Linux 5.8+ for BTF-based eBPF (no kernel headers), which is why the Hetzner k3s setup works cleanly on kernel 6.8."
- *Senior engineer:* "eBPF's verifier is the safety guarantee — it's a formal proof that the program terminates and doesn't corrupt kernel memory. This is why eBPF programs can be loaded into production kernels that would never accept a foreign kernel module. The performance characteristic: eBPF maps use copy-on-write and lock-free ring buffers for kernel→userspace communication — much lower overhead than the alternative (netlink sockets, /proc polling). The ecosystem trajectory: eBPF is becoming the universal instrumentation layer. Cilium replaces kube-proxy, iptables, and CNI with eBPF programs. Tetragon extends Falco's syscall visibility with process tree tracking. Every new observability or security tool built in 2024+ is built on eBPF."

---

### Cilium

| Layer | |
|---|---|
| **Plain English** | A Kubernetes networking plugin that uses eBPF to replace the traditional Linux networking stack — giving you faster packet routing, security policy down to the HTTP path level, and real-time network flow visibility, all without a service mesh. |
| **System Role** | Cilium would replace Flannel as the CNI on the Hetzner k3s cluster. It handles all pod-to-pod routing, exposes network flows via Hubble (who is talking to whom, with latency), and enforces `CiliumNetworkPolicy` restricting AOIS to only its legitimate endpoints (Anthropic API, Kafka, Postgres, Redis). It is not installed on the live cluster — CNI replacement requires a k3s restart — but the fresh-cluster recipe in these notes covers the exact steps for the next rebuild. |
| **Technical** | Cilium replaces kube-proxy by maintaining an eBPF hash map of service-to-pod mappings in kernel memory. A packet destined for a ClusterIP does one hash lookup instead of traversing iptables chains — measurably faster at 1000+ services. `CiliumNetworkPolicy` extends standard k8s NetworkPolicy to L7: `toPorts[].rules.http.path` allows per-HTTP-path policy. Hubble records every network flow as a structured event accessible via `hubble observe`. |
| **Remove it** | Without Cilium: network policy is iptables-based (L3/L4 only, no FQDN or HTTP-path matching). If AOIS is compromised, it can freely connect to any external endpoint — standard NetworkPolicy has no way to say "allow `api.anthropic.com` but not `attacker.io`." Cilium is what makes "AOIS can talk to Anthropic's API but nothing else unexpected" enforceable at the kernel level. |

**Say it at three levels:**
- *Non-technical:* "Cilium is the traffic cop inside Kubernetes. It controls which services can talk to which others, and it uses a newer, faster method (eBPF) instead of the traditional iptables approach."
- *Junior engineer:* "Fresh k3s with Cilium: `curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='--flannel-backend=none --disable-kube-proxy' sh -`, then `cilium install --set kubeProxyReplacement=true --set k8sServiceHost=<NODE_IP>`. Verify: `cilium status --wait`. Network visibility: `cilium hubble enable && hubble observe --namespace aois` — shows every pod connection with source, destination, and HTTP path."
- *Senior engineer:* "Cilium's CNI migration risk is why the live cluster uses Flannel: CNI replacement requires draining all pods and restarting k3s with `--flannel-backend=none`. A 2–3 minute network blackout is unavoidable — Kafka and Strimzi lose networking during this window. In production this is a maintenance window operation. The payoff: Hubble L7 flows show HTTP method, path, and response code for every pod connection, with no application instrumentation required. For v34 EU AI Act compliance audit requirements, that network telemetry is what regulators expect to see."

---

### Tetragon

| Layer | |
|---|---|
| **Plain English** | A security observability tool that records a continuous timeline of everything happening inside every container — which processes ran, what files they accessed, what network connections they made — so that after an incident you can reconstruct the complete picture at the kernel level, not just what the application chose to log. |
| **System Role** | Tetragon runs alongside Falco on the k3s cluster. Falco fires real-time alerts when rules match (shell spawned, /etc write). Tetragon records the forensic timeline: if a Falco alert fires for "shell in AOIS container," Tetragon's record shows which binary executed, what it read and wrote, which network connections it made, and the full process lineage from the shell back to the kubectl exec or compromised subprocess that started it. Falco tells you something happened. Tetragon tells you everything that happened. |
| **Technical** | Tetragon uses eBPF kprobes to intercept kernel syscalls — `sys_execve`, `sys_read`, `sys_write`, `sys_connect`. Events are emitted as structured JSON with `process.binary.path`, `process.pid`, `process.parent_exec_id`, and `node_name`. The `TracingPolicy` CRD scopes observation to specific namespaces, binary paths, or syscalls, keeping CPU overhead minimal. Process lineage is the key forensic feature: every event includes the full parent chain (pid → ppid → ... → PID 1). |
| **Remove it** | Without Tetragon: post-incident forensics relies on application logs (only what the app decided to log), Falco alerts (only what matched a rule), and container stdout. A sophisticated attacker who knows the Falco rules can avoid triggering them. Tetragon has no rules to avoid — it records everything. The question "what did this process actually do after the shell was spawned?" is only answerable from Tetragon's event stream. Without it, the investigation stops at the Falco alert and cannot go deeper. |

**Say it at three levels:**
- *Non-technical:* "Falco is the burglar alarm — it goes off when something suspicious matches a rule. Tetragon is the CCTV recording everything continuously, so you can review the full footage after the alarm goes off."
- *Junior engineer:* "Read events live: `kubectl exec -n kube-system -c tetragon <pod> -- tetra getevents -o compact`. Compact mode uses emoji: 🚀 process, 🔌 network, 📖 file read, ✏️ file write. Filter to AOIS namespace: `tetra getevents --namespace aois`. For structured JSON (scriptable): remove `-o compact` and pipe to `jq .process.binary.path` to extract which binary ran."
- *Senior engineer:* "Tetragon's eBPF ring buffer design is what makes always-on recording viable. Traditional auditd on a busy host becomes a performance problem — too many events, too much overhead. eBPF ring buffers are lock-free and sized to absorb bursts without blocking the kernel. The TracingPolicy CRD is the operational tuning knob: scoping to one namespace and a handful of syscalls adds negligible overhead. In a v34 EU AI Act compliance context, Tetragon's event stream is the audit log that proves what the AI agent did at the OS level — not just what it reported doing. That distinction matters to auditors."
