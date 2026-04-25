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
# Linux aois 6.x.x-xx-generic x86_64 GNU/Linux

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
aois   Ready    control-plane,master   1m    v1.34.x+k3s1
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
aois   Ready    control-plane,master   5m    v1.34.x+k3s1
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

## Part 10 — SPIFFE/SPIRE: Workload Identity (April 2026 Retrofit)

*This section was added after the initial v6 build. The original deployment used a static
`k8s/secret.yaml` with long-lived API keys stored as base64-encoded values in a Kubernetes
Secret. Any principal with `kubectl get secret` access could decode them in seconds. SPIFFE/SPIRE
closes this gap by giving each workload a cryptographic identity that other services can verify —
no static credentials required for service-to-service communication.*

### The problem with static k8s Secrets

```bash
kubectl get secret aois-secrets -n aois -o jsonpath='{.data.ANTHROPIC_API_KEY}' | base64 -d
# Any kubectl user with get/list permission on Secrets in the aois namespace
# receives the raw API key. In a shared cluster this is unacceptable.
```

A Kubernetes Secret is base64, not encrypted. The secret is as secure as the RBAC that protects
it — and RBAC is routinely over-permissioned in practice. Long-lived API keys also cannot be
audited per-workload: if the key leaks, you cannot tell which service used it.

SPIFFE/SPIRE replaces "who are you?" with cryptographic proof. Each pod receives a short-lived
X.509 certificate (SVID) that is automatically renewed. Services verify each other's identity
using the trust bundle rather than matching a shared secret.

### What SPIFFE and SPIRE are

**SPIFFE** (Secure Production Identity Framework For Everyone) is an open standard for workload
identity. The key concept is the SPIFFE ID — a URI that uniquely identifies a workload:
`spiffe://aois.local/ns/aois/sa/aois`. This is AOIS's cryptographic identity in the cluster.

**SPIRE** is the production implementation of SPIFFE. It runs as:
- **SPIRE Server**: issues SVIDs (X.509 certificates) to attested workloads. One per cluster.
- **SPIRE Agent**: runs on every node (DaemonSet). Attests workloads on its node and delivers
  SVIDs via the SPIFFE Workload API socket.

