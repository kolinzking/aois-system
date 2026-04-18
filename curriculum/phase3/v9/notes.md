# v9 — KEDA: Intelligent Autoscaling
⏱ **Estimated time: 3–4 hours**

## What this version builds

v8 gave AOIS a fixed number of pods — `replicaCount: 2` in `values.prod.yaml`. If load spikes, AOIS strains. If load drops overnight, two pods sit idle burning money.

v9 wires in KEDA: Kubernetes Event-Driven Autoscaler. KEDA watches a trigger metric (CPU utilization here, Kafka topic lag in v17) and instructs Kubernetes to add or remove pods automatically. The number of AOIS pods is no longer a number you pick — it is a consequence of real load.

At the end of v9:
- **KEDA installed** on the k3s cluster
- **ScaledObject in the Helm chart** — one file, all scaling configuration
- **CPU trigger active** — AOIS scales up when CPU crosses the threshold
- **ArgoCD deploys it** — git push → ScaledObject live → KEDA takes over
- **Kafka trigger understood** — you know exactly what changes in v17

---

## Prerequisites

- v8 complete: ArgoCD watching `main`, auto-sync enabled, AOIS live at https://aois.46.225.235.51.nip.io
- SSH access to the Hetzner server (46.225.235.51)
- `kubectl` working locally with the Hetzner kubeconfig

Verify the cluster is reachable and AOIS is running:
```bash
kubectl get pods -n aois
```
Expected:
```
NAME                    READY   STATUS    RESTARTS   AGE
aois-7d9f4b8c6-xk2mj   1/1     Running   0          2d
aois-7d9f4b8c6-p9mn2   1/1     Running   0          2d
```

Verify ArgoCD is synced:
```bash
argocd app get aois
```
Expected:
```
Health Status:  Healthy
Sync Status:    Synced
```

---

## Learning goals

By the end of this version you will be able to:
- Explain what KEDA is and why it exists separately from Kubernetes HPA
- Describe the ScaledObject spec: scaleTargetRef, triggers, minReplicaCount, maxReplicaCount, cooldownPeriod
- Explain why CPU scaler cannot scale to zero but Kafka scaler can
- Install KEDA on a live cluster and verify it is running
- Add a ScaledObject to a Helm chart and deploy it through ArgoCD
- Read KEDA's managed HPA to understand current scaling state
- Know exactly what changes in v17 when Kafka replaces CPU as the trigger

---

## Why KEDA Exists

Kubernetes has its own autoscaler: the HorizontalPodAutoscaler (HPA). HPA works on CPU and memory — built-in metrics only. It cannot scale based on Kafka queue depth, Redis list length, Prometheus metrics, or any external signal.

KEDA extends HPA. It does not replace it — it sits in front of it. When you create a ScaledObject, KEDA:
1. Reads your trigger definition (CPU, Kafka, Prometheus, etc.)
2. Converts the trigger signal into a replica count
3. Creates and manages an HPA behind the scenes
4. Updates the HPA's target replica count as the signal changes

You never create an HPA manually when using KEDA. KEDA creates it for you, owns it, and updates it. If you look at HPAs after installing KEDA, you will see one named after your ScaledObject — that is KEDA's managed HPA.

```
Your ScaledObject → KEDA → managed HPA → Kubernetes scheduler → pods
```

The other thing KEDA adds: **scale to zero**. Standard HPA has a minimum of 1. KEDA allows `minReplicaCount: 0` — AOIS goes from 2 pods to 0 when idle. When a trigger fires (a Kafka message arrives, an HTTP request comes in), KEDA scales from 0 to N. This is how production AI services handle cost at scale.

**Why CPU is the starter trigger, and why Kafka is the production trigger:**

CPU scaler limitation: if there are 0 pods, there is no CPU to measure — the scaler has no signal. KEDA cannot scale from 0 using CPU. It needs at least 1 pod to read CPU data.

Kafka scaler: Kafka tracks how many messages are waiting unprocessed (consumer lag). If lag is 0 and you have 0 pods, KEDA knows there is nothing to process and keeps pods at 0. When messages arrive, lag goes from 0 to N — KEDA scales pods up even from zero. This is the correct production pattern for AOIS in v17.

For v9: CPU scaler teaches the KEDA pattern cleanly without Kafka infrastructure. In v17, you swap the trigger type — everything else stays the same.

