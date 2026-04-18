# v6 — k3s on Hetzner: Your First Real Cluster
⏱ **Estimated time: 6–10 hours**

## What this version builds

v5 runs on your laptop inside Docker Compose. That is fine for development but it means:
- It is not accessible from the internet
- If your laptop closes, AOIS stops
- There is no automatic restart, no scaling, no health monitoring
- You cannot give anyone a URL to test it

v6 changes all of that. By the end you will have AOIS running on a real Linux server in a data center in Germany, accessible at a real HTTPS URL, managed by Kubernetes. Every component — the container, the networking, the TLS certificate, the health checks — is declared in YAML files and applied with one command.

This is how production software runs. Not `uvicorn main:app` on a laptop.

**What v6 adds:**
- A Hetzner VPS running k3s (lightweight Kubernetes)
- Your Docker image hosted on GHCR (GitHub Container Registry)
- Raw Kubernetes manifests: Namespace, Secret, Deployment, Service, Ingress
- cert-manager + Let's Encrypt: automatic HTTPS with a real certificate
- nip.io: a free domain that works for any IP address
- `kubectl` from Codespaces talking to the real cluster

**End state:** `curl https://aois.46.225.235.51.nip.io/analyze` returns a real AI analysis, served from Kubernetes, over HTTPS, from a server in Nuremberg.

---

## Prerequisites

- v5 complete — the containerized, security-hardened AOIS
- A Hetzner Cloud account (cloud.hetzner.com) — a CX22 server costs ~€4/month
- A GitHub account with a Personal Access Token (PAT) scoped to `write:packages`
- kubectl installed in your environment:
  ```bash
  kubectl version --client
  ```
  If not installed:
  ```bash
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x kubectl && mv kubectl /usr/local/bin/
  ```

---

## Learning goals

By the end of this version you will understand:
- What Kubernetes is and why it exists (the problem Docker Compose does not solve)
- What k3s is and why it is the right choice for a single Hetzner node
- What each Kubernetes resource type does: Namespace, Secret, Deployment, Service, Ingress
- How cert-manager automates TLS certificate issuance and renewal
- What nip.io is and why it solves the "I need a domain but don't have one" problem
- How to get kubectl on your local machine talking to a remote cluster
- What liveness and readiness probes do and why they matter

---

## Part 1 — The mental model: Kubernetes vs Docker Compose

Docker Compose answers: "How do I run multiple containers together on one machine?"

Kubernetes answers: "How do I run containers reliably across many machines, with automatic restarts, health monitoring, traffic routing, and zero-downtime deploys?"

Even on a single node (like your Hetzner VPS), Kubernetes gives you:

| Capability | Docker Compose | Kubernetes |
|-----------|---------------|------------|
| Restart crashed containers | Yes (restart: always) | Yes (always, with backoff) |
| Health checks before routing traffic | No | Yes (readiness probe) |
| Rolling deploys (zero downtime) | No | Yes |
| Resource limits per container | No | Yes (requests/limits) |
| TLS termination + certificate management | Manual (nginx + certbot) | cert-manager + Ingress |
| Scaling to N replicas | Manual (`--scale`) | `replicas: N` + HPA |
| Declarative desired state | Partial | Full — cluster self-heals toward desired state |

The Kubernetes model is: **you declare what you want, the cluster makes it happen and keeps it that way.** If a pod crashes, Kubernetes restarts it. If you deploy a broken image, Kubernetes refuses to route traffic until the new pod passes health checks.

---

## Part 2 — What k3s is

k3s is Kubernetes, stripped down for single-node and edge deployments:
- Same `kubectl` commands, same YAML manifests, same APIs as full k8s
- Ships as a single ~60MB binary (vs hundreds of components in full k8s)

> **▶ STOP — do this now**
>
> Before touching Kubernetes, map the Docker Compose concepts to their Kubernetes equivalents:
> ```
> Docker Compose → Kubernetes
> ─────────────────────────────────────────
> service: aois   → Deployment + Service
> image:          → spec.containers[].image
> ports:          → Service.spec.ports
> env_file: .env  → Secret (ANTHROPIC_API_KEY etc)
> depends_on:     → readinessProbe
> restart: always → spec.restartPolicy: Always
> networks:       → (built-in — every pod in same namespace can communicate)
> volumes:        → PersistentVolumeClaim
> ```
>
> Open `docker-compose.yml` side by side with `k8s/deployment.yaml`:
> ```bash
> cat /workspaces/aois-system/docker-compose.yml | grep -v "^#" | head -25
> cat /workspaces/aois-system/k8s/deployment.yaml | head -30
> ```
> Find each Docker Compose concept in the Kubernetes manifest. The mapping is exact — Kubernetes just has more verbosity and more power.
- Built-in: Traefik (ingress controller), CoreDNS (internal DNS), local-path storage
- Runs fine on a 2-core 4GB RAM server — the Hetzner CX22