The key distinction from static secrets: SVIDs expire in hours (TTL: 3600s in AOIS's config),
are automatically rotated, and are tied to the specific workload's identity selectors — not a
shared credential anyone can copy.

### Node attestation on k3s (the critical decision)

Before agents can issue SVIDs, they must prove their own identity to the SPIRE server — this is
node attestation.

Cloud-specific attestors (`aws_iid`, `gcp_iit`) use cloud metadata APIs that do not exist on
a self-managed Hetzner VPS. The correct attestor for k3s is **`k8s_psat`** (Projected Service
Account Tokens):

1. The agent pod mounts a projected service account token with audience `spire-server`
2. On startup, the agent presents this token to the SPIRE server
3. The server validates it via the Kubernetes TokenReview API
4. If valid, the server issues the agent a node SVID

This works on any Kubernetes distribution, including k3s, because it only requires the
standard Kubernetes TokenReview API.

### Workload attestation on k3s (the k3s-specific fix)

Once the agent has a node identity, it attests individual workloads (pods) using the k8s
workload attestor. The default behavior queries the kubelet API for pod metadata. This fails
on k3s because:

- The kubelet read-only port (10255) is **disabled** on k3s by default
- The authenticated kubelet port (10250) requires client certificate auth that the SPIRE agent
  cannot provide

**Fix**: `use_new_container_locator = true` in the workload attestor config.

The new container locator reads `/proc/<pid>/cgroup` (available because the DaemonSet runs with
`hostPID: true`) to extract the container ID, then queries the **k8s API server** (not the
kubelet) for pod metadata. Since the SPIRE agent already has a service account with `pods:get`
permission, no additional auth is needed.

```
Workload connects to agent socket
↓
Agent reads /proc/<pid>/cgroup → container ID: cri-containerd-27be5c...
↓
Agent queries k8s API: GET /api/v1/pods?fieldSelector=spec.nodeName=ubuntu-16gb
↓
Finds pod containing container ID → namespace=aois, serviceaccount=default
↓
Selectors match entry: k8s:ns:aois + k8s:sa:default
↓
SPIRE server issues SVID: spiffe://aois.local/ns/aois/sa/aois
```

### Deploying SPIRE to the Hetzner cluster

All manifests live in `k8s/spire/`. Deploy in this order:

```bash
# 1. Namespace and RBAC
kubectl apply -f k8s/spire/namespace.yaml
kubectl apply -f k8s/spire/server-account.yaml
kubectl apply -f k8s/spire/agent-account.yaml

# 2. Server config and StatefulSet
kubectl apply -f k8s/spire/server-configmap.yaml
kubectl apply -f k8s/spire/server-statefulset.yaml

# 3. Wait for server to be ready
kubectl wait --for=condition=ready pod/spire-server-0 -n spire --timeout=60s
# Expected: pod/spire-server-0 condition met

# 4. Bootstrap the trust bundle (two-step: server starts, then bundle is extracted)
kubectl exec -n spire spire-server-0 -- \
  /opt/spire/bin/spire-server bundle show -format pem | \
  kubectl create configmap spire-bundle -n spire \
    --from-file=bundle.crt=/dev/stdin \
    --dry-run=client -o yaml | kubectl apply -f -
# Expected: configmap/spire-bundle configured

# 5. Deploy agent (reads bundle from configmap for bootstrap)
kubectl apply -f k8s/spire/agent-configmap.yaml
kubectl apply -f k8s/spire/agent-daemonset.yaml
kubectl wait --for=condition=ready pod -l app=spire-agent -n spire --timeout=90s
# Expected: pod/spire-agent-xxxxx condition met
```

Verify both are running:
```bash
kubectl get pods -n spire
# Expected:
# NAME             READY   STATUS    RESTARTS   AGE
# spire-agent-k5jbk   1/1     Running   0          2m
# spire-server-0      1/1     Running   0          5m
```

Verify node attestation succeeded:
```bash
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server agent list
# Expected:
# Found 1 attested agent:
# SPIFFE ID         : spiffe://aois.local/spire/agent/k8s_psat/aois-cluster/<pod-uid>
# Attestation type  : k8s_psat
# Expiration time   : 2026-04-24 23:46:58 +0000 UTC
# Can re-attest     : true
```

### Registering the AOIS workload

A workload registration entry tells SPIRE: "any pod matching these selectors should receive
this SPIFFE ID, attested by this agent."

```bash
# Get the agent's SPIFFE ID first
AGENT_ID=$(kubectl exec -n spire spire-server-0 -- \
  /opt/spire/bin/spire-server agent list 2>/dev/null | \
  grep 'SPIFFE ID' | awk '{print $NF}')

kubectl exec -n spire spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://aois.local/ns/aois/sa/aois \
  -parentID $AGENT_ID \
  -selector k8s:ns:aois \
  -selector k8s:sa:default \
  -ttl 3600
# Expected:
# Entry ID         : 2319e545-7fcc-4f00-ae13-6423c218f851
# SPIFFE ID        : spiffe://aois.local/ns/aois/sa/aois
# Parent ID        : spiffe://aois.local/spire/agent/k8s_psat/aois-cluster/<pod-uid>
# Selector         : k8s:ns:aois
# Selector         : k8s:sa:default
```

Selectors:
- `k8s:ns:aois` — pod must be in the `aois` namespace
- `k8s:sa:default` — pod must use the `default` service account

Any pod in `aois` namespace with the default SA receives `spiffe://aois.local/ns/aois/sa/aois`.
This is how Kubernetes RBAC maps to SPIFFE identity.

### Delivering the SVID to AOIS pods

The SPIRE agent exposes the SPIFFE Workload API at `/run/spire/sockets/agent.sock` on the host.
AOIS pods access it via a `hostPath` volume mount:

```yaml
# k8s/deployment.yaml (SPIRE socket mount added in this retrofit)
volumeMounts:
- name: spire-agent-socket
  mountPath: /var/run/secrets/workload-api
  readOnly: true
volumes:
- name: spire-agent-socket
  hostPath:
    path: /run/spire/sockets
    type: Directory
```

### Verify SVID issuance

```bash
# Run a test pod in the aois namespace with the socket mounted
kubectl run spire-test \
  --image=ghcr.io/spiffe/spire-agent:1.10.0 \
  --restart=Never \
  --namespace=aois \
  --overrides='{
    "spec": {
      "containers": [{"name":"spire-test","image":"ghcr.io/spiffe/spire-agent:1.10.0",
        "command":["/opt/spire/bin/spire-agent","api","fetch","x509",
                   "-socketPath","/var/run/secrets/workload-api/agent.sock"],
        "volumeMounts":[{"name":"sock","mountPath":"/var/run/secrets/workload-api"}]}],
      "volumes":[{"name":"sock","hostPath":{"path":"/run/spire/sockets","type":"Directory"}}]
    }
  }'

kubectl logs spire-test -n aois
# Expected:
# Received 1 svid after 1.391163969s
#
# SPIFFE ID:       spiffe://aois.local/ns/aois/sa/aois
# SVID Valid After: 2026-04-24 22:56:07 +0000 UTC
# SVID Valid Until: 2026-04-24 23:56:17 +0000 UTC
# CA #1 Valid After: 2026-04-24 22:44:50 +0000 UTC
# CA #1 Valid Until: 2026-04-25 22:45:00 +0000 UTC

kubectl delete pod spire-test -n aois
```

This is the workload identity gap from the April 2026 audit, closed.

### What SPIFFE/SPIRE does not yet replace

SPIFFE/SPIRE provides service-to-service identity. The static API keys for external services
(Anthropic, OpenAI) remain in `aois-secrets`. The path to replacing them is:

```
AOIS pod → SPIRE SVID (X.509) → Vault JWT auth → dynamic API key lease
```

HashiCorp Vault (covered in v5) accepts SPIFFE SVIDs as authentication tokens via its JWT
auth method. Once Vault is deployed, AOIS can fetch short-lived API credentials at startup
rather than reading from a static Secret. This is the production pattern for external API keys
in organizations running SPIRE.

For the current Hetzner setup, the live cluster uses the manually applied static Secret. The
external key rotation path is a future improvement when Vault is added to the cluster.

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

**cert-manager certificate stuck in Pending — missing ClusterIssuer** *(recognition)*
If `kubectl describe certificate aois-tls -n aois` shows `Waiting for HTTP-01 challenge` but the challenge never completes, the most common causes are: the ClusterIssuer doesn't exist, or port 80 is blocked on the server so Let's Encrypt cannot reach it for validation. Let's Encrypt validates via HTTP before issuing TLS — it must be reachable from the internet.

*(recall — trigger it)*
```bash
# Check if the ClusterIssuer exists
kubectl get clusterissuer
# If empty output, the ClusterIssuer was never applied — cert-manager has no issuer to use

# Check the certificate status
kubectl describe certificate aois-tls -n aois | grep -A10 "Status"

# Check if challenges were created (they represent Let's Encrypt's HTTP-01 attempts)
kubectl get challenges -n aois
kubectl describe challenge -n aois
```
Expected when ClusterIssuer is missing:
```
Events:
  Warning  IssuerNotFound  cert-manager  Referenced "ClusterIssuer" not found: "letsencrypt-prod"
```
Expected when port 80 is blocked:
```
Events:
  Warning  PresentChallenge  cert-manager  Error presenting challenge: HTTP-01 challenge failed
```
Diagnose port 80:
```bash
# From a machine outside your network, verify port 80 reaches the server
curl -v http://46.225.235.51/.well-known/acme-challenge/test
# Must not return "Connection refused" — must reach Traefik
```
Fix: In Hetzner Cloud console → Firewalls → verify port 80 is open (not just 443). cert-manager needs both.
Also verify: `dig aois.46.225.235.51.nip.io` resolves to `46.225.235.51` — nip.io must be working.

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


## Build-It-Blind Challenge

Close the notes. From memory: write the Kubernetes Deployment, Service, and Ingress manifests for AOIS — correct namespace, image pull secret reference, resource limits (256Mi/512Mi, 100m/500m), liveness and readiness probes at `/health`, TLS via cert-manager annotation. 20 minutes.

```bash
kubectl apply -f deployment.yaml --dry-run=client
# No errors
kubectl apply -f service.yaml --dry-run=client
kubectl apply -f ingress.yaml --dry-run=client
```

---

## Failure Injection

Deploy with a deliberately wrong image tag and watch the pod fail:

```yaml
image: ghcr.io/kolinzking/aois:doesnotexist
```

```bash
kubectl get pods -n aois -w
# STATUS: ErrImagePull → ImagePullBackOff
kubectl describe pod <pod-name> -n aois | grep -A5 Events
# Read the exact failure reason
```

Now fix the image tag. How long does Kubernetes take to recover once the correct image is available? That recovery time is your deployment MTTR for image errors.

---

## Osmosis Check

1. The AOIS pod needs the `ANTHROPIC_API_KEY` at runtime. You stored it in a Kubernetes Secret. What happens to the running pod if you rotate the Secret value — does the pod pick up the new value automatically or does it require a restart?
2. The readiness probe fails because AOIS takes 8 seconds to start (model loading). The probe has `initialDelaySeconds: 5`. What does Kubernetes do to incoming traffic during those 3 seconds of probe failure? (v0.4 HTTP + v0.6 FastAPI startup)

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

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### Kubernetes (k8s / k3s)

| Layer | |
|---|---|
| **Plain English** | A system that manages running your application across multiple servers — automatically restarting crashed containers, distributing load, and deploying new versions without downtime. |
| **System Role** | Kubernetes is the production runtime for AOIS. Every service — the FastAPI app, Kafka, ArgoCD, Falco, KEDA — runs as a pod managed by Kubernetes. k3s is the lightweight distribution running on the Hetzner VPS. When KEDA scales AOIS from 1 to 5 pods under load, Kubernetes is what actually starts and stops those pods. |
| **Technical** | A container orchestration system. Core objects: `Pod` (one or more containers), `Deployment` (manages replica sets), `Service` (stable network endpoint for pods), `Ingress` (routes external traffic to services), `ConfigMap`/`Secret` (configuration injection), `Namespace` (logical cluster partitioning). The API server is the control plane; kubelet is the agent running on each node. |
| **Remove it** | Without Kubernetes, AOIS is a single Docker container on one server. If the server crashes, AOIS is down until manually restarted. Scaling requires manual `docker run` commands. Deploying a new version requires SSH + manual steps. k8s automates all of this — the "ops" in DevOps. |

**Say it at three levels:**
- *Non-technical:* "Kubernetes is the manager that keeps all the application containers running. If one crashes, it restarts it. If traffic spikes, it starts more copies. It works across many servers at once."
- *Junior engineer:* "A Deployment says 'run 2 replicas of aois:v6'. k8s ensures exactly 2 pods are running at all times — if one dies, it starts another. A Service gives those pods a stable IP. An Ingress routes `aois.46.225.235.51.nip.io` to that Service. `kubectl get pods -n aois` shows what's running."
- *Senior engineer:* "The k8s control loop is the mental model: desired state (manifests) vs actual state (running cluster) — the controller reconciles continuously. This is also how ArgoCD works (v8). k3s removes the HA control plane and uses SQLite instead of etcd — fine for a single-node Hetzner cluster, not for production multi-node. Resource requests vs limits: requests are what the scheduler uses to place pods; limits are the ceiling. Setting requests == limits is the correct pattern for predictable scheduling."

---

### Terraform

| Layer | |
|---|---|
| **Plain English** | A tool that creates and manages cloud infrastructure by reading configuration files — so you can rebuild your entire server setup from scratch with one command, and track changes in git like code. |
| **System Role** | Terraform provisions the Hetzner VPS that runs k3s. `terraform apply` creates the server, sets up SSH keys, and configures the firewall. The infrastructure is defined in `main.tf` — if the server is destroyed, `terraform apply` recreates it identically. In v12, Terraform provisions the EKS cluster on AWS. |
| **Technical** | A declarative Infrastructure as Code tool. Resources (servers, networks, DNS records) are declared in HCL (HashiCorp Configuration Language). Terraform maintains a state file that tracks what it has created. `terraform plan` shows what will change before applying. `terraform apply` creates/updates resources to match the declared state. `terraform destroy` removes everything. |
| **Remove it** | Without Terraform, infrastructure is created manually via cloud UIs — undocumented, unreproducible, and untrackable. When the Hetzner server is eventually replaced or a second node added, the process must be remembered and repeated manually. With Terraform, the infrastructure is code: versioned, reviewable, and reproducible. |

**Say it at three levels:**
- *Non-technical:* "Terraform is a recipe for infrastructure. I describe what I want (a server with these specs in this region), and Terraform creates it. If something is destroyed, I run the recipe again and it rebuilds everything."
- *Junior engineer:* "`resource 'hcloud_server' 'aois' { server_type = 'cpx21', image = 'ubuntu-24.04' }` — that's the entire server declaration. `terraform plan` shows what it will create/change/destroy. `terraform apply` executes it. The state file tracks what Terraform manages. Never manually edit infra that Terraform manages — the next `terraform apply` will overwrite it."
- *Senior engineer:* "Terraform's state file is the source of truth — it must be stored remotely (S3 + DynamoDB for locking) in team environments. State drift (manually changed infra) is the primary operational hazard; `terraform refresh` detects it. For AOIS, the Hetzner VPS Terraform state is local (solo project) — in a team environment this must be remote. Pulumi (v30) is Terraform's competitor with real programming language support — loops, functions, and conditionals that HCL cannot express."

---

### cert-manager + Let's Encrypt

| Layer | |
|---|---|
| **Plain English** | Automatically obtains and renews HTTPS certificates for your domain, so the application is always accessible over a secure connection without any manual certificate management. |
| **System Role** | cert-manager runs in the k3s cluster and manages the TLS certificate for `aois.46.225.235.51.nip.io`. It requests a certificate from Let's Encrypt, stores it as a Kubernetes Secret, and automatically renews it before it expires. Traefik uses this Secret to serve AOIS over HTTPS. Without it, AOIS is HTTP only. |
| **Technical** | A Kubernetes controller that automates X.509 certificate management. `Issuer`/`ClusterIssuer` resources define where to get certificates (Let's Encrypt ACME server). `Certificate` resources request a cert for a domain. The ACME HTTP-01 challenge: Let's Encrypt sends an HTTP request to a token URL — cert-manager serves the response, proving domain control. Certs are stored as k8s `Secrets` and auto-renewed 30 days before expiry. |
| **Remove it** | Without cert-manager, HTTPS requires manually obtaining a certificate from Let's Encrypt, manually storing it as a k8s Secret, manually creating a renewal reminder, and manually repeating every 90 days. In a production cluster with dozens of services, manual cert management is the thing that gets forgotten and causes a 3am outage when a cert expires. |

**Say it at three levels:**
- *Non-technical:* "cert-manager automatically gets and renews the security certificate that makes the padlock appear in the browser. It works in the background — the certificate never expires because cert-manager renews it automatically."
- *Junior engineer:* "Apply a `ClusterIssuer` pointing at Let's Encrypt. Add an annotation to the Ingress: `cert-manager.io/cluster-issuer: letsencrypt-prod`. cert-manager sees the annotation, requests a cert for the Ingress hostname, completes the HTTP-01 challenge, and stores the cert as a Secret. Traefik reads the Secret for TLS termination."
- *Senior engineer:* "cert-manager's reconciliation loop monitors cert expiry and renews at 2/3 of the certificate lifetime (60 days for a 90-day Let's Encrypt cert). DNS-01 challenges are required for wildcard certs and for clusters without public HTTP access. The cert Secret is a regular k8s Secret — in a multi-cluster setup, use external-secrets-operator to replicate it. Rate limits on Let's Encrypt staging vs prod matter during testing: always use the staging issuer until the pipeline works, then switch to prod."

---

### SPIFFE/SPIRE (Workload Identity)

| Layer | Question | Answer |
|-------|----------|--------|
| **Plain English** | What problem does this solve? | "Every pod in the cluster currently proves who it is with a static password (the API key Secret). SPIFFE/SPIRE gives each pod a short-lived cryptographic certificate instead — like an employee badge that expires daily and is automatically renewed, rather than a permanent password." |
| **System Role** | Where does it sit in AOIS? | SPIRE Server and Agent run in the `spire` namespace. The SPIRE Agent runs as a DaemonSet on every node, exposing the SPIFFE Workload API socket at `/run/spire/sockets/agent.sock`. AOIS pods mount this socket and can request an X.509 SVID at any time — the identity that other services use to verify AOIS is legitimate. |
| **Technical** | What is it, precisely? | SPIFFE is a standard for workload identity. A SPIFFE ID is a URI (`spiffe://aois.local/ns/aois/sa/aois`) that uniquely identifies a workload. SPIRE implements the standard: the server issues X.509 SVIDs (short-lived certificates), the agent attests workloads by matching them to registered entries (selectors: k8s namespace + service account), and delivers SVIDs via a Unix socket. On k3s, node attestation uses `k8s_psat` (Projected Service Account Tokens) and workload attestation uses the new container locator (`use_new_container_locator = true`) which reads cgroups and queries the k8s API — because k3s disables the kubelet read-only port that the default workload attestor requires. |
| **Remove it** | What breaks, and how fast? | Remove SPIRE and AOIS pods no longer receive SVIDs. Service-to-service mTLS (using SVID certificates for mutual auth) fails immediately. The path to Vault-backed dynamic secrets (SPIRE SVID → Vault JWT auth → API key) is also blocked. The static `aois-secrets` Secret remains functional — workload identity is not yet the sole auth mechanism. But the security posture reverts to long-lived credentials that cannot be audited per-workload. |