---

## Step 1: Install KEDA on the Cluster

KEDA is not installed by default on k3s. Install it with the official manifest:

```bash
kubectl apply --server-side -f https://github.com/kedacore/keda/releases/download/v2.14.0/keda-2.14.0.yaml
```

The `--server-side` flag is required because KEDA's CRD manifest is large — client-side apply hits annotation size limits.

Watch the KEDA pods come up:
```bash
kubectl get pods -n keda -w
```
Expected (may take 60–90 seconds):
```
NAME                                      READY   STATUS    RESTARTS   AGE
keda-operator-6b9d4b8f7c-xk2mj           1/1     Running   0          90s
keda-operator-metrics-apiserver-xxx       1/1     Running   0          90s
keda-admission-webhooks-xxx               1/1     Running   0          90s
```

Verify KEDA's CRDs are installed (these are the Kubernetes resource types KEDA adds):
```bash
kubectl get crd | grep keda
```
Expected:
```
clustertriggerauthentications.keda.sh
scaledjobs.keda.sh
scaledobjects.keda.sh
triggerauthentications.keda.sh
```

`scaledobjects.keda.sh` is the key one — this is the CRD that your ScaledObject manifest uses.

▶ **STOP — do this now**

Before continuing, verify KEDA is healthy:
```bash
kubectl get pods -n keda
kubectl get crd | grep keda | wc -l
```
Expected: 3 pods Running, 4 CRDs. If any KEDA pod is not Running, check:
```bash
kubectl describe pod -n keda -l app=keda-operator
```
Common cause: the manifest was not applied with `--server-side`. Re-run with that flag.

---

## Step 2: Understand the ScaledObject

The ScaledObject file was added to the Helm chart in this version. Read it:

```bash
cat charts/aois/templates/scaledobject.yaml
```

```yaml
{{- if .Values.keda.enabled }}
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: {{ .Release.Name }}
  namespace: {{ .Values.namespace }}
  labels:
    app: {{ .Release.Name }}
spec:
  scaleTargetRef:
    name: {{ .Release.Name }}           # the Deployment KEDA controls
  minReplicaCount: {{ .Values.keda.minReplicas }}
  maxReplicaCount: {{ .Values.keda.maxReplicas }}
  cooldownPeriod: {{ .Values.keda.cooldownPeriod }}
  pollingInterval: {{ .Values.keda.pollingInterval }}
  triggers:
    - type: cpu
      metricType: Utilization
      metadata:
        value: "{{ .Values.keda.cpu.targetUtilization }}"
{{- end }}
```

**Field by field:**

`scaleTargetRef.name` — the Deployment KEDA controls. Must match exactly. KEDA reads this Deployment's current replica count and updates it.

`minReplicaCount` — the floor. With CPU trigger: minimum 1 (cannot go to 0 without an external trigger). With Kafka trigger: can be 0.

`maxReplicaCount` — the ceiling. KEDA will never create more pods than this, even if load demands it. Set this thoughtfully — it is your cost ceiling.

`cooldownPeriod` — seconds to wait after load drops before scaling down. 300 seconds (5 minutes) prevents flapping: a brief drop does not trigger a scale-down that would require a scale-up 30 seconds later.

`pollingInterval` — how often KEDA checks the trigger metric. 30 seconds is the default. Lower = faster reaction, more API calls to metrics server.

`triggers` — the list of signals that drive scaling. KEDA evaluates all triggers and scales to the highest replica count any trigger demands. In v9, one trigger (CPU). In v17, you add a second trigger (Kafka lag) — both run simultaneously and KEDA takes the max.

The values that drive this template come from `values.prod.yaml`:
```yaml
keda:
  enabled: true
  minReplicas: 1
  maxReplicas: 5
  cooldownPeriod: 300
  cpu:
    targetUtilization: "60"
```

`enabled: false` in `values.yaml` means the ScaledObject is not created for local dev or non-KEDA environments. Set `enabled: true` in `values.prod.yaml` to activate it on the production cluster.

▶ **STOP — do this now**

