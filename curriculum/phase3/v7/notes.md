# v7 — Helm Chart: Packaging AOIS for Any Cluster
⏱ **Estimated time: 2–3 hours**

## Prerequisites

- v6 complete — k3s running on Hetzner, AOIS accessible at `https://aois.46.225.235.51.nip.io`
- Helm CLI installed:
  ```bash
  helm version
  # version.BuildInfo{Version:"v3.xx.x", GitCommit:"...", GitTreeState:"clean", GoVersion:"go1.21.x"}
  ```
  If not installed: `curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash`
- kubeconfig pointing at Hetzner (verified with `kubectl get nodes`)

---

## Learning Goals

By the end of this version you will be able to:
- Explain what Helm solves and why raw YAML breaks at scale
- Read any Helm chart and understand every file's purpose
- Write Go template syntax: value substitution, conditionals, `range` loops
- Render, lint, and dry-run a chart before touching a cluster
- Deploy, upgrade, roll back, and uninstall a release via Helm
- Override values per environment without duplicating templates
- Diagnose and recover from all common Helm failure states
- Explain where Helm stores its release history and how rollback uses it

---

## What This Is

In v6 you deployed AOIS to Hetzner using raw Kubernetes YAML. It works — for one environment, one version, managed by one person. The moment any of those constraints changes, raw YAML breaks down.

Every value in those files is hardcoded: the image tag, the hostname, the replica count, the resource limits, the namespace. To deploy a new version you open `deployment.yaml` and change the tag by hand. To deploy to a second environment you copy the files and change them again. Now you have two sets of YAML and no guarantee they stay in sync.

Helm solves this. It is Kubernetes's package manager — the equivalent of `apt` or `brew` but for deploying applications to clusters. You write templates once. You provide a `values.yaml` for each environment. Helm renders the final YAML for you and tracks what was deployed.

The `charts/aois/` chart you build here is not a throwaway exercise. It will deploy to:
- Hetzner k3s right now (`values.prod.yaml`)
- AWS EKS in v12 (`values.eks.yaml` — different ingress class, different hostname)
- Any cluster you ever work on in the future

One chart. Any cluster. This is the value proposition.

---

## Why Helm Exists: The Problems It Solves

### Problem 1: Environment drift

Without Helm you have `k8s/deployment.yaml`. You copy it to a staging cluster and change a few values. Six months later your dev YAML and staging YAML have diverged — someone changed resources in one but not the other, different image tags, different probe timeouts. You no longer know which is canonical.

With Helm: one `templates/deployment.yaml`. Different values files per environment. The template is the truth. The values file is the configuration. They cannot drift from each other because there is only one template.

### Problem 2: No release history

`kubectl apply` is stateless. After applying, the cluster knows about the Deployment but has no memory of what came before. You cannot ask: "What version was running before this? Who deployed it? What changed?"

Helm tracks every deploy as a numbered revision. `helm history aois` shows every revision with its timestamp. `helm rollback aois 2` re-applies the templates from that revision. This is the same capability that made `git log` + `git revert` indispensable — applied to Kubernetes deployments.

### Problem 3: Upgrades require touching multiple files

To bump the image tag in v6, you edit `k8s/deployment.yaml`. If you also have a Job or a CronJob that uses the same image, you edit those too. You miss one. The wrong version runs somewhere.

With Helm: change `image.tag` in `values.prod.yaml`. Run `helm upgrade`. Every template that references `{{ .Values.image.tag }}` gets the new value simultaneously. One change, consistent everywhere.

### Problem 4: Shareability

A raw YAML directory is tied to your specific cluster. A Helm chart is self-contained and shareable. Anyone can run `helm install aois ./charts/aois -f my-values.yaml` against their own cluster. This is how the Kubernetes ecosystem distributes software — Prometheus, Grafana, cert-manager, ArgoCD itself are all installed via Helm charts.

---

## How Helm Works: Under the Hood

Before looking at files, understand what Helm actually does when you run a command.

### Where Helm stores state

When you run `helm install aois ...`, Helm creates a **release** and stores its state as a Kubernetes Secret in the same namespace. Run this after installing:

