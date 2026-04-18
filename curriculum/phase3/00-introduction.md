# Phase 3 — Kubernetes & GitOps

## Introduction

Phase 2 proved AOIS can run safely. Phase 3 asks: can it run reliably, at a real URL, in a real data center, with zero manual intervention?

There is a specific moment that separates engineers who understand infrastructure from engineers who have only read about it: the first time you type `kubectl apply -f` and your application appears on the internet — running on a server you provisioned from nothing, managed by an orchestration system that self-heals when things break, with a real TLS certificate that was issued automatically. That moment is Phase 3.

Kubernetes is not a tool you use because it is fashionable. It is the mechanism by which the entire industry runs software at scale. Every cloud provider has a managed Kubernetes offering. Every production AI deployment you will work with in your career will run on Kubernetes or something that works like it. Understanding Kubernetes at the manifest level — what a Deployment is, what a Service does, how Ingress routes traffic, what cert-manager does with Let's Encrypt — is the difference between being able to operate production systems and being dependent on someone who can.

Phase 3 also introduces GitOps. ArgoCD makes the cluster watch your git repository. A git push is a deployment. This is not automation for its own sake — it is the removal of the entire category of "deployment drift," where what is running in the cluster diverges from what the code says should be running. With GitOps, the repository is always the truth. The cluster converges to it.

By the end of Phase 3 you have AOIS running live on the internet, deployed via a Helm chart, automatically redeployed on every git push to main. The service heals itself if a pod dies. The certificate renews itself. You are operating a real production system.

---

## What you will know by the end

- What Kubernetes is and why Docker Compose cannot replace it
- Every core Kubernetes resource type (Namespace, Deployment, Service, Ingress, ConfigMap, Secret, HPA)
- How cert-manager automates TLS certificate lifecycle
- How to package a service as a Helm chart with environment-specific values
- What GitOps means and why it matters for production reliability
- How ArgoCD watches a git repo and drives the cluster toward desired state
- How KEDA scales pods based on real work queues, not CPU/memory proxies

---

## The versions

| Version | Topic | What you build |
|---------|-------|----------------|
| v6 | k3s on Hetzner | AOIS live at a real HTTPS URL on a Hetzner VPS |
| v7 | Helm Chart | AOIS packaged for multi-environment deployment |
| v8 | ArgoCD GitOps | git push → automatic cluster deployment |
| v9 | KEDA Autoscaling | Pods scale to zero when idle, burst on demand |

---

## The narrative arc

v6 is raw Kubernetes — manifests applied by hand, understanding each resource.
v7 is packaging — the same manifests parameterized, environment differences in values.yaml.
v8 is GitOps — the cluster watches the repo, manual deployment never happens again.
v9 is intelligent scaling — pods appear when there is work and disappear when there is not.

Each version layers on top of the previous. The Deployment from v6 becomes the template in the Helm chart in v7. The Helm chart becomes what ArgoCD deploys in v8. The Deployment in v8 becomes what KEDA scales in v9.

---

## What Phase 2 contributes

The container from v4 and the security hardening from v5 feed directly into Phase 3:
- The Dockerfile becomes the image pushed to GHCR and referenced in the k8s Deployment
- The non-root user and read-only filesystem from v5 are preserved in the container spec
- The `/health` endpoint from v1 becomes the liveness and readiness probe target

Nothing in Phase 2 is redone. It is extended.