Render the chart locally and inspect the ScaledObject output before deploying:
```bash
helm template aois ./charts/aois -f charts/aois/values.prod.yaml | grep -A 25 "ScaledObject"
```
Expected output:
```yaml
kind: ScaledObject
metadata:
  name: aois
  namespace: aois
spec:
  scaleTargetRef:
    name: aois
  minReplicaCount: 1
  maxReplicaCount: 5
  cooldownPeriod: 300
  pollingInterval: 30
  triggers:
    - type: cpu
      metricType: Utilization
      metadata:
        value: "60"
```

Verify it is NOT rendered with the default values (keda.enabled is false):
```bash
helm template aois ./charts/aois | grep -c "ScaledObject"
```
Expected: `0` — the `{{- if .Values.keda.enabled }}` guard works.

---

## Step 3: Deploy Through ArgoCD

The ScaledObject is in the Helm chart. ArgoCD watches the chart. Deploying is a git push.

First, verify the chart renders without errors:
```bash
helm lint ./charts/aois
```
Expected:
```
==> Linting ./charts/aois
[INFO] Chart.yaml: icon is recommended

1 chart(s) linted, 0 chart(s) failed
```

Commit and push:
```bash
git add charts/aois/templates/scaledobject.yaml charts/aois/values.yaml charts/aois/values.prod.yaml
git commit -m "v9: KEDA ScaledObject — CPU trigger, 1-5 replicas"
git push
```

Force ArgoCD to sync immediately (instead of waiting 3 minutes):
```bash
argocd app sync aois
```

Expected output:
```
TIMESTAMP    GROUP              KIND         NAMESPACE  NAME  STATUS   HEALTH
...          keda.sh            ScaledObject  aois      aois  Synced   -
```

The ScaledObject is `Synced` but `Health` shows `-` — KEDA resources do not have a standard Kubernetes health check that ArgoCD knows how to evaluate. This is expected.

▶ **STOP — do this now**

After the sync, verify KEDA picked up the ScaledObject:
```bash
kubectl get scaledobject -n aois
```
Expected:
```
NAME   SCALETARGETKIND   SCALETARGETNAME   MIN   MAX   TRIGGERS   READY   ACTIVE
aois   Deployment        aois              1     5     cpu        True    False
```

`READY: True` — KEDA connected to the deployment successfully.
`ACTIVE: False` — no trigger is currently firing (CPU is below 60%). AOIS is at minimum replicas.

Now check the HPA KEDA created for you:
```bash
kubectl get hpa -n aois
```
Expected:
```
NAME              REFERENCE         TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
keda-hpa-aois     Deployment/aois   3%/60%    1         5         1          2m
```

You never created this HPA. KEDA created it. `3%/60%` means current CPU is 3%, target is 60% — well below threshold, so AOIS stays at 1 replica.

---

## Step 4: Watch KEDA Scale

Generate load to push CPU above the 60% threshold and watch KEDA respond.

Run a load test against the live endpoint:
```bash
# Install hey if not present
go install github.com/rakyll/hey@latest
# or use ab (apache bench): apt-get install apache2-utils

# Send 500 concurrent analyze requests
hey -n 500 -c 20 -m POST \
  -H "Content-Type: application/json" \
  -d '{"log": "pod OOMKilled in production namespace", "tier": "standard"}' \
  https://aois.46.225.235.51.nip.io/analyze
```

In a separate terminal, watch what happens:
```bash
# Watch pods and HPA simultaneously
watch -n 5 'echo "=== PODS ===" && kubectl get pods -n aois && echo "" && echo "=== HPA ===" && kubectl get hpa -n aois && echo "" && echo "=== SCALEDOBJECT ===" && kubectl get scaledobject -n aois'
```

Expected sequence:
1. Load hits → CPU climbs above 60%
2. KEDA detects the threshold breach (within `pollingInterval` seconds)
3. HPA `REPLICAS` increases from 1 → 2 → 3
4. New pods spin up (30–60 seconds to `Running`)
5. Load distributes → CPU drops per pod
6. When load stops → CPU drops → after `cooldownPeriod` (300s) → replicas back to 1

```bash
# After load test, watch the scale-down (takes cooldownPeriod seconds)
kubectl get hpa -n aois -w
```

If you cannot generate enough load to trigger the threshold, you can temporarily lower the threshold to trigger it manually:
```bash
# Override just the threshold for testing
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml \
  --set keda.cpu.targetUtilization=5 -n aois
# Now any activity triggers scale-up
# Reset after testing:
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```