```bash
kubectl get secret -n aois | grep helm
# sh.helm.release.v1.aois.v1    helm.sh/release.v1   1   5m
```

That Secret contains the full rendered templates from that revision, base64-encoded. This is how `helm rollback` works — it fetches the old rendered YAML from the Secret and re-applies it. No git, no local files needed — the release history lives inside the cluster.

### What `helm install` does step by step

1. Reads `Chart.yaml` — validates the chart
2. Merges `values.yaml` with any `-f overrides.yaml` and `--set` flags — prod values win
3. Renders every template in `templates/` using the merged values — produces plain YAML
4. Runs `helm lint` internally — validates the rendered YAML
5. Applies the YAML to Kubernetes via the API (same as `kubectl apply`)
6. Stores the rendered output + metadata as a Secret in the cluster (revision 1)
7. Reports: `NAME: aois, STATUS: deployed`

### What `helm upgrade` does differently

`helm upgrade` diffs the new rendered output against the current release's stored YAML. It only applies resources that changed. A Deployment where only the image tag changed will trigger a rolling update. A ConfigMap that didn't change is untouched. This is more efficient than `kubectl apply -f .` which applies everything.

### What `helm rollback` does

Fetches the rendered YAML from the target revision's Secret. Applies it. Creates a new revision (revision N+1) — rollback is not destructive, it is a forward-applied revert. `helm history` will show the rollback as a new entry.

---

## The Chart Structure

```
charts/aois/
├── Chart.yaml              # chart metadata
├── values.yaml             # default values (safe for any environment)
├── values.prod.yaml        # production overrides only
└── templates/
    ├── namespace.yaml      # the aois namespace
    ├── deployment.yaml     # the AOIS Deployment
    ├── service.yaml        # ClusterIP Service
    └── ingress.yaml        # Ingress (conditional)
```

No `_helpers.tpl` yet — that comes when the chart grows complex enough to need shared template fragments. For now, four templates is the right size.

---

## Chart.yaml: What Each Field Means

```yaml
apiVersion: v2
name: aois
description: AI Operations Intelligence System
type: application
version: 0.7.0
appVersion: "v7"
```

**`apiVersion: v2`** — Helm 3 format. Helm 2 is dead (removed its Tiller server, a major security hole), but you will still see `v1` charts in the wild. They still work in Helm 3.

**`version: 0.7.0`** — the chart's own version. Increment this when the chart structure changes (new template, new value, changed default). This is independent of what the chart deploys.

**`appVersion: "v7"`** — the version of the application inside the chart. This is informational — shown in `helm list`. It does not have to match the Docker image tag, but by convention it should.

The separation matters: you can release chart version `0.7.1` (fixed a template bug) that still deploys appVersion `v7`. Or you can bump appVersion to `v8` without changing the chart structure. They track different things.

---

## values.yaml: The Contract

`values.yaml` is the public interface of your chart. Every value a user might need to change should be here with a sensible default.

```yaml
replicaCount: 1

image:
  repository: ghcr.io/kolinzking/aois
  tag: v7
  pullPolicy: IfNotPresent

imagePullSecrets:
  - name: ghcr-secret

namespace: aois

service:
  port: 80
  targetPort: 8000

ingress:
  enabled: true
  className: traefik
  host: aois.46.225.235.51.nip.io
  clusterIssuer: letsencrypt-prod
  tlsSecretName: aois-tls

resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"

probes:
  liveness:
    path: /health
    initialDelaySeconds: 15
    periodSeconds: 20
  readiness:
    path: /health
    initialDelaySeconds: 5
    periodSeconds: 10

secretName: aois-secrets
```

Design principle: the defaults in `values.yaml` should be safe for a development environment — low resource requests, 1 replica, sensible timeouts. Production overrides live in `values.prod.yaml`. This way `helm install aois ./charts/aois` (no values file) works without accidentally deploying a 10-replica prod-sized deployment to a dev cluster.

---

## Go Template Syntax: What You're Actually Writing

The templates use Go's `text/template` package with Helm's extensions. You need to understand the syntax to write and debug templates.

### Basic substitution

```yaml
image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
```