**What k3s includes that full k8s does not have by default:**
- Traefik ingress controller — already running, no separate install needed
- local-path-provisioner — creates PersistentVolumes from host disk

**What k3s does not change:**
- All YAML manifests are identical to full k8s
- `kubectl` works exactly the same
- Phase 4 (EKS) uses the same manifests with minor value changes

k3s is not a toy. It runs in production at companies and powers edge deployments at scale. You are learning real Kubernetes.

---

## Part 3 — Server setup

### Provision the Hetzner VPS

In Hetzner Cloud console:
1. Create project → Add server
2. Location: Nuremberg (NBG1) — closest to most users
3. Image: Ubuntu 24.04
4. Type: CX22 (2 vCPU, 4GB RAM) — sufficient for k3s + AOIS
5. SSH keys: paste your public key
6. Click Create

Note the IP address — this is your `SERVER_IP` throughout this guide.

### SSH into the server

```bash
ssh root@46.225.235.51
```

Expected: you land at a root shell on the Ubuntu server.

Verify:
```bash
uname -a
# Linux ubuntu-8gb-nbg1-1 6.x.x-xx-generic x86_64 GNU/Linux

free -h
#               total        used        free
# Mem:           7.8Gi       500Mi       7.3Gi

df -h /
# Filesystem      Size  Used Avail Use%
# /dev/sda1        76G  3.2G   73G   5%
```

### Install k3s

One command:
```bash
curl -sfL https://get.k3s.io | sh -
```

This downloads the k3s binary, installs it as a systemd service, and starts it. The install takes about 60 seconds.

Verify:
```bash
kubectl get nodes
```

Expected output:
```
NAME                STATUS   ROLES                  AGE   VERSION
ubuntu-8gb-nbg1-1   Ready    control-plane,master   1m    v1.34.x+k3s1
```

`Ready` means k3s is running and the node has registered itself.

**What just happened under the hood:**
- k3s installed as `/usr/local/bin/k3s`
- systemd service `k3s.service` created and started
- Kubernetes API server running on port 6443
- Traefik ingress controller deployed automatically
- CoreDNS deployed for internal cluster DNS
- kubeconfig written to `/etc/rancher/k3s/k3s.yaml`

---

## Part 4 — Connect kubectl from Codespaces to the cluster

k3s wrote a kubeconfig to `/etc/rancher/k3s/k3s.yaml`. This file contains:
- The cluster's certificate authority (to verify the server is real)
- Client credentials (to prove you are authorized)
- The API server URL (currently `https://127.0.0.1:6443`)

You need to copy this file to your Codespaces environment and change `127.0.0.1` to the server's public IP.

**On the Hetzner server:**
```bash
cat /etc/rancher/k3s/k3s.yaml
```

Copy the full output.

**In Codespaces:**
```bash
mkdir -p ~/.kube
cat > ~/.kube/config << 'EOF'
# paste the k3s.yaml content here
EOF
sed -i 's/127.0.0.1/46.225.235.51/g' ~/.kube/config
chmod 600 ~/.kube/config
```

The `sed` command replaces `127.0.0.1` (localhost on the server) with the public IP so kubectl can reach the API server from outside.

Verify from Codespaces:
```bash
kubectl get nodes
```

Expected:
```
NAME                STATUS   ROLES                  AGE   VERSION
ubuntu-8gb-nbg1-1   Ready    control-plane,master   5m    v1.34.x+k3s1
```

You are now controlling the remote cluster from your local machine. Every `kubectl` command you run goes over HTTPS to port 6443 on the Hetzner server, authenticated with the certificates from the kubeconfig.

**Security note:** The kubeconfig is equivalent to a root password for your cluster. Keep it in `~/.kube/config` with `chmod 600`, never commit it to git.

---

## Part 5 — Build and push the Docker image to GHCR

GHCR (GitHub Container Registry) is GitHub's Docker registry. Your cluster needs to pull the image from somewhere on the internet — GHCR is free for public and private images.

### Create a GitHub Personal Access Token

GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token:
- Name: `aois-ghcr`
- Expiration: 90 days
- Scopes: `write:packages`, `read:packages`, `delete:packages`

Copy the token immediately — GitHub only shows it once.

### Login and push