---

## Step 5: Understand scale-to-zero (and when CPU cannot do it)

Try setting `minReplicas: 0` and see what happens:
```bash
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml \
  --set keda.minReplicas=0 -n aois
```

Check the ScaledObject:
```bash
kubectl get scaledobject -n aois
```
```
NAME   SCALETARGETKIND  ...  MIN   MAX   TRIGGERS   READY   ACTIVE
aois   Deployment           0     5     cpu        True    False
```

Wait 10 minutes with no load. Check replicas:
```bash
kubectl get deployment aois -n aois
```
With CPU trigger, AOIS will **not** scale to 0 even with `minReplicas: 0`. The CPU metrics go away when there are 0 pods — KEDA has no signal and does not attempt the scale-down. This is the CPU scaler's fundamental limitation.

Now you understand why Kafka is the right trigger for scale-to-zero:
```yaml
# v17 — this replaces the cpu trigger
triggers:
  - type: kafka
    metadata:
      bootstrapServers: kafka:9092
      consumerGroup: aois-consumer
      topic: incoming-logs
      lagThreshold: "5"      # scale up when 5+ messages waiting per pod
```
When `lagThreshold` is met with 0 messages, KEDA confidently scales to 0. When messages arrive, lag jumps to N — KEDA scales from 0 to N/threshold pods. The signal exists independently of whether pods are running.

Reset to `minReplicas: 1` (correct for CPU trigger):
```bash
# Just push the chart — ArgoCD handles it
git push  # ArgoCD syncs back to values.prod.yaml which has minReplicas: 1
```

---

## Common Mistakes

**KEDA applied without `--server-side` — annotation too large** *(recognition)*
`kubectl apply -f keda-2.14.0.yaml` without `--server-side` fails because KEDA's CRD annotations exceed the 262KB limit that client-side apply stores in the `kubectl.kubernetes.io/last-applied-configuration` annotation.

*(recall — trigger it)*
```bash
# Try applying without --server-side
kubectl apply -f https://github.com/kedacore/keda/releases/download/v2.14.0/keda-2.14.0.yaml
```
Expected error:
```
The CustomResourceDefinition "scaledobjects.keda.sh" is invalid: 
metadata.annotations: Too long: must have at most 262144 bytes
```
Fix:
```bash
kubectl apply --server-side -f https://github.com/kedacore/keda/releases/download/v2.14.0/keda-2.14.0.yaml
```
`--server-side` moves the "what was last applied" tracking to the server — no annotation size limit.

---

**ScaledObject targeting the wrong Deployment name** *(recognition)*
`scaleTargetRef.name` must exactly match the Deployment name that KEDA will control. If the names diverge (e.g., Deployment is `aois` but scaleTargetRef says `aois-app`), the ScaledObject is created but does nothing — KEDA logs an error internally and `READY` stays `False`.

*(recall — trigger it)*
```bash
# Temporarily set a wrong target name
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml \
  --set "keda.enabled=true" -n aois

# Then manually patch the ScaledObject to a wrong name
kubectl patch scaledobject aois -n aois \
  --type json \
  -p '[{"op": "replace", "path": "/spec/scaleTargetRef/name", "value": "wrong-name"}]'

kubectl get scaledobject -n aois
```
Expected:
```
NAME   SCALETARGETKIND   SCALETARGETNAME   ...  READY    ACTIVE
aois   Deployment        wrong-name             False    False
```
`READY: False` is the indicator. Check the reason:
```bash
kubectl describe scaledobject aois -n aois | grep -A5 "Conditions"
# Message: deployment.apps "wrong-name" not found
```
Fix: restore the correct name (`{{ .Release.Name }}` in the template matches the Deployment name exactly because both use the Helm release name).

---

**Creating an HPA manually alongside KEDA — two controllers fight** *(recognition)*
KEDA creates and owns the HPA for your ScaledObject. If you also create an HPA manually targeting the same Deployment, two controllers compete to set replica counts — the result is unpredictable oscillation.

