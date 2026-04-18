# v7 — Helm Chart: Packaging AOIS for Any Cluster

## What This Is

In v6 you deployed AOIS to Hetzner using raw Kubernetes YAML. It works. But every value — the image tag, the hostname, the replica count, the resource limits — is hardcoded in those files. Change one thing and you're editing YAML by hand. Deploy to a second environment and you're copying files and editing them again.

Helm solves this. It is Kubernetes's package manager. You write templates once, then provide a `values.yaml` for each environment. The chart renders the final YAML for you.

The same `charts/aois/` directory you build here will deploy to:
- Hetzner k3s (now, with `values.prod.yaml`)
- AWS EKS (v12, with `values.eks.yaml`)
- Local kind/minikube (with `values.local.yaml`)

One chart. Any cluster.

---

## Why Helm Exists

Without Helm, you have a directory of YAML files with hardcoded values. This creates three problems:

**Problem 1: Environment drift.** Your dev YAML and prod YAML diverge. You change replicas in prod and forget to update dev. Now you don't know which is canonical.

**Problem 2: Upgrades are error-prone.** To update the image tag you grep through multiple files. You miss one. The wrong version runs in production.

**Problem 3: No release history.** kubectl apply is stateless. You cannot ask "what version is running?" or "what changed in the last deploy?" or "how do I roll back?"

Helm fixes all three:
- **Values file** = single source of truth per environment
- **`helm upgrade`** = one command, one version bump
- **Release history** = `helm history aois`, `helm rollback aois 2`

---

## Helm Concepts

### The Three Parts of a Chart

```
charts/aois/
├── Chart.yaml          # metadata: name, version, appVersion
├── values.yaml         # default values (dev-safe defaults)
├── values.prod.yaml    # prod overrides (higher resources, prod hostname)
└── templates/          # Go template files that render to k8s YAML
    ├── namespace.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── ingress.yaml
```

### Chart.yaml

```yaml
apiVersion: v2
name: aois
description: AI Operations Intelligence System
type: application
version: 0.7.0      # chart version — increment when the chart changes
appVersion: "v7"    # the application version — what's running inside
```

`version` is the chart itself. `appVersion` is what the chart deploys. These are independent. You can release chart version 0.7.1 (a bug fix in the template) that still deploys appVersion v7.

### values.yaml

This is the contract the chart exposes to the operator. Every hardcoded value in v6's YAML becomes a key here:

```yaml
replicaCount: 1

image:
  repository: ghcr.io/kolinzking/aois
  tag: v7
  pullPolicy: IfNotPresent

ingress:
  host: aois.46.225.235.51.nip.io
  clusterIssuer: letsencrypt-prod

resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

`values.yaml` contains safe defaults. `values.prod.yaml` contains only the keys that differ in production — everything else falls through to the defaults.

### Templates

Templates are YAML files with Go template syntax. Helm renders them by substituting values:

```yaml
# templates/deployment.yaml
image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
replicas: {{ .Values.replicaCount }}
```

`.Values` references `values.yaml`. `.Release.Name` is the name you give the release at install time (`helm install aois ...` → `.Release.Name` = `"aois"`).

---

## What Changed from v6

In v6, `k8s/deployment.yaml` had:
```yaml
image: ghcr.io/kolinzking/aois:v6
replicas: 1
memory: "256Mi"
```

In v7, `charts/aois/templates/deployment.yaml` has:
```yaml
image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
replicas: {{ .Values.replicaCount }}
memory: {{ .Values.resources.requests.memory }}
```

The YAML structure is identical. Only the static values became template variables. This is the full extent of what Helm templating does — it is not magic, it is substitution.

---

## The File Structure Built

```
charts/aois/
├── Chart.yaml
├── values.yaml          # defaults (1 replica, dev resources)
├── values.prod.yaml     # prod overrides (2 replicas, higher limits)
└── templates/
    ├── namespace.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── ingress.yaml     # wrapped in {{- if .Values.ingress.enabled }}
```

### The Ingress Conditional

```yaml
{{- if .Values.ingress.enabled }}
...ingress spec...
{{- end }}
```

If you set `ingress.enabled: false` in a local dev values file, no Ingress resource is created. The same chart works for a cluster without an Ingress controller.

---

## Helm Commands

### Validate without deploying

```bash
# Render the chart to YAML — check what would be applied
helm template aois ./charts/aois

# With prod overrides
helm template aois ./charts/aois -f charts/aois/values.prod.yaml

# Check for syntax errors (doesn't hit the cluster)
helm lint ./charts/aois
```

`helm template` is your most important debugging tool. Before any deploy, render and read the output. Confirm the values substituted correctly.

### Install

```bash
# First deploy (namespace already exists from v6)
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois
```

### Upgrade (subsequent deploys)

```bash
# Bump image tag and redeploy
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois --set image.tag=v8
```

`--set` overrides a single value inline. Useful for CI where the image tag is a variable.

### Check what's running

```bash
helm list -n aois
helm status aois -n aois
helm history aois -n aois
```

`helm history` shows every revision — what was deployed and when.

### Rollback

```bash
helm rollback aois 1 -n aois
```

Rolls back to revision 1. Kubernetes applies the previous templates. The old pods come up, the new ones are terminated. This is one command vs. multiple kubectl apply operations.

### Uninstall

```bash
helm uninstall aois -n aois
```

Removes everything the chart created. The Namespace is preserved because you may have other resources there.

---

## Rendering What You See

Run this now and read the output:

```bash
helm template aois ./charts/aois -f charts/aois/values.prod.yaml
```

You should see:
- `replicas: 2` (prod override)
- `image: ghcr.io/kolinzking/aois:v7`
- `memory: 512Mi` requests, `1Gi` limits (prod override)
- `host: aois.46.225.235.51.nip.io`

This is exactly what gets sent to the Kubernetes API when you run `helm install` or `helm upgrade`. There is no hidden transformation. What you see in `helm template` is what Kubernetes receives.

---

## values.prod.yaml: The Override Pattern

```yaml
# values.prod.yaml — only what differs from defaults
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

