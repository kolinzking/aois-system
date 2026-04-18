# v8 — ArgoCD: GitOps
⏱ **Estimated time: 3–4 hours**

## Prerequisites

- v7 complete — Helm chart at `charts/aois/` with `values.prod.yaml`, verified with `helm template`
- AOIS deployed and healthy: `curl https://aois.46.225.235.51.nip.io/health` returns `{"status":"healthy"}`
- `kubectl` access to Hetzner cluster (`kubectl get nodes` works)
- The repo is on GitHub (`git remote -v` shows `origin https://github.com/kolinzking/aois-system`)

---

## Learning Goals

By the end of this version you will be able to:
- Explain the GitOps model and why it inverts the traditional deploy workflow
- Describe ArgoCD's components and what each one does
- Read an ArgoCD Application manifest and explain every field
- Distinguish Sync Status from Health Status and name all four problematic combinations
- Perform a complete deploy cycle using only `git push` — no kubectl, no helm
- Trigger rollback via ArgoCD CLI and via git revert
- Diagnose sync failures and recovery from OutOfSync states
- Explain what ArgoCD does NOT do (build images, run tests, manage secrets)

---

## What This Is

In v7 you packaged AOIS as a Helm chart. To deploy a new version you still run `helm upgrade` from your terminal. That command requires:
- Your machine to have kubeconfig pointing at the cluster
- You to be available to run it
- Trust that you ran the right command with the right values file
- No record in git of what was deployed or when

ArgoCD removes all of these requirements. It is a controller that runs inside your cluster, watches a git repository, and continuously reconciles: if the cluster does not match what git says it should be, ArgoCD makes it match.

This is GitOps. Git is not just where your code lives — it is the control plane for your infrastructure. Every deployment is a git commit. Every rollback is a git revert (or `argocd app rollback`). "What's running in prod?" is answered by reading git, not SSHing into the cluster.

---

## The Problem ArgoCD Solves

Without ArgoCD, your deployment pipeline has an implicit dependency on the person running it. You deploy by running a command. The command either works or fails. If it fails halfway, the cluster is in an unknown partial state. If it succeeds, the only record of what happened is in your terminal history.

**Concrete problems this creates:**

**Cluster drift**: Over time, people apply quick fixes directly with `kubectl patch` or `kubectl edit`. The cluster diverges from what's in git. When something breaks, you don't know if the cause is a code change or a manual edit made six months ago by someone who no longer works there.

**No audit trail**: `kubectl apply` leaves no trace in git. The Helm release Secret in the cluster has a timestamp, but it doesn't tell you who triggered it, from what code state, or what changed.

**Tribal knowledge deploys**: Only people with kubeconfig and helm installed can deploy. New team members can't deploy. Automation that doesn't have cluster credentials can't deploy.

**No continuous reconciliation**: If a pod's resource limit is manually changed, no system detects or corrects it. The cluster silently drifts.

ArgoCD makes the cluster self-correcting. If git says AOIS should have 2 replicas and the cluster has 3, ArgoCD corrects it within minutes — automatically, logged, traceable.

---

## The GitOps Mental Model

**Before GitOps:**
```
Engineer → helm upgrade / kubectl apply → Kubernetes cluster
```
The cluster's desired state is defined by whoever ran the last command. Git may or may not reflect what's actually running.

**With GitOps:**
```
Engineer → git commit + push → GitHub → ArgoCD (watching) → Kubernetes cluster
```
The cluster's desired state is defined by git. ArgoCD is a reconciliation loop between git and the cluster. The cluster is always catching up to git, never the other way around.

**The inversion**: In GitOps you do not manage the cluster. You manage git. The cluster manages itself.

---

## How ArgoCD Works: Under the Hood

ArgoCD is not a deployment tool. It is a **control loop** — a Kubernetes pattern where a controller continuously watches desired state (git) and actual state (cluster) and corrects any difference.

### The components

When you install ArgoCD, several pods run in the `argocd` namespace:

**argocd-application-controller**: The brain. Runs the reconciliation loop. Every 3 minutes (default) it:
1. Fetches the source from git (your repo, your branch, your Helm chart path)
2. Renders the Helm templates with your values file — identical to what `helm template` produces
3. Compares the rendered output to the live cluster state
4. If different: applies the changes (if auto-sync is enabled)