*(recall — trigger it)*
```bash
# After KEDA ScaledObject is live, manually create a conflicting HPA
kubectl autoscale deployment aois --cpu-percent=80 --min=1 --max=10 -n aois

# Check the HPAs
kubectl get hpa -n aois
```
Expected: two HPAs for the same Deployment. KEDA's HPA and your manual HPA are now fighting.
```bash
kubectl describe hpa -n aois | grep -A3 "ScaleTarget\|Events"
# You will see conflicting scale events
```
Fix: delete the manually created HPA. KEDA's managed HPA is the only one:
```bash
kubectl delete hpa aois -n aois   # delete the manually created one
kubectl get hpa -n aois           # only keda-hpa-aois should remain
```

---

**`minReplicas: 0` with CPU trigger — pods never reach zero** *(recognition)*
Setting `minReplicaCount: 0` with a CPU trigger does not produce scale-to-zero behavior. CPU metrics require at least one running pod to collect. KEDA sees no metric source and keeps the last-known replica count — effectively freezing at 1. This is the CPU scaler's architectural limitation.

*(recall — trigger it)*
```bash
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml \
  --set keda.minReplicas=0 -n aois

# Stop all traffic to AOIS for 10 minutes
# Then check:
kubectl get deployment aois -n aois -o jsonpath='{.spec.replicas}'
# Still 1 — did not reach 0
```
Compare to what happens with an external trigger that has a zero signal (like Kafka with 0 messages). Fix: for v9, keep `minReplicas: 1`. The scale-to-zero pattern comes in v17 when Kafka provides the signal.

---

**ScaledObject not rendered — `keda.enabled` is false in the active values file** *(recognition)*
The ScaledObject template is guarded by `{{- if .Values.keda.enabled }}`. If you deploy with `values.yaml` (default, `enabled: false`) instead of `values.prod.yaml` (`enabled: true`), the ScaledObject is not created — KEDA never activates.

*(recall — trigger it)*
```bash
# Deploy without specifying the prod values file
helm upgrade aois ./charts/aois -n aois    # no -f values.prod.yaml

# Check if ScaledObject was created
kubectl get scaledobject -n aois
```
Expected:
```
No resources found in aois namespace.
```
KEDA is installed and running but has nothing to do — the ScaledObject was not rendered.
```bash
# Verify by checking what helm template produces without -f
helm template aois ./charts/aois | grep -c "ScaledObject"
# 0 — the {{- if .Values.keda.enabled }} guard worked correctly
```
Fix: always specify the values file when upgrading:
```bash
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```
Or — better for production — let ArgoCD manage the upgrade. The ArgoCD Application in `argocd/application.yaml` already specifies `values.prod.yaml`.

---

## Troubleshooting

**`kubectl get scaledobject -n aois` returns "No resources found":**
Either KEDA is not installed, the ScaledObject was not deployed, or it was deployed to the wrong namespace.
```bash
kubectl get crd | grep keda           # CRDs must be present
kubectl get pods -n keda              # KEDA operator must be running
argocd app get aois --show-operation  # check if ArgoCD synced the ScaledObject
```

**ScaledObject shows `READY: False`:**
```bash
kubectl describe scaledobject aois -n aois
```
Look at `Status.Conditions`. Common causes:
- `scaleTargetRef.name` does not match the Deployment name
- KEDA operator is not running
- The Deployment has no `resources.requests.cpu` set — CPU scaler requires a CPU request to calculate utilization percentage

**HPA `TARGETS` shows `<unknown>/60%`:**
The metrics server cannot read CPU for the pods. Verify:
```bash
kubectl top pods -n aois
```
If `kubectl top` also shows `<unknown>` or errors, the metrics-server is not running. k3s includes it by default — if it is missing:
```bash
kubectl get deployment metrics-server -n kube-system
```

**ScaledObject shows `ACTIVE: True` but no extra pods appear:**
KEDA activated scaling but Kubernetes cannot schedule new pods. Check:
```bash
kubectl describe replicaset -n aois | grep -A10 "Events"
# "Insufficient memory" or "Insufficient cpu" means nodes are full
kubectl describe nodes | grep -A5 "Allocated resources"
```
The Hetzner server may not have enough resources for additional AOIS pods. Reduce `resources.requests` or increase the node size.

**After load test ends, pods don't scale down for a long time:**
This is `cooldownPeriod` working correctly. With `cooldownPeriod: 300`, KEDA waits 5 minutes after the trigger drops below threshold before reducing replicas. This prevents flapping. To test faster:
```bash
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml \
  --set keda.cooldownPeriod=30 -n aois   # 30 seconds for testing
# Reset after:
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```