```bash
export GITHUB_TOKEN=ghp_your_token_here
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

Expected:
```
Login Succeeded
```

Build and push:
```bash
docker build -t ghcr.io/YOUR_GITHUB_USERNAME/aois:v6 /workspaces/aois-system
docker push ghcr.io/YOUR_GITHUB_USERNAME/aois:v6
```

Expected (push):
```
v6: digest: sha256:abc123... size: 2205
```

The image is now at `ghcr.io/kolinzking/aois:v6` — accessible from anywhere, including your Hetzner cluster.

---

## Part 6 — The Kubernetes manifests

All manifests live in `/workspaces/aois-system/k8s/`. Each file declares one or more Kubernetes resources.

### namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: aois
```

A Namespace is a logical boundary inside the cluster. All AOIS resources live in the `aois` namespace — separate from `cert-manager`, `kube-system`, and other namespaces. This means:
- `kubectl get pods -n aois` shows only AOIS pods
- Resource quotas can be set per namespace
- RBAC policies can be scoped to a namespace

Every subsequent resource has `namespace: aois` in its metadata.

### secret.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: aois-secrets
  namespace: aois
type: Opaque
stringData:
  ANTHROPIC_API_KEY: "sk-ant-..."
  OPENAI_API_KEY: "sk-proj-..."
```

A Secret stores sensitive data as base64-encoded values in etcd (the cluster database). `stringData` accepts plain text and Kubernetes handles the encoding.

**Why not use a ConfigMap?** ConfigMaps are for non-sensitive config. Secrets get special treatment: they can be encrypted at rest (with etcd encryption), mounted as tmpfs in pods, and excluded from logs.

**Important:** `secret.yaml` is in `.gitignore` — it must never be committed to git. In production (v27), HashiCorp Vault or AWS Secrets Manager replaces this.

The Deployment references it with:
```yaml
envFrom:
- secretRef:
    name: aois-secrets
```

This injects every key from the Secret as an environment variable in the container. The AOIS app reads `ANTHROPIC_API_KEY` from `os.environ` via `python-dotenv` — this is identical to how `.env` worked locally.

### deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aois
  namespace: aois
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aois
  template:
    metadata:
      labels:
        app: aois
    spec:
      imagePullSecrets:
      - name: ghcr-secret
      containers:
      - name: aois
        image: ghcr.io/kolinzking/aois:v6
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: aois-secrets
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
```

**Field by field:**

`replicas: 1` — run one instance. In v9 (KEDA), this scales automatically based on load.

`selector.matchLabels` and `template.metadata.labels` — these must match. The Deployment uses them to know which pods it owns. When you scale to 3 replicas, all 3 pods get `app: aois` and the Deployment manages them.

`imagePullSecrets` — your GHCR image is private. This tells Kubernetes to use the `ghcr-secret` credential when pulling. Without this, the pull fails with `ImagePullBackOff`.

`resources.requests` — what this container is guaranteed. The scheduler uses requests to decide which node to place the pod on.

`resources.limits` — the maximum the container can use. If it tries to use more memory than the limit, the OOMKiller terminates it (the same OOMKilled error AOIS analyzes in its test cases). If it exceeds CPU limits, it gets throttled.

**Liveness probe** — Kubernetes pings `/health` every 20 seconds (after a 15-second startup grace period). If it fails 3 times in a row, Kubernetes kills the pod and restarts it. This catches hangs: a pod that is running but stuck.

**Readiness probe** — Kubernetes pings `/health` every 10 seconds (after 5 seconds). Until it passes, the pod receives zero traffic. This prevents Kubernetes from routing requests to a pod that is still starting up. A pod can be alive (liveness passes) but not ready (readiness fails) — for example, during a model warm-up.