Everything not in `values.prod.yaml` comes from `values.yaml`. This is Helm's merge behavior: prod values take precedence, defaults fill the rest.

In v12 (EKS), you will add `values.eks.yaml`:
```yaml
ingress:
  className: alb          # AWS Load Balancer Controller instead of Traefik
  host: aois.yourdomain.com
image:
  tag: v12
```

Same chart. Different ingress class. Different hostname. Everything else inherits from `values.yaml`.

---

## Deploying v7 to Hetzner

The cluster from v6 is still running. The AOIS deployment, service, and ingress already exist (applied with `kubectl apply`). Before installing via Helm, you need to delete the existing resources so Helm can take ownership:

```bash
# On the Hetzner server — delete what kubectl applied
kubectl delete deployment aois -n aois
kubectl delete service aois -n aois
kubectl delete ingress aois -n aois
# Do NOT delete: namespace, secret (aois-secrets), ghcr-secret, cert-manager resources

# Then install via Helm (from your local machine with kubeconfig set)
helm install aois ./charts/aois -f charts/aois/values.prod.yaml -n aois

# Watch the rollout
kubectl get pods -n aois -w
```

After `helm install`, the release is tracked. Future updates use `helm upgrade`.

---

> **▶ STOP — do this now**
>
> Before deploying, understand what you're about to send to Kubernetes:
> ```bash
> helm template aois ./charts/aois -f charts/aois/values.prod.yaml > /tmp/rendered.yaml
> cat /tmp/rendered.yaml
> ```
> Read every line. Confirm:
> - The image tag matches what you expect
> - The host matches your Hetzner IP
> - Resources are what you set in values.prod.yaml
>
> This is the habit that prevents "I applied the wrong values" incidents.

---

> **▶ STOP — do this now**
>
> Run `helm lint ./charts/aois` and confirm it reports no errors. Lint checks:
> - Required fields in Chart.yaml are present
> - Template syntax is valid
> - Values referenced in templates exist in values.yaml
>
> If lint passes, the chart is structurally sound.

---

## What helm upgrade Looks Like in Practice

Once Helm owns the release, every future deploy is one command:

```bash
# New image version
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois --set image.tag=v8

# Scale up
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois --set replicaCount=3

# View the history after a few upgrades
helm history aois -n aois
# REVISION  UPDATED                   STATUS     CHART       APP VERSION
# 1         2026-04-18 09:30:00 UTC   superseded aois-0.7.0  v7
# 2         2026-04-18 10:15:00 UTC   deployed   aois-0.7.0  v7
```

In v8 (ArgoCD), you will stop running `helm upgrade` by hand entirely. ArgoCD watches the git repo and runs it for you when values.prod.yaml changes. But the Helm chart is the same — ArgoCD is just the automation layer on top.

---

## Mastery Checkpoint

**1. Explain Helm's purpose in one sentence**
Without referencing documentation, explain to someone unfamiliar with Helm why it exists. If you cannot do this without the notes, re-read the "Why Helm Exists" section.

**2. Trace a value from values.yaml to rendered YAML**
Pick any value from `values.prod.yaml` — say `replicaCount: 2`. Trace it:
- Where is it defined? (`values.prod.yaml`)
- Where does the template reference it? (`templates/deployment.yaml`, `{{ .Values.replicaCount }}`)
- What does the rendered output look like? (`replicas: 2` in the Deployment spec)

Run `helm template aois ./charts/aois -f charts/aois/values.prod.yaml | grep replicas` to confirm.

**3. Add a new value without breaking the chart**
Add an `environment` key to `values.yaml` with default `"dev"`. Add it to `values.prod.yaml` as `"prod"`. Reference it in `deployment.yaml` as an environment variable in the container spec:
```yaml
env:
- name: ENVIRONMENT
  value: {{ .Values.environment }}
```
Run `helm template` and confirm the env var appears with `"prod"` when using the prod values file.

**4. Understand the override merge**
In `values.yaml`, `resources.requests.memory` is `256Mi`. In `values.prod.yaml` it is `512Mi`.
- Run `helm template aois ./charts/aois` — what memory value appears?
- Run `helm template aois ./charts/aois -f charts/aois/values.prod.yaml` — what value appears now?
- Why? (Prod values override defaults; unspecified keys fall through)

**5. Understand helm list vs kubectl get**
After deploying with Helm, run both:
```bash
helm list -n aois
kubectl get deployment -n aois
```
Both show AOIS running. What does `helm list` show that `kubectl get` cannot? (Release name, chart version, revision number, last deploy time — Helm's release metadata, not Kubernetes object state)

**6. Rollback understanding**
You deploy v8 and it has a bug. Run:
```bash
helm history aois -n aois
helm rollback aois 1 -n aois
```
What does Kubernetes do when Helm rolls back? (Re-applies the templates from revision 1 — Kubernetes performs a rolling update back to the previous pod spec. Old pods terminate, previous-version pods come up.)

**The mastery bar**: You understand why Helm exists, can add and override values, can render and read templates before deploying, and know how to roll back. When someone asks you to "cut a Helm release" or "bump the chart version," you know exactly what that means and what files to touch.