**argocd-repo-server**: Handles all git operations. Clones repos, caches them, runs `helm template` / `kustomize build` / raw YAML parsing. The application controller never touches git directly — it asks the repo server.

**argocd-server**: The API server + web UI. Exposes the REST API that the `argocd` CLI and the web dashboard use. Not involved in reconciliation — that's the application controller.

**argocd-redis**: Caches repo server results so the application controller does not re-clone the repo on every tick.

**argocd-dex-server**: Handles SSO / OIDC authentication for the web UI. Not needed for basic usage.

### Three-way diff

When ArgoCD compares what git says against what the cluster has, it performs a **three-way diff** — the same technique as `git merge`:

1. **Desired state**: the rendered output from git (what Helm templates produce)
2. **Live state**: what's actually in the cluster right now
3. **Last applied state**: what ArgoCD last applied (stored in the resource's annotation)

The three-way diff distinguishes between:
- Changes from git (should be applied)
- Changes Kubernetes added itself (status fields, resourceVersion — should be ignored)
- Changes from manual edits (should be reverted if selfHeal is on)

This is why ArgoCD does not fight with Kubernetes's own mutations. When Kubernetes adds a `resourceVersion` or updates a `status`, ArgoCD knows not to treat those as drift.

### Where ArgoCD stores state

ArgoCD's own state lives in Kubernetes custom resources in the `argocd` namespace. The `Application` resource you define in `argocd/application.yaml` is stored in the cluster. ArgoCD watches its own namespace for Application resources and reconciles each one.

```bash
kubectl get application -n argocd
kubectl describe application aois -n argocd
```

The Application resource holds: source repo, target branch, Helm values file path, sync policy, and current sync/health status.

---

## The Application Manifest

Everything ArgoCD needs to know about managing AOIS lives in `argocd/application.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: aois
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/kolinzking/aois-system
    targetRevision: main
    path: charts/aois
    helm:
      valueFiles:
        - values.prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: aois
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### `source` — where to get the desired state

**`repoURL`**: The git repository. ArgoCD will clone this.

**`targetRevision: main`**: Watch the `main` branch. Every commit to main is a candidate sync. You can also target a specific tag (`v7.0.0`) or commit SHA for immutable deploys.

**`path: charts/aois`**: Within the repo, the Helm chart lives here.

**`helm.valueFiles`**: The values overlay to apply. ArgoCD passes this to `helm template` just like you do manually. The path is relative to `path` — so it looks for `charts/aois/values.prod.yaml`.

### `destination` — where to deploy

**`server: https://kubernetes.default.svc`**: Deploy to the same cluster ArgoCD is running in. This is the in-cluster endpoint. You can also target remote clusters by registering them with ArgoCD.

**`namespace: aois`**: Deploy into the `aois` namespace.

### `syncPolicy` — the behavior rules

**`automated:`**: Enable auto-sync. Without this, ArgoCD detects drift but waits for you to manually click Sync or run `argocd app sync aois`. With it, drift is corrected automatically.

**`prune: true`**: If you remove a resource from the chart (say you delete `templates/service.yaml`), ArgoCD deletes it from the cluster. Without `prune`, removed resources become orphans — they stay in the cluster forever, unreferenced and unmanaged.

**`selfHeal: true`**: If someone manually edits a resource in the cluster (kubectl patch, kubectl edit), ArgoCD detects the drift on its next tick and reverts it. Git wins, always. Without `selfHeal`, manual edits persist until the next git-triggered sync overwrites them.

**`CreateNamespace=true`**: Creates the destination namespace if it does not exist. Removes the need to pre-create the namespace.

---

## Installing ArgoCD

All commands run on the Hetzner server (or from your machine with kubeconfig set):

```bash
# Create the namespace
kubectl create namespace argocd

# Apply the official upstream manifest
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

This creates around 50 resources: CRDs (Application, AppProject, etc.), Deployments, Services, ClusterRoles, and ConfigMaps. Watch them come up:

```bash
kubectl get pods -n argocd -w
# Wait until all pods show Running
# argocd-application-controller-0   1/1   Running
# argocd-dex-server-xxx             1/1   Running
# argocd-redis-xxx                  1/1   Running
# argocd-repo-server-xxx            1/1   Running
# argocd-server-xxx                 1/1   Running
```

### Get the initial admin password

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

This Secret is created by ArgoCD on first install. After you change the password, delete this Secret — it is no longer needed and leaving it is a security risk.

### Access the UI

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
# Open https://localhost:8080 — accept the self-signed cert
# Username: admin, Password: from above
```

The UI shows a card for each Application. Click into it to see the resource graph: your Deployment, Service, Ingress, the ReplicaSet the Deployment created, the pods it manages — all with health indicators.

### Install the ArgoCD CLI

```bash
# Linux (on the Hetzner server or your machine)
curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x argocd && sudo mv argocd /usr/local/bin/

# Authenticate to the ArgoCD server
argocd login localhost:8080 --username admin --password <password> --insecure
# --insecure skips TLS verification for the self-signed cert
```

---

## Registering the AOIS Application

With ArgoCD running, apply the Application manifest from the repo:

```bash
# If Helm still owns the release, hand it off first:
helm uninstall aois -n aois
# This removes the Helm release Secret — ArgoCD will take over ownership

# Apply the Application resource
kubectl apply -f argocd/application.yaml

# Watch ArgoCD discover and sync it
kubectl get application aois -n argocd -w
# SYNC STATUS will move: Unknown → OutOfSync → Synced
# HEALTH STATUS will move: Unknown → Progressing → Healthy
```

ArgoCD will:
1. Clone your repo
2. Find `charts/aois/` with `values.prod.yaml`
3. Run `helm template` internally
4. Apply all resources to the `aois` namespace
5. Report `Synced / Healthy`

Verify:
```bash
argocd app get aois
# Name:           aois
# Server:         https://kubernetes.default.svc
# Namespace:      aois
# URL:            https://localhost:8080/applications/aois
# Repo:           https://github.com/kolinzking/aois-system
# Target:         main
# Path:           charts/aois
# Helm Values:    values.prod.yaml
# SyncWindow:     Sync Allowed
# Sync Policy:    Automated (Prune)
# Sync Status:    Synced to main (abc1234)
# Health Status:  Healthy

curl https://aois.46.225.235.51.nip.io/health
# {"status":"healthy"}
```

---

## The GitOps Deploy Workflow

Every future deploy is now a git operation.

### Deploy a new image version

```bash
# 1. Edit values.prod.yaml
image:
  tag: v8

# 2. Commit and push
git add charts/aois/values.prod.yaml
git commit -m "deploy: AOIS v8"
git push

# 3. ArgoCD detects the change within 3 minutes and syncs automatically
# Watch from the CLI:
argocd app get aois --watch

# Or trigger an immediate sync (instead of waiting for the poll interval):
argocd app sync aois --watch
```

### Scale up

```bash
# Edit values.prod.yaml
replicaCount: 3

git add charts/aois/values.prod.yaml
git commit -m "scale: AOIS to 3 replicas"
git push
# ArgoCD applies — third pod comes up
```

### Emergency rollback

```bash
# Option 1: ArgoCD history-based rollback (fast, no git commit)
argocd app history aois
# ID  DATE                           REVISION
# 0   2026-04-18 10:00:00 +0000 UTC  abc1234
# 1   2026-04-18 11:30:00 +0000 UTC  def5678

argocd app rollback aois 0
# ArgoCD re-applies the Helm chart as it was at commit abc1234

# Option 2: Git revert (leaves audit trail)
git revert HEAD --no-edit
git push
# ArgoCD deploys the reverted state
```

Option 1 is faster for emergencies. Option 2 is better for team environments — the git history shows what happened and why.

---

## Sync Status and Health Status

ArgoCD tracks two independent dimensions:

### Sync Status

**`Synced`**: The cluster matches git exactly. Every resource in the cluster is identical to what the Helm templates produce from the current git commit.

**`OutOfSync`**: A difference exists between git and the cluster. This happens when:
- You push a new commit (git changed, cluster hasn't caught up)
- Someone made a manual cluster edit (cluster changed, git didn't)
- A resource was removed from git but `prune: false` (orphan exists in cluster)

**`Unknown`**: ArgoCD cannot determine status — usually a permissions issue or the Application was just created.

### Health Status

**`Healthy`**: All resources are running correctly. Pods are up and passing readiness probes. Services have endpoints.

**`Progressing`**: A rollout is in progress. ArgoCD is watching the Deployment's rollout — new pods starting, old ones terminating.

**`Degraded`**: Something is wrong. A pod is crashlooping, a Deployment is stuck, a resource failed to apply.

**`Suspended`**: The application is paused (sync is disabled).

### The important combinations

**`Synced / Healthy`**: Everything is fine. Git = cluster, cluster is healthy.

**`Synced / Degraded`**: ArgoCD applied what git says, but it's not working. The YAML was valid but the app is crashing. This is an application problem, not a deployment problem.

**`OutOfSync / Healthy`**: The cluster is running something different from git (maybe from a manual edit), but it's healthy. With `selfHeal: true`, this self-corrects.

**`OutOfSync / Progressing`**: A sync is happening right now. Normal transition state during a deploy.

---

## Polling vs Webhooks

By default ArgoCD polls git every 3 minutes. This means pushes can take up to 3 minutes to trigger a sync.

For faster deploys, configure a GitHub webhook that notifies ArgoCD the instant a push happens:

```bash
# Get the ArgoCD server URL (expose it first — see below)
# In GitHub: Settings → Webhooks → Add webhook
# Payload URL: https://your-argocd-server/api/webhook
# Content type: application/json
# Secret: generate one and add it to ArgoCD's secret
# Events: Just the push event
```

With a webhook, syncs trigger in seconds after a push. Without it, the 3-minute poll is fine for learning — add the webhook when deploy speed matters.

For now, trigger immediate syncs manually with `argocd app sync aois` to avoid waiting.

---

## Exposing ArgoCD (Optional)

You have cert-manager and Traefik running. Expose the ArgoCD server on a real domain:

```bash
# argocd/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-server
  namespace: argocd
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - argocd.46.225.235.51.nip.io
    secretName: argocd-tls
  rules:
  - host: argocd.46.225.235.51.nip.io
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 80
```

ArgoCD also needs to know it is behind TLS:
```bash
kubectl patch configmap argocd-cmd-params-cm -n argocd \
  --type merge -p '{"data":{"server.insecure":"true"}}'
kubectl rollout restart deployment argocd-server -n argocd
```

Then `https://argocd.46.225.235.51.nip.io` reaches the UI directly.

---

> **▶ STOP — do this now**
>
> After ArgoCD syncs AOIS, look at what it actually did:
> ```bash
> kubectl get all -n aois
> argocd app get aois
> ```
> Expected `argocd app get aois` output:
> ```
> Name:               aois
> Project:            default
> Server:             https://kubernetes.default.svc
> Namespace:          aois
> URL:                https://localhost:8080/applications/aois
> Repo:               https://github.com/kolinzking/aois-system
> Target:             main
> Path:               charts/aois
> Helm Values:        values.prod.yaml
> SyncWindow:         Sync Allowed
> Sync Policy:        Automated (Prune)
> Sync Status:        Synced to main (abc1234)
> Health Status:      Healthy
> ```
> In the `Sync Status` line, find the commit SHA (e.g., `abc1234`). Open that commit in GitHub: `https://github.com/kolinzking/aois-system/commit/abc1234`. You can see exactly what was in `values.prod.yaml` at deploy time. Every deploy is traceable to a commit, an author, a timestamp — this is the audit trail GitOps provides.

---

> **▶ STOP — do this now**
>
> Test `selfHeal`. With ArgoCD running and AOIS synced:
> ```bash
> # Manually scale the deployment
> kubectl scale deployment aois -n aois --replicas=5
>
> # Immediately check ArgoCD status
> argocd app get aois | grep "Sync Status"
> ```
> Expected immediately after the manual scale:
> ```
> Sync Status:        OutOfSync from main (abc1234)
> ```
> ArgoCD detected the drift within seconds (it watches the cluster, not just git).
> ```bash
> # Trigger sync now instead of waiting 3 minutes
> argocd app sync aois --watch
> ```
> Expected output during sync:
> ```
> TIMESTAMP   GROUP  KIND        NAMESPACE  NAME  STATUS   HEALTH   HOOK  MESSAGE
> 09:45:01           Deployment  aois       aois  Synced   Healthy        deployment "aois" successfully rolled out
> ```
> ```bash
> # Confirm replica count reverted
> kubectl get deployment aois -n aois -o jsonpath='{.spec.replicas}'
> ```
> Expected: `2` (back to what `values.prod.yaml` says — the three extra pods were terminated).
>
> This is `selfHeal: true` in action. Git is authoritative. Every manual edit is eventually corrected.

---

> **▶ STOP — do this now**
>
> Do a complete GitOps deploy cycle:
> ```bash
> # 1. Change a value in values.prod.yaml — drop to 1 replica
> #    (edit the file, do not use kubectl or helm)
>
> # 2. Commit and push
> git add charts/aois/values.prod.yaml
> git commit -m "test: scale to 1 replica via GitOps"
> git push
>
> # 3. Trigger immediate sync
> argocd app sync aois --watch
>
> # 4. Confirm
> kubectl get pods -n aois
> # One pod — the second terminated
>
> # 5. Revert via git
> git revert HEAD --no-edit
> git push
> argocd app sync aois --watch
>
> # 6. Confirm
> kubectl get pods -n aois
> # Two pods — back to values.prod.yaml default
> ```
> You just deployed twice with zero kubectl involvement. This is the GitOps workflow.

---

## Common Mistakes

**Pushing broken Helm templates to `main`** *(recognition)*
ArgoCD watches `main` and immediately tries to sync on every push. If you push a template with a syntax error, ArgoCD enters a `ComparisonError` state and stops syncing — including future good pushes. Always run `helm lint ./charts/aois` and `helm template` locally before pushing to main. Never use main as a scratch branch when ArgoCD is watching it.

*(recall — trigger it)*
```bash
# Introduce a deliberate Go template syntax error
# Edit charts/aois/templates/deployment.yaml — break a template expression
# Change: {{.Values.image.tag}} to {{.Values.image.tag}   (missing closing brace)
git add charts/aois/templates/deployment.yaml
git commit -m "test: broken template"
git push
```
Wait 3 minutes then check ArgoCD status:
```bash
argocd app get aois
# Health:   Unknown
# Sync:     ComparisonError
# Message:  failed to load target state: failed to generate manifest
```
Now push a fix — ArgoCD is blocked on every push until the broken template is fixed:
```bash
# Revert the broken template
git revert HEAD
git push
# Wait 3 minutes or: argocd app sync aois
```
Prevention — always run before pushing:
```bash
helm lint ./charts/aois
helm template aois ./charts/aois -f charts/aois/values.prod.yaml > /dev/null && echo "Template OK"
```

---

**Manual `kubectl edit` reverts immediately — fighting selfHeal** *(recognition)*
With `selfHeal: true`, ArgoCD compares the live cluster to git every 3 minutes and corrects any drift. Manual kubectl edits are overwritten by design — this is not a bug.

*(recall — trigger it)*
```bash
# Manually scale the deployment
kubectl scale deployment aois --replicas=5 -n aois
kubectl get deployment aois -n aois
# DESIRED: 5 — your change applied
```
Wait 3 minutes (or trigger: `argocd app sync aois`):
```bash
kubectl get deployment aois -n aois
# DESIRED: 2 — ArgoCD reverted to values.prod.yaml
```
This is correct behavior — the git file is the truth. Fix: if you want 5 replicas, change `replicaCount: 5` in `values.prod.yaml`, commit, push. ArgoCD will sync it.

For emergency bypasses during an incident:
```bash
argocd app set aois --sync-policy none    # disable auto-sync
kubectl scale deployment aois --replicas=5 -n aois   # make emergency change
# ... resolve incident ...
argocd app set aois --sync-policy automated   # re-enable
```

---

**No `prune: true` — deleted resources accumulate in the cluster** *(recognition)*
Without `prune: true`, ArgoCD never deletes resources. You remove a Service from the chart and push — the Service stays in the cluster forever. Over weeks, the cluster fills with stale resources that nobody manages and nobody knows about.

*(recall — trigger it)*
```bash
# Temporarily remove prune from the Application
kubectl patch application aois -n argocd \
  --type json \
  -p '[{"op": "remove", "path": "/spec/syncPolicy/automated/prune"}]'

# Now delete a template — rename ingress.yaml to ingress.yaml.disabled
mv charts/aois/templates/ingress.yaml charts/aois/templates/ingress.yaml.disabled
git add -A && git commit -m "test: remove ingress" && git push

# Force sync
argocd app sync aois
```
Expected: ArgoCD syncs successfully, but:
```bash
kubectl get ingress -n aois
# NAME   CLASS   HOSTS                               ...
# aois   nginx   aois.46.225.235.51.nip.io          # still there!
```
The Ingress was not deleted. ArgoCD is `Synced` but the old resource remains.

Fix: restore `prune: true` and re-sync. Now the orphaned Ingress is deleted. Restore your template after:
```bash
mv charts/aois/templates/ingress.yaml.disabled charts/aois/templates/ingress.yaml
```

---

**Confusing sync status with health status — they're independent** *(recognition)*
`Synced` means ArgoCD applied the manifests. `Healthy` means the application is actually running. A pod can crash after a successful sync — ArgoCD shows `Synced` and `Degraded` simultaneously. These are two different dimensions.

*(recall — trigger it)*
```bash
# Set an invalid image tag to cause pods to fail after a clean sync
# Edit values.prod.yaml: image.tag: v999-does-not-exist
git add charts/aois/values.prod.yaml
git commit -m "test: bad image tag"
git push
argocd app sync aois
```
Expected after sync:
```bash
argocd app get aois
# Sync Status:    Synced    ← ArgoCD applied the manifest — that part worked
# Health Status:  Degraded  ← pods are in ImagePullBackOff
```
`argocd app get aois --show-operation` shows the operation succeeded. The problem is in the application layer, not the gitops layer.

Fix: revert the values change, push, sync again. `argocd app get aois --show-operation` is the first command to run when diagnosing any ArgoCD problem — it shows exactly which phase failed.

---

**ArgoCD's 3-minute poll makes deploys feel broken** *(recognition)*
After `git push`, ArgoCD polls every 3 minutes by default. If you push and watch for 30 seconds expecting immediate deployment, nothing happens — which looks like ArgoCD is broken or ignoring the push.

*(recall — trigger it)*
```bash
# Push a real change
echo "# comment" >> charts/aois/templates/deployment.yaml
git add -A && git commit -m "test: force push" && git push

# Immediately check ArgoCD
argocd app get aois
# OutOfSync — but not deploying yet. It's waiting for the 3-minute poll.
```
You can either wait, or force immediate sync:
```bash
argocd app sync aois    # trigger immediately
```
For production, configure the GitHub webhook to eliminate polling entirely — ArgoCD deploys within seconds of a push instead of up to 3 minutes later. The webhook setup in the notes converts ArgoCD from poll-mode to push-mode.

---

## Troubleshooting

**`ComparisonError: failed to load target state: failed to generate manifest`**
ArgoCD cannot render the Helm chart. Usually a template syntax error or a missing values key. Run locally to reproduce:
```bash
helm template aois ./charts/aois -f charts/aois/values.prod.yaml
```
Fix the error, push, ArgoCD re-renders.

**Application stuck in `OutOfSync` even after sync**
ArgoCD synced but the cluster still differs. Usually a resource that ArgoCD cannot manage (immutable fields, a resource owned by another controller). Check:
```bash
argocd app get aois --show-operation
```
Look for resources showing `SyncFailed` and the error message.

**`Namespace "aois" already exists` on first sync**
ArgoCD tried to create the namespace (because of `CreateNamespace=true`) but it already exists. This is not an error — ArgoCD compares the namespace spec and finds it matches. Status should be `Synced`. If it reports as a problem, verify the namespace was not created with conflicting labels.

**ArgoCD reverts my manual changes even though selfHeal should be off**
Check that `automated.selfHeal` is not in your Application manifest. Run:
```bash
kubectl get application aois -n argocd -o yaml | grep -A5 selfHeal
```
If the field is there, selfHeal is on.

**Sync triggered but no change in cluster**
The rendered Helm output is identical to what's already in the cluster. ArgoCD applied but nothing differed. This is correct behavior — ArgoCD only patches resources that actually changed.

**Application shows `Missing` resources**
A resource that ArgoCD expects (based on the rendered templates) does not exist in the cluster. This happens if someone deleted a resource manually. ArgoCD will recreate it on the next sync if auto-sync is on.

---

## What ArgoCD Does NOT Do

ArgoCD manages the deploy lifecycle. It does not:

- **Build Docker images** — that is still GitHub Actions / your CI pipeline. ArgoCD only deploys what already exists in the registry.
- **Run tests** — ArgoCD applies YAML, it does not run test suites. Tests happen before the commit that changes the image tag.
- **Manage secrets** — ArgoCD applies Kubernetes Secrets if they are in the repo (never put real secrets in git). For secret management, you will use External Secrets Operator in v12 to pull secrets from Vault or AWS Secrets Manager into Kubernetes.
- **Provision infrastructure** — ArgoCD deploys to existing clusters. Terraform provisions the cluster. ArgoCD deploys onto it.

Understanding these boundaries matters. When someone asks "can ArgoCD run our tests?" the answer is no — and knowing why tells you where tests belong in the pipeline.

---

## How v8 Connects to What Comes Next

**v9 (KEDA)**: You will add a `ScaledObject` to the Helm chart. After `git push`, ArgoCD deploys it. KEDA detects the resource and wires up event-driven scaling. You will never touch the cluster directly.

**v28 (GitHub Actions)**: The CI/CD pipeline will push a new image, update `values.prod.yaml` with the new tag, commit, and push to main. ArgoCD detects the commit and deploys. The full pipeline from code push to running pod becomes automated end to end.

**v12 (EKS)**: You will create a second ArgoCD Application pointing at `values.eks.yaml`. Same chart, different values, different destination cluster. ArgoCD manages both independently.

GitOps is not just an ArgoCD feature — it is the operational model for the rest of the curriculum. After v8, git is always the control plane.

---

## Mastery Checkpoint

**1. Explain the GitOps inversion**
Without notes: what does "the cluster is a consequence of git, not a thing you manage directly" mean? What changes operationally when you adopt this model? (You stop running kubectl/helm to deploy. You make git commits. The cluster follows.)

**2. Name ArgoCD's components and their roles**
What does each pod in the `argocd` namespace do?
- `argocd-application-controller` — the reconciliation loop
- `argocd-repo-server` — git cloning, template rendering
- `argocd-server` — API + web UI
- `argocd-redis` — caching
- `argocd-dex-server` — auth/SSO

Run `kubectl get pods -n argocd` and match each pod name to its role.

**3. Understand three-way diff**
ArgoCD uses a three-way diff. What are the three states it compares? (Desired state from git, live state from cluster, last applied state from annotation.) Why does it need all three? (To distinguish Kubernetes-added fields from user drift — if it only compared git vs live, it would fight Kubernetes's own mutations like adding `resourceVersion`.)

**4. The selfHeal test**
Perform the selfHeal test from the STOP exercise. Then explain what would happen if `selfHeal` were `false`: the manual edit persists until the next git-triggered sync. A commit that changes a different field would cause ArgoCD to apply the full diff — which would also revert the manual edit as a side effect. With `selfHeal: false`, drift is corrected eventually but not guaranteed to be corrected immediately.

**5. Distinguish Sync vs Health**
Give one example of each problematic combination:
- `Synced / Degraded`: ArgoCD applied the chart correctly, but the pod is OOMKilled. Git and cluster match, but the app is broken.
- `OutOfSync / Healthy`: Someone kubectl-patched the replica count up. The extra pods are healthy, but the cluster doesn't match git.

**6. Trace a complete deploy**
Walk through every step from `git push` to `Synced/Healthy`:
1. Push lands on GitHub
2. ArgoCD's poll timer fires (or webhook triggers immediately)
3. `argocd-repo-server` clones the repo at the new commit
4. `argocd-repo-server` runs `helm template charts/aois -f values.prod.yaml`
5. `argocd-application-controller` receives the rendered output
6. Three-way diff runs — identifies what changed
7. Application controller applies the diff to the cluster via Kubernetes API
8. Kubernetes performs rolling update
9. Readiness probe passes on new pod
10. Old pod terminates
11. Application controller checks live state — matches desired state
12. Reports: `Synced / Healthy`

Can you identify which step would fail if: the image tag doesn't exist in GHCR? (Step 8 — pod fails to pull image, ImagePullBackOff, Health goes Degraded)

**7. The rollback decision**
You deployed a bad config and need to roll back immediately. When do you use `argocd app rollback aois 0` vs `git revert HEAD && git push`?

- Use `argocd app rollback` when speed matters more than audit trail. It's faster (no commit, instant).
- Use `git revert` when working in a team. The revert commit is visible to everyone — it documents what happened and when. In regulated environments, the git revert may be required for compliance audit trails.

**The mastery bar**: You understand GitOps as an operational model, not just a tool. You can explain what ArgoCD is doing at the component level, diagnose sync and health status, perform the full GitOps deploy cycle, and recover from failures. When someone on a team says "just kubectl apply it" you can explain exactly why that breaks the GitOps model — and what to do instead.