---

## Connection to later phases

- **v17 (Kafka)**: The `triggers` section in the ScaledObject gains a second entry: `type: kafka` with `lagThreshold`. KEDA now evaluates both CPU and Kafka lag — scales to whichever is higher. The rest of the ScaledObject is identical. You are learning the shape now so v17 is a three-line change.
- **v19 (Chaos Engineering)**: Chaos Mesh injects latency and pod failures. KEDA detects the load change and attempts to scale. You will watch what happens to the ScaledObject during a chaos event — does KEDA fight chaos or cooperate with it?
- **v23 (LangGraph)**: Agent nodes generate bursty CPU load — one node spikes during investigation, drops after resolution. KEDA is the right tool here: pods scale up during investigation bursts, back to 1 during idle. The same ScaledObject config handles this with no changes.
- **The pattern**: Every production AI workload has bursty load. KEDA's job is to match infrastructure to that load automatically. The pattern — ScaledObject + trigger + Deployment — is what you use in every phase that handles variable load.

---

## Mastery Checkpoint

**1. Trace KEDA's architecture on your cluster**
After deploying the ScaledObject, run:
```bash
kubectl get scaledobject,hpa,deployment -n aois
```
You will see three resources. The ScaledObject is what you defined. The HPA (`keda-hpa-aois`) was created by KEDA. The Deployment is what both reference. Explain in one sentence the relationship between all three. Then run:
```bash
kubectl describe hpa keda-hpa-aois -n aois | grep -E "ScaleTarget|Min|Max|Metrics|Events" -A2
```
Find the line that shows the current metric value vs the target. What does this number represent?

**2. Trigger a scale event deliberately**
Lower the CPU threshold to 5% and generate a single request. Watch the HPA respond within 30 seconds. Then restore the threshold to 60% and watch it scale back down. Record the exact timestamps. Calculate how long scale-up took (from trigger to new pod Running). Calculate how long scale-down took (from threshold drop to replica reduction). These numbers are your AOIS scaling SLA.

**3. Explain the scale-to-zero boundary**
Without looking at the notes: explain why `minReplicas: 0` does not produce zero pods with the CPU trigger. Then explain what a Kafka trigger provides that makes scale-to-zero possible. If you cannot explain this in two sentences, re-read the "Understanding scale-to-zero" section.

**4. The multi-trigger design**
Add a second trigger to the ScaledObject alongside the CPU trigger:
```yaml
triggers:
  - type: cpu
    metricType: Utilization
    metadata:
      value: "60"
  - type: cron
    timezone: UTC
    metadata:
      start: "0 8 * * 1-5"    # 8am UTC weekdays
      end: "0 18 * * 1-5"     # 6pm UTC weekdays
      desiredReplicas: "3"
```
Deploy it. KEDA now scales AOIS to 3 replicas during business hours regardless of CPU, and uses CPU for reactive scaling otherwise. Watch the behavior. What happens at 8am UTC? What happens at 6pm? This is how production systems handle predictable load patterns alongside reactive load.

**5. Inspect KEDA's internal state**
```bash
kubectl logs -n keda -l app=keda-operator --tail=50 | grep -i "aois\|scaledobject\|scaled"
```
Read what KEDA is doing internally — every polling interval, every scale decision. This is the log that tells you why KEDA did or did not scale. Find the line where KEDA checked the CPU metric and decided to hold at 1 replica. This is the same log you read in v17 when debugging a Kafka scaler that is not triggering.

**6. Cost arithmetic**
With `minReplicas: 1` and `maxReplicas: 5`, what is the difference in monthly Hetzner cost between:
- Always running at 5 replicas (no KEDA)
- KEDA with average utilization at 2 replicas

Look up Hetzner's CPX11 pricing (the node type). Calculate the monthly pod cost at 5 vs 2 replicas. KEDA's value is this difference, compounded across every service in the cluster.

**The mastery bar:** You can describe KEDA's architecture (ScaledObject → KEDA → managed HPA → Deployment), explain why CPU cannot produce scale-to-zero while Kafka can, and deploy a ScaledObject through ArgoCD. You understand what changes in v17 and can make that change without notes.
