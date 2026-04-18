# v8 — ArgoCD: GitOps

## What This Is

In v7 you packaged AOIS as a Helm chart. To deploy a new version you still run `helm upgrade` by hand. That means:
- You need to be at a terminal with kubeconfig
- There is no record in git of what was deployed and when
- A teammate cannot deploy without your credentials
- "What's running in prod?" requires SSHing into the cluster to check

ArgoCD eliminates all of this. It is a controller that runs inside your cluster and watches a git repo. When the repo changes, ArgoCD detects the diff and applies it. The cluster state is always what git says it should be.

This pattern is called **GitOps**. Git is the single source of truth. The cluster is a consequence of git, not a thing you manage directly.

---

## The GitOps Mental Model

**Before GitOps (what you've been doing):**
```
You → kubectl apply / helm upgrade → Cluster
```
The cluster state lives in the cluster. Git may or may not reflect it. There is no automatic reconciliation.

**With GitOps:**
```
You → git push → GitHub → ArgoCD detects diff → Cluster
```
The cluster state is defined in git. ArgoCD continuously compares what git says against what the cluster has. Any drift is corrected automatically.

**What this means in practice:**
- "Deploy v8" = change `image.tag: v8` in `values.prod.yaml`, commit, push
- "Roll back" = `git revert` or `argocd app rollback aois 1`
- "What's running?" = read `values.prod.yaml` in git — that IS what's running
- Disaster recovery = provision a new cluster, apply ArgoCD, point it at the repo — everything comes back

---

## How ArgoCD Works

ArgoCD runs as a set of pods in the `argocd` namespace. Its core component is the **Application Controller** — a reconciliation loop that:

1. Reads the `Application` custom resource you define
2. Fetches the source from git (your repo, your branch, your Helm chart path)
3. Renders the Helm templates with your values file
4. Compares the rendered output against what's currently in the cluster
5. If there's a diff: applies the changes (if auto-sync is on) or marks the app as OutOfSync (if manual)
6. Repeats every 3 minutes (default) or immediately on a webhook from GitHub

This loop never stops. If someone manually edits a Deployment in the cluster, ArgoCD detects the drift within 3 minutes and reverts it. The cluster is self-healing.

---

## The Application Manifest

Everything about how ArgoCD manages AOIS is defined in `argocd/application.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: aois
  namespace: argocd          # ArgoCD's own namespace
spec:
  project: default
  source:
    repoURL: https://github.com/kolinzking/aois-system
    targetRevision: main     # watch this branch
    path: charts/aois        # Helm chart is here
    helm:
      valueFiles:
        - values.prod.yaml   # overlay on top of values.yaml
  destination:
    server: https://kubernetes.default.svc   # this cluster
    namespace: aois
  syncPolicy:
    automated:
      prune: true        # delete resources removed from git
      selfHeal: true     # revert manual cluster edits
    syncOptions:
      - CreateNamespace=true
```

**`prune: true`**: If you remove a resource from the chart, ArgoCD deletes it from the cluster. Without this, removed resources linger as orphans.

**`selfHeal: true`**: If someone kubectl-patches a Deployment directly, ArgoCD reverts it on the next sync. Git wins, always.

**`targetRevision: main`**: ArgoCD watches the `main` branch. Every push to main is a potential deploy. This is why you should never push broken Helm templates to main.

---

## Installing ArgoCD

Run these on the Hetzner server (or from your machine with the cluster's kubeconfig):

```bash
# Create the argocd namespace
kubectl create namespace argocd

# Install ArgoCD (official upstream manifest)
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for all pods to be running (~60 seconds)
kubectl wait --for=condition=available deployment -l app.kubernetes.io/name=argocd-server -n argocd --timeout=120s

# Verify
kubectl get pods -n argocd
```

You should see pods for: argocd-server, argocd-repo-server, argocd-application-controller, argocd-dex-server, argocd-redis.

### Access the ArgoCD UI

ArgoCD has a web UI. To access it from your laptop:

```bash
# Port-forward the ArgoCD server
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Open https://localhost:8080 in your browser (accept the self-signed cert)
```

Get the initial admin password:
```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

Login: username `admin`, password from above.

### Install the ArgoCD CLI (optional but useful)

```bash
# macOS
brew install argocd

# Linux
curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x argocd && sudo mv argocd /usr/local/bin/

# Login via CLI
argocd login localhost:8080 --username admin --password <password> --insecure
```

---

## Deploying the AOIS Application

With ArgoCD running, register the AOIS application:

```bash
# Remove the Helm-managed release first (ArgoCD will own it now)
helm uninstall aois -n aois

# Apply the Application manifest from the repo
kubectl apply -f argocd/application.yaml

# Watch ArgoCD sync
kubectl get application aois -n argocd -w
```

Within a minute ArgoCD will:
1. Clone your git repo
2. Render `charts/aois` with `values.prod.yaml`
3. Apply all resources to the `aois` namespace
4. Report status: `Synced / Healthy`

In the UI you will see a visual graph of all resources — Deployment, Service, Ingress, pods — with their health status.

---

## The Deploy Workflow (GitOps Style)

**Old way (v7):**
```bash
helm upgrade aois ./charts/aois -f charts/aois/values.prod.yaml -n aois --set image.tag=v8
```

**New way (v8):**
```bash
# 1. Edit values.prod.yaml
image:
  tag: v8

# 2. Commit and push
git add charts/aois/values.prod.yaml
git commit -m "deploy: bump AOIS to v8"
git push

# 3. ArgoCD detects the change and deploys automatically
# Watch it happen:
kubectl get pods -n aois -w
```

You never touch kubectl or helm to deploy again. Git is the deployment mechanism.

---

## Sync Status and Health

ArgoCD tracks two dimensions for every application:

**Sync Status:**
- `Synced` — cluster matches git exactly
- `OutOfSync` — cluster differs from git (someone edited directly, or you pushed a change not yet applied)

**Health Status:**
- `Healthy` — all resources are running correctly (pods up, endpoints ready)
- `Degraded` — something is wrong (crashlooping pod, failed deployment)
- `Progressing` — a rollout is in progress

When you push a new image tag:
1. Status goes `OutOfSync` (git has v8, cluster has v7)
2. ArgoCD detects and begins sync
3. Status becomes `Progressing` (new pod starting)
4. Status becomes `Synced / Healthy` (new pod ready, old pod terminated)

```bash
# Watch sync status from CLI
argocd app get aois
argocd app sync aois --watch   # trigger manual sync and watch progress
```

---

## Rollback

ArgoCD keeps a history of every sync (tied to git commits):

```bash
argocd app history aois
# ID  DATE                           REVISION
# 1   2026-04-18 10:00:00 +0000 UTC  abc1234 (HEAD)
# 2   2026-04-18 11:30:00 +0000 UTC  def5678

# Roll back to the previous revision
argocd app rollback aois 1
```

ArgoCD re-applies the Helm chart as it was at that git commit. Kubernetes performs a rolling update back to the previous image. No manual kubectl required.

You can also roll back via git:
```bash
git revert HEAD
git push
# ArgoCD deploys the reverted state
```

Both work. The git revert approach leaves an explicit audit trail in git history.

---

> **▶ STOP — do this now**
>
> Before installing ArgoCD, understand what you're about to run:
> ```bash
> kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
> ```
> This creates ~50 Kubernetes resources. After applying, run:
> ```bash
> kubectl get all -n argocd
> ```
> Identify: which pods are running, what each does (server = UI/API, repo-server = git cloning, application-controller = the reconciliation loop, redis = caching, dex = auth).

---

> **▶ STOP — do this now**
>
> After ArgoCD has synced AOIS, trigger a manual edit to the Deployment and watch selfHeal revert it:
> ```bash
> # Edit the replica count directly in the cluster
> kubectl scale deployment aois -n aois --replicas=3
>
> # Watch the pod count
> kubectl get pods -n aois -w
>
> # Within 3 minutes, ArgoCD reverts to replicas=2 (from values.prod.yaml)
> # ArgoCD UI will briefly show OutOfSync then return to Synced
> ```
> This is what `selfHeal: true` does. Git is authoritative. The cluster cannot drift.

---

> **▶ STOP — do this now**
>
> Do a full GitOps deploy cycle:
> ```bash
> # 1. Open values.prod.yaml and change a value (replicaCount: 1 to test)
> # 2. Commit and push
> git add charts/aois/values.prod.yaml
> git commit -m "test: scale down to 1 replica via GitOps"
> git push
>
> # 3. Watch ArgoCD detect and apply
> kubectl get pods -n aois -w
> # You'll see one pod terminate
>
> # 4. Revert it
> git revert HEAD --no-edit
> git push
> # Watch the second pod come back
> ```
> You just did two production deploys via git. No kubectl, no helm, no SSH.

---

## Mastery Checkpoint

**1. The GitOps mental model**
Without notes: explain the difference between "push to deploy" (what you did in v6/v7) and GitOps. What is ArgoCD's role? What is git's role? What happens if someone kubectl-edits the cluster?

**2. Read the Application manifest**
Open `argocd/application.yaml`. For each field in `spec.syncPolicy`, explain what would happen if you removed it:
- Remove `prune: true` → deleted resources linger as orphans
- Remove `selfHeal: true` → manual kubectl edits persist until next git push
- Remove `automated:` entirely → ArgoCD detects diffs but never applies them (manual sync only)

**3. Trace a deploy from git push to running pod**
Walk through every step: you edit `values.prod.yaml` and push. What happens next? (ArgoCD polls/webhook → detects OutOfSync → fetches repo → renders Helm templates → kubectl applies diff → Kubernetes rolling update → new pod up → old pod terminated → ArgoCD reports Synced/Healthy)

**4. Understand sync vs health**
An application can be `Synced` but `Degraded`. How? (git matches cluster exactly — ArgoCD applied the change — but the pod is crashlooping. Synced means git=cluster; Healthy means the application is actually working. These are independent.)

**5. The self-healing test**
After deploying with ArgoCD, manually change something in the cluster:
```bash
kubectl patch deployment aois -n aois -p '{"spec":{"replicas":5}}'
```
Wait 3 minutes. What happens? (ArgoCD reverts to whatever `replicaCount` says in `values.prod.yaml`) Why? (`selfHeal: true` — the controller compares cluster state to desired state on every tick and corrects drift)

**6. Rollback via CLI and via git**
Name both rollback methods and when you'd use each:
- `argocd app rollback aois 1` — fast, no new commit, good for emergency
- `git revert HEAD && git push` — leaves audit trail in git, better for team environments

**The mastery bar**: You understand that ArgoCD is a control loop, not a deployment tool. You can explain GitOps to someone who has only used kubectl. You have done at least one full deploy cycle via git push and watched ArgoCD apply it without touching the cluster directly.