The difference:
- Liveness failure → restart the pod
- Readiness failure → stop sending traffic to it (but don't restart)

### service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: aois
  namespace: aois
spec:
  selector:
    app: aois
  ports:
  - port: 80
    targetPort: 8000
```

A Service is a stable internal endpoint. Pods have ephemeral IPs that change when they restart. The Service has a stable DNS name (`aois.aois.svc.cluster.local`) and load-balances across all pods matching `app: aois`.

`port: 80` — the port other services inside the cluster use to reach AOIS.
`targetPort: 8000` — the port the container actually listens on (uvicorn's port).

The Ingress sends traffic to the Service, which forwards it to the pod.

### ingress.yaml

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: aois
  namespace: aois
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - aois.46.225.235.51.nip.io
    secretName: aois-tls
  rules:
  - host: aois.46.225.235.51.nip.io
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: aois
            port:
              number: 80
```

The Ingress is the entry point from the internet. Traefik (k3s's built-in ingress controller) watches for Ingress resources and configures itself accordingly:
- Requests for `aois.46.225.235.51.nip.io` → route to Service `aois` on port 80
- TLS: terminate HTTPS using the certificate in Secret `aois-tls`

The annotation `cert-manager.io/cluster-issuer: letsencrypt-prod` tells cert-manager: "when you see this Ingress, automatically issue a certificate for its hostname."

**What is nip.io?**

nip.io is a free wildcard DNS service. Any hostname in the format `<anything>.<IP>.nip.io` resolves to `<IP>`. So `aois.46.225.235.51.nip.io` resolves to `46.225.235.51` — your Hetzner server.

This means:
- No domain registrar needed
- Works with Let's Encrypt (which validates via HTTP challenge to the IP)
- Works immediately — no DNS propagation wait

In v7 (Helm), you parameterize the hostname in a values file. In Phase 9 (CI/CD), you point to a real domain.

---

> **▶ STOP — do this now**
>
> Before applying manifests, read each file and predict what it creates:
> ```bash
> ls /workspaces/aois-system/k8s/
> ```
> For each `.yaml` file, read it and write down:
> - What kind of k8s object does it create? (`kind:` field)
> - What namespace does it go into?
> - What is the purpose of this object in making AOIS accessible from the internet?
>
> Then apply them in order:
> ```bash
> kubectl apply -f /workspaces/aois-system/k8s/namespace.yaml
> kubectl get namespace aois
> kubectl apply -f /workspaces/aois-system/k8s/secret.yaml
> kubectl get secret -n aois
> kubectl apply -f /workspaces/aois-system/k8s/deployment.yaml
> kubectl rollout status deployment/aois -n aois
> ```
> Watch the deployment rollout — this is the pod lifecycle: Pending → ContainerCreating → Running. If it stays in Pending, read the events: `kubectl describe pod -n aois`.

---

## Part 7 — cert-manager and Let's Encrypt

### Install cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.yaml
```

This installs cert-manager into the `cert-manager` namespace. It creates three pods:
- `cert-manager` — the main controller
- `cert-manager-cainjector` — injects CA data into webhooks
- `cert-manager-webhook` — validates cert-manager resources

Wait for it:
```bash
kubectl rollout status deployment/cert-manager -n cert-manager
kubectl rollout status deployment/cert-manager-webhook -n cert-manager
```

Expected:
```
deployment "cert-manager" successfully rolled out
deployment "cert-manager-webhook" successfully rolled out
```

### ClusterIssuer

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your@email.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          ingressClassName: traefik
```

A ClusterIssuer defines how cert-manager gets certificates. This one uses ACME (the Let's Encrypt protocol) with HTTP-01 challenge validation:

1. cert-manager sees the Ingress annotated with `letsencrypt-prod`
2. cert-manager asks Let's Encrypt: "I want a cert for `aois.46.225.235.51.nip.io`"
3. Let's Encrypt says: "Prove you control it — serve this token at `http://aois.46.225.235.51.nip.io/.well-known/acme-challenge/TOKEN`"
4. cert-manager creates a temporary Ingress route that serves the token via Traefik
5. Let's Encrypt makes an HTTP request to verify
6. Verification passes → Let's Encrypt issues the certificate
7. cert-manager stores the certificate in Secret `aois-tls`
8. cert-manager auto-renews 30 days before expiry — you never manually renew

This entire flow happens automatically when you apply the Ingress. You do not touch it again.

### Verify the certificate

```bash
kubectl get certificate -n aois
```

Expected:
```
NAME       READY   SECRET     AGE
aois-tls   True    aois-tls   1m
```

`READY: True` means Let's Encrypt issued the certificate and it is stored in the `aois-tls` Secret.

If `READY: False`, check what is happening:
```bash
kubectl describe certificate aois-tls -n aois
kubectl get challenges -n aois    # shows HTTP-01 challenge status
```

---

## Part 8 — Creating the image pull secret

Your GHCR image is private. Kubernetes needs credentials to pull it. Create a docker-registry Secret:

```bash
kubectl create secret docker-registry ghcr-secret \
  --namespace aois \
  --docker-server=ghcr.io \
  --docker-username=kolinzking \
  --docker-password=YOUR_GITHUB_TOKEN
```

This creates a Secret of type `kubernetes.io/dockerconfigjson` — the Kubernetes standard format for registry credentials. The Deployment references it via `imagePullSecrets`.

Alternatively, make the GHCR package public (GitHub → your package → Package settings → Change visibility to Public) and remove `imagePullSecrets` from the Deployment.

---

## Running and testing v6

### Apply everything

```bash
kubectl apply -f /workspaces/aois-system/k8s/namespace.yaml
kubectl apply -f /workspaces/aois-system/k8s/secret.yaml
kubectl apply -f /workspaces/aois-system/k8s/deployment.yaml
kubectl apply -f /workspaces/aois-system/k8s/service.yaml
kubectl apply -f /workspaces/aois-system/k8s/clusterissuer.yaml
kubectl apply -f /workspaces/aois-system/k8s/ingress.yaml
```

### Watch the pod come up

```bash
kubectl get pods -n aois -w
```

Expected sequence:
```
NAME                    READY   STATUS              RESTARTS   AGE
aois-6c76df6fd7-vpx6w   0/1     ContainerCreating   0          5s
aois-6c76df6fd7-vpx6w   0/1     Running             0          15s
aois-6c76df6fd7-vpx6w   1/1     Running             0          20s
```

`0/1 Running` → readiness probe hasn't passed yet.
`1/1 Running` → readiness probe passed, pod is receiving traffic.

### Check the ingress

```bash
kubectl get ingress -n aois
```

Expected:
```
NAME   CLASS     HOSTS                       ADDRESS         PORTS     AGE
aois   traefik   aois.46.225.235.51.nip.io   46.225.235.51   80, 443   1m
```

`ADDRESS` shows the server IP — Traefik is routing to this Ingress.

### Test health

```bash
curl https://aois.46.225.235.51.nip.io/health
```

Expected:
```json
{"status":"ok","tiers":["premium","standard","fast","local"]}
```

### Test analysis

```bash
curl -s -X POST https://aois.46.225.235.51.nip.io/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service memory_limit=512Mi restarts=14"}' \
  | python3 -m json.tool
```

Expected: full JSON analysis with `severity`, `suggested_action`, `confidence`, `provider`, `cost_usd`.

### View logs

```bash
kubectl logs -n aois -l app=aois --tail=50
```

Expected: uvicorn access logs for each request.

### Check all resources

```bash
kubectl get all -n aois
```

Expected:
```
NAME                        READY   STATUS    RESTARTS   AGE
pod/aois-6c76df6fd7-vpx6w   1/1     Running   0          5m

NAME           TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)   AGE
service/aois   ClusterIP   10.43.x.x     <none>        80/TCP    5m

NAME                   READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/aois   1/1     1            1           5m

NAME                              DESIRED   CURRENT   READY   AGE
replicaset.apps/aois-6c76df6fd7   1         1         1       5m
```

---

> **▶ STOP — do this now**
>
> With AOIS running on Kubernetes, trace the full request path from your terminal to the response:
> ```bash
> # Step 1: Your curl → Hetzner server IP
> curl -v https://aois.46.225.235.51.nip.io/health 2>&1 | grep -E "< HTTP|SSL|Connected|TLS"
>
> # Step 2: The Ingress → Service → Pod routing
> kubectl get ingress -n aois    # shows: host → service mapping
> kubectl get service -n aois    # shows: service → port mapping
> kubectl get endpoints -n aois  # shows: service → pod IP mapping
>
> # Step 3: Prove the pod is answering
> POD=$(kubectl get pod -n aois -l app=aois -o jsonpath='{.items[0].metadata.name}')
> kubectl exec -n aois $POD -- wget -qO- http://localhost:8000/health
> ```
> You just traced the request through: nip.io DNS → Hetzner IP → k3s Ingress → Service → Pod → FastAPI.
> This is the same path on AWS EKS, just with an AWS Load Balancer instead of the Hetzner IP. The Kubernetes concepts are identical.

---

## Common Mistakes

**Forgetting `-n aois` — commands run in the wrong namespace** *(recognition)*
Without `-n namespace`, kubectl defaults to the `default` namespace. Every AOIS resource is in the `aois` namespace. You will spend time confused about why kubectl shows nothing when everything is running fine. Set `kubectl config set-context --current --namespace=aois` to make `aois` the default for this context — then you can omit `-n aois` in most commands.

*(recall — trigger it)*
```bash
# Run this while AOIS is deployed and running
kubectl get pods          # no -n flag
```
Expected:
```
No resources found in default namespace.
```
AOIS is running perfectly — you are just looking in the wrong place. Fix:
```bash
kubectl get pods -n aois
# NAME                    READY   STATUS    RESTARTS   AGE
# aois-7d9f4b8c6-xk2mj   1/1     Running   0          12m
```
Permanently fix by setting the default namespace for this context:
```bash
kubectl config set-context --current --namespace=aois
kubectl get pods    # now works without -n
```

---

**`ImagePullBackOff` — the image pull secret is wrong** *(recognition)*
When the pod cannot pull the image, it shows `ImagePullBackOff`. The most common cause: the `ghcr-secret` was created with the wrong GitHub token (expired, wrong scope, wrong username). Verify:
```bash
kubectl get secret ghcr-secret -n aois -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d
```
Confirm the `auth` field decodes to `username:token` and the token has `read:packages` scope on GitHub.

*(recall — trigger it)*
```bash
# Create a secret with a deliberately bad token
kubectl create secret docker-registry ghcr-secret-test \
  --docker-server=ghcr.io \
  --docker-username=kolinzking \
  --docker-password=BADTOKEN \
  -n aois

# Patch the deployment to use this bad secret
kubectl patch deployment aois -n aois \
  -p '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"ghcr-secret-test"}]}}}}'

# Watch the pod status
kubectl get pods -n aois -w
```
Expected output after patch:
```
NAME                    READY   STATUS             RESTARTS
aois-new-pod            0/1     ImagePullBackOff   0
```
Diagnosis:
```bash
kubectl describe pod -n aois -l app=aois | grep -A5 "Events"
# Failed to pull image: unauthorized: unauthenticated
```
Fix: recreate the secret with a valid token that has `read:packages` scope, then roll back the patch. One memory hook: **ImagePullBackOff always means authentication or the image tag doesn't exist — check both.**

---

**Liveness probe too aggressive — kills healthy pods during startup** *(recognition)*
If `initialDelaySeconds` is too small (e.g., 5 seconds) and AOIS takes 12 seconds to start, the liveness probe fails three times before the app is ready. Kubernetes kills the pod and restarts it — which fails again. This looks identical to an application crash from the outside.

*(recall — trigger it)*
```yaml
# Apply this deliberately aggressive probe to see the crash loop
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 1    # <-- too small
  periodSeconds: 3
  failureThreshold: 1       # <-- fails on first miss
```
```bash
kubectl apply -f - <<'EOF'
# paste the above into your deployment
EOF
kubectl get pods -n aois -w
```
Expected:
```
NAME              READY   STATUS             RESTARTS
aois-pod          0/1     Running            0
aois-pod          0/1     Running            1          # killed and restarted
aois-pod          0/1     CrashLoopBackOff   2
```
Fix:
```yaml
initialDelaySeconds: 20    # 1.5× observed startup time
failureThreshold: 3        # tolerate 3 consecutive failures
```
Measure your actual startup time first: `kubectl logs -n aois -l app=aois | grep "Application startup complete"` and note the timestamp delta.

---

**Editing base64-encoded Secrets by hand** *(recognition)*
`kubectl edit secret` shows base64-encoded values. A trailing newline, a missed `=` padding character, or any typo in a base64 string produces a silently different decoded value — your application gets a garbled API key and fails with an authentication error that looks unrelated to the secret edit.

*(recall — trigger it)*
```bash
# See what hand-editing looks like
kubectl get secret aois-secrets -n aois -o yaml
# data:
#   ANTHROPIC_API_KEY: c2stYW50LVJFQUFLRVK=    # hard to spot errors here
```
Manually base64-encode a string with a common mistake:
```bash
echo "my-api-key" | base64      # produces: bXktYXBpLWtleQo=
echo -n "my-api-key" | base64   # produces: bXktYXBpLWtleQ==
```
The first has a trailing newline in the decoded value — your application gets `"my-api-key\n"` instead of `"my-api-key"`. An auth header with a newline is silently rejected.

Fix — the safe pattern for updating secrets:
```bash
kubectl create secret generic aois-secrets \
  --from-literal=ANTHROPIC_API_KEY="sk-ant-real-key" \
  --dry-run=client -o yaml | kubectl apply -f -
```
`--dry-run=client -o yaml` generates correct base64 without manual encoding. `kubectl apply` applies it idempotently.

---

**`kubectl apply` after Helm takes ownership** *(recognition)*
Once Helm manages AOIS (v7+), using `kubectl apply` on the same resources creates state Helm does not know about. On the next `helm upgrade`, Helm either overwrites your manual change or enters a conflict state where the live resource differs from both the Helm chart and your manual apply.

*(recall — trigger it)*
```bash
# After v7 Helm install, manually edit the deployment replicas
kubectl scale deployment aois --replicas=3 -n aois
kubectl get deployment aois -n aois   # shows 3 replicas

# Now run helm upgrade
helm upgrade aois ./charts/aois -n aois

# Check replicas after upgrade
kubectl get deployment aois -n aois   # back to whatever values.yaml says
```
Expected: Helm has silently overwritten the manual change. The `kubectl scale` is gone. If `values.yaml` says `replicaCount: 1`, you are back to 1.

Fix: after v7, all configuration changes go through `values.yaml` and `helm upgrade`. Never `kubectl apply` or `kubectl scale` Helm-managed resources. The git file is the truth, not the live cluster.

---

## Troubleshooting

**Pod stuck in `ImagePullBackOff`:**
```bash
kubectl describe pod -n aois -l app=aois
```
Look for `Failed to pull image`. Either:
- The `ghcr-secret` is missing or has wrong credentials → recreate it
- The image tag doesn't exist → verify with `docker manifest inspect ghcr.io/kolinzking/aois:v6`
- The GHCR package is private and `imagePullSecrets` is missing from the Deployment

**Pod in `CrashLoopBackOff`:**
```bash
kubectl logs -n aois -l app=aois --previous
```
The `--previous` flag shows logs from the last crashed container. Usually: missing environment variable, import error, port conflict.

**Certificate stuck at `READY: False`:**
```bash
kubectl describe certificaterequest -n aois
kubectl get challenges -n aois
```
Common causes:
- Port 80 not open on the server firewall → in Hetzner Cloud, check the Firewall rules
- Let's Encrypt rate limits (5 failures per domain per hour) → wait an hour

**Ingress has no ADDRESS:**
```bash
kubectl get pods -n kube-system | grep traefik
```
Traefik must be running. If not: `kubectl logs -n kube-system -l app.kubernetes.io/name=traefik`

**kubectl connection refused from Codespaces:**
```bash
curl -k https://46.225.235.51:6443/version
```
If this fails, port 6443 is blocked. In Hetzner Cloud → Firewalls, ensure port 6443 is open for your Codespaces IP, or open it for `0.0.0.0/0` temporarily.

---

## Key kubectl commands for daily use

```bash
# See everything in the aois namespace
kubectl get all -n aois

# Watch pods in real time
kubectl get pods -n aois -w

# View pod logs (live)
kubectl logs -n aois -l app=aois -f

# Describe a pod (events, probe status, resource usage)
kubectl describe pod -n aois POD_NAME

# Execute a command inside the running pod
kubectl exec -it -n aois POD_NAME -- /bin/sh

# Restart the deployment (pull fresh pod)
kubectl rollout restart deployment/aois -n aois

# Scale to 3 replicas
kubectl scale deployment/aois -n aois --replicas=3

# Apply a changed manifest
kubectl apply -f k8s/deployment.yaml

# Delete everything and start fresh
kubectl delete namespace aois
```

---

## What v6 does not have (solved in later versions)

| Gap | Fixed in |
|-----|---------|
| Manual image build + push — no CI/CD | v28: GitHub Actions builds and pushes on every commit |
| Secret stored in a file on disk — not ideal | v27: HashiCorp Vault, External Secrets Operator |
| No autoscaling — always 1 replica | v9: KEDA scales on Kafka consumer lag |
| No GitOps — `kubectl apply` is manual | v8: ArgoCD deploys on git push |
| Single node — no high availability | v12: EKS multi-node cluster |
| No observability — only pod logs | v16: OpenTelemetry, Prometheus, Grafana |
| Helm values not parameterized | v7: full Helm chart with per-environment values |

---

## Summary: what changed across v5 → v6

| Concern | v5 (Docker Compose) | v6 (Kubernetes) |
|---------|--------------------|--------------------|
| Where it runs | Your laptop | Hetzner VPS (always on) |
| How it starts | `docker compose up` | `kubectl apply` |
| Accessible from internet | No | Yes — real HTTPS URL |
| TLS certificate | No | Auto-issued by Let's Encrypt, auto-renewed |
| Health monitoring | No | Liveness + readiness probes |
| Restart on crash | `restart: always` | Kubernetes controller (with backoff) |
| Image storage | Local | GHCR (internet-accessible registry) |
| Config/secrets | `.env` file | Kubernetes Secret |
| Scaling | Manual | `replicas: N` → v9 HPA/KEDA |

---

## Connection to later phases

- **v7 (Helm)**: The raw YAML manifests in `k8s/` become a Helm chart. `values.yaml` replaces hardcoded strings like the hostname and replica count. `helm install aois ./charts/aois -f values.prod.yaml` replaces `kubectl apply -f k8s/`.
- **v8 (ArgoCD)**: ArgoCD watches the git repo. When you push a change to `k8s/` or the Helm chart, ArgoCD detects the diff and applies it automatically. You stop running `kubectl apply` manually.
- **v9 (KEDA)**: The `replicas: 1` in the Deployment becomes dynamic — KEDA scales it based on Kafka consumer lag. When log volume spikes, AOIS scales up. When idle, it scales to zero.
- **v12 (EKS)**: The same manifests deploy to AWS EKS with minor changes (`ingressClassName: alb` instead of `traefik`, IAM for secrets instead of `secret.yaml`). The pattern is identical.
- **The principle**: Every production Kubernetes deployment follows this exact pattern — Namespace, Secret, Deployment, Service, Ingress. You now understand each piece from first principles.

---

## Mastery Checkpoint

You are running a real production Kubernetes cluster. These exercises prove you can operate it with confidence.

**1. Read every resource with understanding**
For each resource type in `k8s/`:
```bash
cat k8s/deployment.yaml
```
For each field you see, explain what it does. Focus on:
- `resources.requests` vs `resources.limits` — what happens when a pod exceeds limits?
- `livenessProbe` vs `readinessProbe` — when does Kubernetes kill a pod vs stop routing traffic?
- `imagePullPolicy: Always` — why is this important for a deployment that uses mutable tags like `:v6`?
- `replicas: 1` — what happens to AOIS if you set this to 3? (Try it: `kubectl scale deployment/aois -n aois --replicas=3`, then `kubectl get pods -n aois`)

**2. Simulate a pod failure and recovery**
With AOIS running (1 replica), kill the pod:
```bash
kubectl delete pod -n aois $(kubectl get pods -n aois -o jsonpath='{.items[0].metadata.name}')
```
Watch what happens:
```bash
kubectl get pods -n aois -w
```
The Deployment controller should create a new pod within seconds. The `kubectl delete pod` did not affect the Deployment — the Deployment's `replicas: 1` is the desired state, and the controller immediately works to restore it. This is Kubernetes self-healing.

Now test that AOIS is still responding:
```bash
curl https://aois.46.225.235.51.nip.io/health
```

**3. Deploy an update with zero downtime**
Change the image tag in `deployment.yaml` to a non-existent tag (e.g., `aois:invalid-tag`). Apply it:
```bash
kubectl apply -f k8s/deployment.yaml
kubectl get pods -n aois -w
```
Watch the rolling update: Kubernetes starts the new pod, it fails to pull the image, it stays in `ImagePullBackOff`. But the OLD pod is still running — traffic still flows.
```bash
curl https://aois.46.225.235.51.nip.io/health  # still responds from old pod
```
Revert to the working tag and apply again. Watch Kubernetes drain the bad pod and bring back the good one. This is `RollingUpdate` strategy — Kubernetes never kills the old version until the new version is healthy.

**4. Understand the full certificate chain**
```bash
kubectl describe certificate aois-tls -n aois
kubectl get secret aois-tls -n aois -o yaml
```
The second command shows the TLS certificate and key (base64 encoded) stored in the Secret. This is what Traefik reads to terminate TLS.

Now explain from memory: how does a request from your browser get decrypted? (Browser sends TLS ClientHello → Traefik presents the certificate from the Secret → TLS handshake completes → HTTP request decrypted → forwarded to AOIS pod over HTTP internally)

**5. kubectl as your production debugger**
Simulate these production scenarios and use only kubectl to diagnose:
- **Scenario 1**: AOIS is returning 500 errors. Diagnose: `kubectl logs -n aois -l app=aois --tail=100`
- **Scenario 2**: Pod keeps restarting. Diagnose: `kubectl describe pod -n aois <name>` and `kubectl logs --previous`
- **Scenario 3**: Certificate is not renewing. Diagnose: `kubectl describe certificate` and `kubectl get challenges`
- **Scenario 4**: Response is slow. Diagnose: `kubectl top pod -n aois` (resource usage)

For each scenario, write the exact command sequence you would run and what output would indicate the problem.

**6. The mental model test**
Without looking at the YAML files, draw the complete network path for a request from your laptop to the AOIS pod:

```
Your browser → ? → ? → ? → ? → AOIS container:8000
```

Fill in each hop with the Kubernetes resource responsible. (Answer: DNS → Hetzner server IP → Traefik (Ingress controller) → Service (ClusterIP) → Pod (container port 8000))

Verify your understanding: what would break if you deleted the Service? (Traefik cannot reach the pod — traffic stops.) What would break if you deleted the Ingress? (External traffic has no route in — the domain stops working, but the pod and Service still exist.)

**The mastery bar**: You can deploy a service to Kubernetes from scratch, debug any failure state using kubectl alone, explain the network path from browser to container, and understand what each resource type's job is. When you join a company and see their k8s setup, none of it will be mysterious — you will recognize every resource type and know what to look for when something breaks.
