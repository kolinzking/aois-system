# Phase 3 Complete — What Comes Next

AOIS is live. A real server. A real cluster. A real HTTPS URL. Deployed via Helm, automatically redeployed when you push to main. Pods self-heal. Certificates renew automatically. You operate this with `kubectl` from a laptop anywhere in the world.

This is production-grade infrastructure. The gap between this and what enterprises run at scale is smaller than it looks.

---

## What you actually know now

After Phase 3 you understand:

**Kubernetes at the manifest level.** Not just "k8s is an orchestrator" — you have written the YAML, understood every field, debugged real failures. You know what a Deployment does (declares desired pod state and manages rolling updates), what a Service does (stable network identity for ephemeral pods), what an Ingress does (routes HTTP/HTTPS to services), what a liveness probe does vs a readiness probe (liveness: is the process alive? readiness: is it ready for traffic?). Every k8s engineer starts here.

**How Helm packages Kubernetes.** The same manifests you wrote in v6 are parameterized with `{{ .Values.image.tag }}`. Different environments (staging, production) use different `values.yaml` files. The chart installs with one command, upgrades with one command, rolls back with one command. This is how every real service is deployed — not by hand-editing YAML.

**What GitOps means in practice.** ArgoCD watches the git repository. The `desired state` is the Helm chart in git. The `actual state` is what is running in the cluster. ArgoCD continuously reconciles them. Push a bad image tag: ArgoCD deploys it, the liveness probe fails, ArgoCD reports degraded. Push a fix: ArgoCD deploys the fix. The cluster is always converging toward what git says. Manual `kubectl apply` never happens in production again.

**Intelligent autoscaling.** KEDA scales pods based on what actually matters — Kafka topic lag, queue depth, real work — not CPU/memory proxies that are often wrong. Zero pods when AOIS is idle (saving money). Twenty pods when Kafka lag grows (handling load). This is the right model for event-driven AI services.

---

## The gap you can now feel

Phase 3 ends with AOIS on Hetzner k3s. One region, one provider, one node.

What enterprises actually need:

- **Multiple regions** — AOIS serving users in Europe, US, and Asia from clusters in each region
- **Managed Kubernetes** — not k3s on a VPS you manage, but EKS on AWS where the control plane is AWS's responsibility
- **Compliance infrastructure** — enterprise AI has regulatory requirements (SOC2, HIPAA, GDPR) that require auditable deployment patterns, managed secrets, specific data residency
- **Scale** — a Hetzner CX22 handles test traffic. AWS EKS + Karpenter handles millions of requests

Phase 4 puts AOIS on AWS. Same Helm chart, different values. But also: Claude running through Amazon Bedrock (managed, compliant, no API key management). Lambda for serverless bursts. EKS for production scale.

The skills transfer. The YAML is the same. The `values.yaml` changes. That is the payoff of Helm.

---

## What Phase 4 feels like on day one

You open the v10 notes. The first thing is not Kubernetes — it is Bedrock. Amazon Bedrock is how enterprises run Claude in AWS environments: no API key to manage, IAM roles for authentication, compliance logging built in, data residency controls.

You configure LiteLLM to route to `bedrock/anthropic.claude-opus-4-6-v1:0` instead of direct Anthropic. The `POST /analyze` endpoint does not change at all. The routing layer from v2 absorbs the provider change transparently.

Then EKS: same Helm chart from v7. `helm install aois ./charts/aois -f values.eks.yaml`. The cluster is AWS-managed. Karpenter provisions nodes in 60 seconds when load spikes. IRSA (IAM Roles for Service Accounts) gives AOIS permission to call Bedrock without any static credentials — the pod authenticates via its Kubernetes service account, and AWS handles the rest.

The value of Phase 3 is that Phase 4 is mostly configuration, not new code.

---

## The deployment evolution

```
v6:  kubectl apply -f k8s/                     (raw manifests, Hetzner k3s)
v7:  helm install aois ./charts/aois           (Helm, same cluster)
v8:  git push → ArgoCD syncs                   (GitOps, zero manual ops)
v9:  KEDA scales pods to 0-20 based on load    (intelligent autoscaling)
v10: helm install -f values.bedrock.yaml       (same chart, AWS/Bedrock)
v12: helm install -f values.eks.yaml           (same chart, EKS)
```

One chart. Multiple targets. The parameterization from v7 is what makes this possible. You built that infrastructure in Phase 3.

---

## The mental model to carry forward

Kubernetes is a control loop. It continuously asks: "What state does this cluster want to be in?" (from your manifests/Helm chart) and "What state is it actually in?" (from reality). The difference is the reconciliation target. Controllers run constantly to close that gap.

ArgoCD is a control loop at a higher level: "What does the git repo say should be deployed?" vs "What is actually running?" Same principle, different scope.

KEDA is a control loop for pod count: "What does the work queue depth say I need?" vs "How many pods are running?" Same principle, scaling dimension.

This pattern — desired state vs actual state, continuous reconciliation — is the fundamental model of the entire Kubernetes ecosystem. Once you see it, you see it everywhere. It explains why Kubernetes is designed the way it is, why everything is declarative, why controllers exist. You are not learning a tool; you are learning a paradigm.
