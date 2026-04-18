# Phase 2 Complete — What Comes Next

Phase 2 asked a harder question than Phase 1. Phase 1 was: can AOIS reason about logs? Phase 2 was: can it survive contact with the real world?

The answer is yes. AOIS is now a containerized, scanned, signed, rate-limited, injection-defended, secrets-managed service that runs identically anywhere Docker runs.

---

## What you actually know now

After Phase 2 you understand:

**Containerization at the level that matters.** Multi-stage Docker builds (builder stage compiles, runtime stage runs, with only what is needed). Non-root user in the container. Read-only filesystem where possible. Minimal base image. Trivy scanning to zero HIGH/CRITICAL vulnerabilities before any image ships. These are not checkboxes — you understand why each one exists and what it prevents.

**The AI threat model.** Standard API security (rate limiting, input validation, authentication) is necessary but not sufficient when the API accepts untrusted content that goes to an LLM. Prompt injection is an entirely different attack surface — an attacker does not attack your API, they attack your model through data it reads. AOIS accepts log lines from infrastructure it monitors. An attacker who controls a log source can embed instructions. You have seen this threat and built a defense against it.

**Defense-in-depth for AI systems.** Input sanitization strips injection patterns before they reach the model. The hardened system prompt explicitly instructs the model to refuse instructions embedded in data. The output blocklist catches any destructive recommendation before it leaves the service. Three layers, each independent. If one fails, the others still hold.

**Secrets management patterns.** `.env` files work for local development. Production secrets live in Vault, never in environment variables that get logged, never in files that get leaked in error messages. You know the pattern: Vault stores the secret, External Secrets Operator (later) injects it into Kubernetes at runtime.

---

## The gap you can now feel

Phase 2 ends with a container. Run `docker compose up`. AOIS is running at `localhost:8000`.

But:

- `localhost:8000` is unreachable from any other machine
- There is no domain name, no TLS certificate
- If the process crashes, it restarts (Docker's `restart: always`), but there is no health gate — Docker will route traffic to a starting container even before it is ready
- Scaling to multiple instances requires manual intervention
- Deploying an update requires `docker compose down && docker compose up` — a few seconds of downtime

These are the problems Kubernetes solves. Phase 3 moves AOIS from Docker Compose on a single machine to k3s on a real server — with proper health checks, TLS termination, and a deployment model that guarantees zero downtime for updates.

---

## What Phase 3 feels like on day one

You open the v6 notes. You provision a Hetzner VPS. A real server — not your laptop, not a Codespace — running in a data center in Nuremberg.

You install k3s on it. You copy the kubeconfig to your Codespace. You run `kubectl get nodes` and see:

```
NAME            STATUS   ROLES                  AGE   VERSION
your-server     Ready    control-plane,master   2m    v1.29.2+k3s1
```

That is your cluster. One node, but real Kubernetes.

Then you write YAML manifests. A Namespace (isolation). A Secret (your API keys). A Deployment (how many AOIS pods to run, what image, what resource limits, liveness probe, readiness probe). A Service (internal networking). An Ingress (routing external traffic to the service). A ClusterIssuer (cert-manager's connection to Let's Encrypt).

`kubectl apply -f k8s/`

And then you `curl https://aois.your-ip.nip.io/health`.

It responds. From a server in Germany. Over HTTPS. With a real certificate.

That is not localhost anymore.

---

## The infrastructure progression you are building

```
Phase 1: uvicorn main:app (your terminal, your machine)
Phase 2: docker compose up (any machine with Docker)
Phase 3: kubectl apply -f k8s/ (any k8s cluster)
Phase 4: helm install (any k8s cluster, any environment, values-based config)
Phase 5: git push → ArgoCD syncs (zero manual deployment ever again)
```

Each phase adds a layer of operational maturity. By Phase 3 you understand why the industry moved from "just run the script" to Docker to Kubernetes to GitOps — not because engineers like complexity, but because each layer solved real problems the previous layer could not.

The complexity buys you something. Phase 3 shows you what.