`.Values` is the merged values object. `.Values.image.repository` navigates the YAML hierarchy. The result is a string substituted in place.

### The dot (`.`) — current context

`.Values` is available because `.` is the current context — at the top level of a template, `.` is the root data structure, which has `.Values`, `.Release`, `.Chart`, and `.Files` as top-level keys.

Inside a `range` block, `.` becomes the current iteration item (covered below). This is the most common source of confusion in Helm templates.

### `.Release` — built-in metadata

```yaml
name: {{ .Release.Name }}       # the name given at helm install time
namespace: {{ .Release.Namespace }}
```

`.Release.Name` is why the templates use `{{ .Release.Name }}` instead of hardcoding `"aois"`. If someone installs the chart as `helm install my-aois ./charts/aois`, all resources get named `my-aois`. One chart can be installed multiple times in the same cluster under different release names.

### `.Chart` — chart metadata

```yaml
# reference chart version in a label
chart: {{ .Chart.Name }}-{{ .Chart.Version }}
```

Rarely needed in templates but useful for adding standard labels.

### Conditionals: `{{- if }}`

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
...
{{- end }}
```

If `ingress.enabled` is `false`, the entire Ingress resource is omitted from the rendered output — no resource is created. The same chart works for clusters without an Ingress controller (set `ingress.enabled: false` in values).

**The `{{-` (dash)**: strips whitespace/newlines before the tag. `{{ if }}` leaves a blank line in the output. `{{- if }}` removes it. For valid YAML, use `{{-` to avoid extra blank lines that can confuse parsers.

### Loops: `{{- range }}`

```yaml
imagePullSecrets:
{{- range .Values.imagePullSecrets }}
- name: {{ .name }}
{{- end }}
```

`.Values.imagePullSecrets` is a list. `range` iterates it. Inside the range block, `.` becomes the current list item — so `.name` refers to the `name` key of each item.

This is why `.Values.imagePullSecrets` is defined as a list of objects (`- name: ghcr-secret`) rather than a list of strings — so each item has a `.name` field.

### Default values in templates

```yaml
replicas: {{ .Values.replicaCount | default 1 }}
```

The `| default` pipe applies a fallback if the value is empty or nil. Useful for optional values that might not be set. Not needed for required values that should fail loudly if missing.

---

## The Four Templates: What Each Does

### templates/namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: {{ .Values.namespace }}
```

Simple. Creates the `aois` namespace. The value comes from `values.yaml`. This means the same chart can deploy to a different namespace just by changing one value — useful for multi-tenant clusters.

### templates/deployment.yaml

The most complex template. Every configurable aspect of the Deployment is a value reference:

```yaml
spec:
  replicas: {{ .Values.replicaCount }}
  ...
  containers:
  - name: {{ .Release.Name }}
    image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
    imagePullPolicy: {{ .Values.image.pullPolicy }}
    ...
    resources:
      requests:
        memory: {{ .Values.resources.requests.memory }}
        cpu: {{ .Values.resources.requests.cpu }}
      limits:
        memory: {{ .Values.resources.limits.memory }}
        cpu: {{ .Values.resources.limits.cpu }}
    livenessProbe:
      httpGet:
        path: {{ .Values.probes.liveness.path }}
        port: {{ .Values.service.targetPort }}
      initialDelaySeconds: {{ .Values.probes.liveness.initialDelaySeconds }}
      periodSeconds: {{ .Values.probes.liveness.periodSeconds }}
```

The probe path and port are values — in v9 when KEDA changes the way AOIS starts up, you can tune the probe timing without editing the template.

### templates/service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}
  namespace: {{ .Values.namespace }}
spec:
  selector:
    app: {{ .Release.Name }}
  ports:
  - port: {{ .Values.service.port }}
    targetPort: {{ .Values.service.targetPort }}
```

Note the `selector: app: {{ .Release.Name }}`. The Deployment labels its pods `app: aois` (using `.Release.Name`). The Service selects pods with the same label. Both use `.Release.Name` — they stay in sync automatically regardless of what name you install the chart with.

### templates/ingress.yaml

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .Release.Name }}
  namespace: {{ .Values.namespace }}
  annotations:
    cert-manager.io/cluster-issuer: {{ .Values.ingress.clusterIssuer }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  tls:
  - hosts:
    - {{ .Values.ingress.host }}
    secretName: {{ .Values.ingress.tlsSecretName }}
  rules:
  - host: {{ .Values.ingress.host }}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {{ .Release.Name }}
            port:
              number: {{ .Values.service.port }}
{{- end }}
```

The `clusterIssuer` annotation drives cert-manager. When you deploy to EKS in v12, you will set `ingress.className: alb` and remove the cert-manager annotation — a completely different ingress setup, same template.

---

## values.prod.yaml: The Override Pattern

`values.prod.yaml` contains **only the keys that differ from defaults**. Everything else falls through from `values.yaml`. Helm deep-merges them, with the override file winning on any conflict.

```yaml
replicaCount: 2

image:
  tag: v7

ingress:
  host: aois.46.225.235.51.nip.io

resources:
  requests:
    memory: "512Mi"
    cpu: "200m"
  limits:
    memory: "1Gi"
    cpu: "1000m"
```

This file is small on purpose. The smaller the override file, the clearer what is different in production. A 200-line override file that copies most of `values.yaml` is a sign the defaults are wrong.

**Important**: when Helm merges two YAML files, it merges at the key level. If you only set `image.tag` in the override, `image.repository` and `image.pullPolicy` still come from `values.yaml`. You do not need to repeat the entire `image:` block — only the keys you want to change.

**Future override files:**
- `values.eks.yaml` (v12): `ingress.className: alb`, EKS-specific hostname
- `values.local.yaml`: `ingress.enabled: false`, `replicaCount: 1`, minimal resources

---

## Helm Commands: The Full Reference

### Before touching a cluster

```bash
# Render the chart — see exactly what would be applied
helm template aois ./charts/aois
helm template aois ./charts/aois -f charts/aois/values.prod.yaml

# Syntax check — catches template errors before runtime
helm lint ./charts/aois

# Dry run — sends to Kubernetes API for validation but does not apply
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois --dry-run
```

Run these in order before any real deploy. `helm template` catches your errors. `helm lint` catches structural issues. `--dry-run` catches Kubernetes validation errors (invalid field values, missing required fields).

### Installing for the first time

```bash
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```

`install` fails if the release already exists. Use `upgrade --install` for idempotent behavior (installs if new, upgrades if exists):

```bash
helm upgrade --install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```

This is what CI pipelines use — they don't know or care if it's a first install or an upgrade.

### Deploying a new version

```bash
# Bump the tag in values.prod.yaml, then:
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois

# Or override the tag inline without editing the file:
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois --set image.tag=v8
```

`--set` is useful in CI scripts where the image tag is a variable: `--set image.tag=$CI_COMMIT_SHA`.

### Inspecting a release

```bash
# List all releases in a namespace
helm list -n aois

# Detailed status of one release
helm status aois -n aois

# Full history of revisions
helm history aois -n aois

# See the values that are currently deployed
helm get values aois -n aois

# See the fully rendered YAML that is currently deployed
helm get manifest aois -n aois
```

`helm get manifest` is the most useful debugging command. It shows you exactly what Helm applied — the rendered templates with all values substituted. Compare this against what `kubectl get -o yaml` shows to diagnose drift.

### Rolling back

```bash
# See the history first
helm history aois -n aois
# REVISION  UPDATED                   STATUS      CHART        APP VERSION  DESCRIPTION
# 1         2026-04-18 10:00:00 UTC   superseded  aois-0.7.0   v7           Install complete
# 2         2026-04-18 11:30:00 UTC   deployed    aois-0.7.0   v8           Upgrade complete

# Roll back to revision 1
helm rollback aois 1 -n aois

# History after rollback:
# REVISION  STATUS      DESCRIPTION
# 1         superseded  Install complete
# 2         superseded  Upgrade complete
# 3         deployed    Rollback to 1    ← new revision, re-applied revision 1's templates
```

Rollback creates a new revision. It does not delete or overwrite the history.

### Uninstalling

```bash
helm uninstall aois -n aois
```

Removes all resources created by the chart. The Namespace stays — Helm does not delete namespaces because other resources may live there (Secrets, cert-manager certificates, etc.). Delete the namespace manually if you want a clean slate.

---

## Deploying v7 to Hetzner

The cluster from v6 has AOIS resources already applied via `kubectl apply`. Helm cannot manage resources it did not create. Before installing via Helm, remove the kubectl-managed resources:

```bash
# On the Hetzner server (or with your kubeconfig pointing at it)
kubectl delete deployment aois -n aois
kubectl delete service aois -n aois
kubectl delete ingress aois -n aois

# Do NOT delete — these were not created by the v6 manifests we're replacing:
# - namespace (aois) — keep it
# - secret aois-secrets — keep it (API keys live here)
# - secret ghcr-secret — keep it (image pull credentials)
# - cert-manager resources — keep them (ClusterIssuer, certificates)
# - the existing TLS secret (aois-tls) — keep it (cert is already issued)

# Now install via Helm
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois

# Watch the pods come up
kubectl get pods -n aois -w
```

After `helm install`, confirm with:
```bash
helm list -n aois
# NAME   NAMESPACE  REVISION  STATUS    CHART        APP VERSION
# aois   aois       1         deployed  aois-0.7.0   v7

curl https://aois.46.225.235.51.nip.io/health
# {"status":"healthy"}
```

From this point on, never use `kubectl apply` to manage AOIS. Helm owns the release. Mixing `kubectl apply` and `helm upgrade` causes state corruption — Helm will not know about manually-applied changes.

---

## What `helm template` Output Tells You

Running `helm template` before deploying is not optional — it is the habit that prevents incidents. Read the output like a pre-flight checklist:

```bash
helm template aois ./charts/aois -f charts/aois/values.prod.yaml
```

Look for:
- **Image**: `image: ghcr.io/kolinzking/aois:v7` — is this the tag you intend?
- **Replicas**: `replicas: 2` — does this match `values.prod.yaml`?
- **Resources**: memory limits and requests — did the prod override apply?
- **Host**: `host: aois.46.225.235.51.nip.io` — does this match the actual cluster?
- **Namespace**: every resource should be in `aois`
- **Labels/Selectors**: `app: aois` — do the Deployment labels match the Service selector?

A mismatch here means a broken deploy. Catching it in `helm template` costs nothing. Catching it in production costs an incident.

---

> **▶ STOP — do this now**
>
> Run the template and trace one value all the way through:
> ```bash
> helm template aois ./charts/aois -f charts/aois/values.prod.yaml | grep -A2 "resources:"
> ```
> Expected output:
> ```yaml
>         resources:
>           requests:
>             memory: 512Mi
>             cpu: 200m
>           limits:
>             memory: 1Gi
>             cpu: 1000m
> ```
>
> Now run without the prod overlay:
> ```bash
> helm template aois ./charts/aois | grep -A2 "resources:"
> ```
> Expected output:
> ```yaml
>         resources:
>           requests:
>             memory: 256Mi
>             cpu: 100m
>           limits:
>             memory: 512Mi
>             cpu: 500m
> ```
>
> If your output differs, check: did you save both values files? Does `values.prod.yaml` have `resources.requests.memory: "512Mi"`? The quotes matter for YAML parsing — but Helm strips them in the rendered output.
>
> This is Helm's merge in action. `values.prod.yaml` wins on the keys it defines. Everything else falls through from `values.yaml`.

---

> **▶ STOP — do this now**
>
> Add a new value to the chart without breaking anything:
>
> 1. Add to `values.yaml`:
> ```yaml
> environment: dev
> ```
>
> 2. Add to `values.prod.yaml`:
> ```yaml
> environment: prod
> ```
>
> 3. Add to `templates/deployment.yaml` in the container spec:
> ```yaml
> env:
> - name: ENVIRONMENT
>   value: {{ .Values.environment }}
> ```
>
> 4. Verify:
> ```bash
> helm template aois ./charts/aois | grep ENVIRONMENT
> # value: dev
>
> helm template aois ./charts/aois -f charts/aois/values.prod.yaml | grep ENVIRONMENT
> # value: prod
> ```
>
> You just extended the chart contract. Any operator can now configure `environment` without editing a template.

---

> **▶ STOP — do this now**
>
> Run `helm lint ./charts/aois`. Expected output:
> ```
> ==> Linting ./charts/aois
> [INFO] Chart.yaml: icon is recommended
>
> 1 chart(s) linted, 0 chart(s) failed
> ```
> The INFO about `icon` is harmless — icons are for public chart repositories. 0 failures is what matters.
>
> Now deliberately break a template — open `templates/deployment.yaml` and remove the closing `}}` from `{{ .Values.replicaCount }}` so it becomes `{{ .Values.replicaCount }`. Run lint:
> ```bash
> helm lint ./charts/aois
> ```
> Expected:
> ```
> ==> Linting ./charts/aois
> [ERROR] templates/deployment.yaml: parse error at (aois/templates/deployment.yaml:8): unexpected "}" in operand
>
> Error: 1 chart(s) linted, 1 chart(s) failed
> ```
> Fix it and confirm lint passes again. Lint catches syntax errors before they reach the cluster — run it before every deploy.

---

## Common Mistakes

**Mixing `kubectl apply` and `helm upgrade` on the same resources** *(recognition)*
After `helm install`, Helm owns those resources and tracks state in a cluster Secret. If you then run `kubectl apply -f k8s/deployment.yaml` on the same Deployment, Helm's stored state no longer matches the cluster. The next `helm upgrade` will fight the manually-applied change.

*(recall — trigger it)*
```bash
# After helm install, manually apply the old k8s manifest
kubectl apply -f k8s/deployment.yaml -n aois

# Now try helm upgrade
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```
Expected: Helm either silently overwrites your manual change or throws a conflict error depending on the field. Run `helm status aois -n aois` and `kubectl get deployment aois -n aois -o yaml | grep -A2 managedFields` to see the fighting ownership annotations.

Fix: once Helm is installed, never touch those resources with kubectl. If you made manual changes, reconcile them: delete the kubectl-applied resources and re-run `helm upgrade`, or `helm uninstall` and start fresh.

---

**Wrong `--set` syntax for nested values** *(recognition)*
```bash
# Wrong — this is shell syntax, not Helm syntax
helm upgrade aois ./charts/aois --set image: {tag: v8}

# Correct — use dot notation for nested keys
helm upgrade aois ./charts/aois --set image.tag=v8
```
`--set` uses dot-separated paths. Always verify with `helm get values aois -n aois` after upgrading to confirm the value took effect.

*(recall — trigger it)*
```bash
# Wrong — shell-style syntax
helm upgrade aois ./charts/aois --set "image: {tag: v8}" -n aois
```
Expected:
```
Error: failed parsing --set data: key "image: {tag: v8}" has no value
```
Or worse — it parses but does nothing meaningful. Now try the correct form:
```bash
helm upgrade aois ./charts/aois --set image.tag=v8 -n aois
```
Verify it took effect:
```bash
helm get values aois -n aois | grep tag
# tag: v8
```
Rule: `--set` takes `key.nested_key=value`. No spaces around `=`, no YAML braces, dot-notation for nesting.

---

**Forgetting `-n namespace` on every Helm command** *(recognition)*
`helm list` without `-n aois` shows releases in the `default` namespace. Your AOIS release is in `aois`. Running `helm upgrade aois` without `-n aois` will either fail ("release not found") or upgrade the wrong release if one named `aois` happens to exist in `default`. Always include `-n aois` in every Helm command.

*(recall — trigger it)*
```bash
helm list            # no -n flag
```
Expected:
```
NAME    NAMESPACE    REVISION    ...
# empty — your release is not in 'default'
```
Compare:
```bash
helm list -n aois
# NAME    NAMESPACE    REVISION    STATUS      CHART          APP VERSION
# aois    aois         1           deployed    aois-0.7.0     v7
```
Fix: always include `-n aois` in every Helm command. Set an alias if you find yourself forgetting:
```bash
alias h='helm -n aois'
h list        # now works without -n
```

---

**`helm upgrade` when the release doesn't exist yet** *(recognition)*
`helm upgrade` requires the release to already exist. On first deploy, it fails with "release not found." `helm install` is for first deploy; `helm upgrade` is for subsequent ones. For CI, use `--install` to handle both cases.

*(recall — trigger it)*
```bash
# Uninstall to simulate a fresh cluster
helm uninstall aois -n aois

# Now try upgrade instead of install
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```
Expected:
```
Error: UPGRADE FAILED: release: not found
```
Fix:
```bash
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
# or for idempotent CI/CD:
helm upgrade --install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```
`--install` installs on first run, upgrades on subsequent runs. This is the pattern to use in GitHub Actions.

---

**Typo in values key silently ignored** *(recognition)*
If you write `replicasCount: 2` instead of `replicaCount: 2` in `values.prod.yaml`, Helm does not error. It creates a new key `replicasCount` (unused), and the default `replicaCount: 1` from `values.yaml` is used silently. You deploy thinking you have 2 replicas and you have 1.

*(recall — trigger it)*
```bash
# Add a typo to values.prod.yaml
echo "replicasCount: 3" >> charts/aois/values.prod.yaml   # typo: replicasCount

helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois

# Check actual replicas
kubectl get deployment aois -n aois
```
Expected: DESIRED shows 1 (default from values.yaml), not 3. Helm silently used the default.

Diagnose with:
```bash
helm template aois ./charts/aois -f charts/aois/values.prod.yaml | grep replicas
# replicas: 1    -- the template rendered with the default
helm get values aois -n aois
# replicasCount: 3    -- typo key is stored, but unused
```
Fix: check `helm template` output before every deploy. Remove the typo from `values.prod.yaml`.

---

**Editing secrets in-place before `helm install`** *(recognition)*
The `aois-secrets` Secret in the cluster was created with `kubectl create secret`. Helm does not manage it — it was created outside the chart. Do not add the Secret to the chart without planning the migration. Adding it to the chart and running `helm install` will fail with "resource already exists." Either keep it external (current approach) or delete the existing Secret and let Helm create it.

*(recall — trigger it)*
```bash
# Try adding the Secret to the Helm chart and installing
# First: copy the secret manifest into charts/aois/templates/secret.yaml
# Then attempt install:
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```
Expected:
```
Error: rendered manifests contain a resource that already exists in the cluster
Secret "aois-secrets" in namespace "aois" exists and cannot be imported into the current release
```
Helm refuses because the Secret was not created by this Helm release and has no `helm.sh/chart` annotation. Fix option 1 — keep it external (recommended for secrets):
```bash
# Remove secret.yaml from the chart — keep using kubectl for secrets
rm charts/aois/templates/secret.yaml
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```
Fix option 2 — adopt the secret into Helm:
```bash
# Delete the kubectl-created secret, let Helm recreate it
kubectl delete secret aois-secrets -n aois
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```
The difference matters: option 1 means the secret lives outside GitOps (good for secrets). Option 2 means the secret value must be in `values.yaml` or passed via `--set` (risky — values files may be committed to git).

---

## Troubleshooting

**`Error: release aois already exists`**
You ran `helm install` when the release already exists. Use `helm upgrade` or `helm upgrade --install`.

**`Error: rendered manifests contain a resource that already exists`**
Resources exist in the cluster that were not created by Helm (e.g., the kubectl-applied resources from v6). Solution: delete the orphaned resources first, then install.

**`Error: INSTALLATION FAILED: cannot re-use a name that is still in use`**
A previous install failed midway. The release is in a failed state. Run:
```bash
helm list -n aois -a   # -a shows failed releases too
helm uninstall aois -n aois
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```

**Values not appearing as expected in rendered output**
Run `helm template` and inspect. Then run `helm get values aois -n aois` to see what values Helm actually deployed with. Compare the two. A common mistake: the override file has a typo in a key name (e.g., `replicasCount` instead of `replicaCount`) — the key is silently ignored and the default is used.

**Pod is up but shows wrong image tag**
Run `helm get manifest aois -n aois | grep image:`. If the tag is wrong there, the values file had the wrong value. If the tag is right there but the pod shows something different, the pod was not restarted — run `kubectl rollout restart deployment aois -n aois`.

**Helm rollback did not change anything**
The revision you rolled back to may have the same template output as the current revision. Run `helm get manifest aois -n aois --revision 1` and compare. If they're identical, the rollback applied but nothing changed in Kubernetes because nothing was different.

---

## How v7 Connects to What Comes Next

**v8 (ArgoCD)**: ArgoCD is Helm-aware. When you point ArgoCD at `charts/aois` with `values.prod.yaml`, it runs `helm template` internally and applies the output. You do not run `helm upgrade` anymore — ArgoCD does it for you when git changes.

**v9 (KEDA)**: You will add a `ScaledObject` resource to the chart. One new template file, a few new values. The chart handles it naturally.

**v12 (EKS)**: Add `values.eks.yaml`. The same chart deploys to a completely different cluster. This is the moment the investment in Helm pays off — you don't rewrite anything.

The chart you built in v7 is production infrastructure. It will carry AOIS forward for the rest of the curriculum.

---

## Mastery Checkpoint

**1. Explain Helm's three core problems solved**
Without notes: name the three problems Helm solves for raw kubectl-apply workflows. (Environment drift, no release history, multi-file version bumps.) If you cannot name them, the "Why Helm Exists" section is worth re-reading.

**2. Trace Helm's storage**
After `helm install`, where does Helm store the release state? (As a Secret in the cluster namespace.) Run:
```bash
kubectl get secret -n aois | grep helm
kubectl get secret sh.helm.release.v1.aois.v1 -n aois -o jsonpath='{.data.release}' | base64 -d | base64 -d | gunzip | python3 -m json.tool | head -30
```
You should see the rendered manifest and release metadata stored inside the cluster itself.

**3. Explain `.Release.Name` vs hardcoding**
Why does the Deployment template use `{{ .Release.Name }}` for the container name and pod labels instead of hardcoding `"aois"`? What would break if someone installed the chart as `helm install aois-staging ./charts/aois`? (Resource names and labels would not match the release name — the Service selector would target `app: aois` but pods would be labeled `app: aois-staging`. Traffic breaks.)

Actually verify this with helm template:
```bash
helm template aois-staging ./charts/aois | grep -E "name:|app:"
```
Confirm that every `aois` reference becomes `aois-staging`.

**4. The merge test**
In `values.yaml`, `ingress.className` is `traefik`. Create a new file `values.local.yaml`:
```yaml
ingress:
  enabled: false
```
Run:
```bash
helm template aois ./charts/aois -f charts/aois/values.local.yaml | grep -i ingress
```
Confirm no Ingress resource appears. This is the same override pattern you will use for EKS in v12.

**5. Understand helm history and rollback**
Do three helm upgrades (changing `replicaCount` each time: 1, 2, 3). Then:
```bash
helm history aois -n aois
helm rollback aois 1 -n aois
kubectl get deployment aois -n aois -o jsonpath='{.spec.replicas}'
```
Confirm the replica count reverted to 1. Then check `helm history` again and note that rollback created a new revision (4), not deleted revisions 2 and 3.

**6. The corrupted release recovery**
Simulate a failed install by applying a broken manifest manually:
```bash
kubectl run broken-pod --image=doesnotexist -n aois
helm install aois ./charts/aois -n aois  # will fail — release exists? Try it
```
Practice diagnosing and recovering from common Helm error states using the troubleshooting section.

**7. Read `helm get manifest` and compare to `kubectl`**
```bash
helm get manifest aois -n aois > /tmp/helm-manifest.yaml
kubectl get deployment aois -n aois -o yaml > /tmp/kubectl-manifest.yaml
diff /tmp/helm-manifest.yaml /tmp/kubectl-manifest.yaml
```
The kubectl output will have many additional fields (status, resourceVersion, annotations added by Kubernetes). These are fields Kubernetes added after Helm applied the manifest. This is why Helm stores its own copy — it needs to diff against what it originally applied, not what Kubernetes has mutated since.

**The mastery bar**: You understand why Helm exists, know where it stores state, can trace any value from `values.yaml` through the template to rendered output, can diagnose and recover from common error states, and understand how the chart will extend as AOIS grows. When someone says "bump the chart version" or "the Helm release is in a failed state," you know exactly what to do.
