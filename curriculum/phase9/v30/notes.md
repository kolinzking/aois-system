# v30 — Internal Developer Platform: Crossplane, Pulumi, Semantic Kernel

⏱ **Estimated time: 6–8 hours**

---

## Prerequisites

v29 W&B logging working. kubectl access to Hetzner cluster. Python 3.11+.

```bash
# Crossplane installable
helm repo add crossplane-stable https://charts.crossplane.io/stable
helm search repo crossplane | head -3

# Pulumi CLI
pulumi version
# v3.x.x

# Python typing works
python3 -c "from typing import TypedDict; print('ok')"
# ok
```

---

## Learning Goals

By the end you will be able to:

- Explain what an Internal Developer Platform is and why it matters for AI systems at scale
- Understand how Crossplane extends Kubernetes to provision external resources (Hetzner VMs, AWS RDS) as k8s objects
- Write a Pulumi program in Python that provisions AOIS infrastructure with real logic (loops, conditionals, secrets management) that Terraform's HCL cannot express
- Explain what Semantic Kernel is and how it integrates AOIS as an enterprise AI capability for .NET/Azure environments
- Design a self-service tenant provisioning flow: "new team wants AOIS" → Crossplane provisions infra → ArgoCD deploys → AOIS ready

---

## What an IDP Is

An Internal Developer Platform (IDP) is a self-service layer on top of your infrastructure. Instead of a developer filing a ticket and waiting 3 days for an SRE to provision a new AOIS instance, they fill out a form or run a command — and 5 minutes later their instance is live.

For AOIS, the IDP handles:
- New tenant provisioning: namespace + secrets + Helm release + ArgoCD app
- Self-service configuration: model tier, alert thresholds, notification webhooks
- Runbooks: documented standard operations accessible without SRE intervention

---

## Crossplane: Kubernetes as the Control Plane for Everything

Crossplane installs as a Kubernetes operator. After installation, you can create Custom Resources that provision external resources:

```yaml
# A Crossplane Composite Resource — provisions a Hetzner server + k8s namespace + ArgoCD app
apiVersion: aois.io/v1alpha1
kind: AoisTenant
metadata:
  name: team-payments
spec:
  teamName: payments
  modelTier: premium        # P1/P2 → Claude, P3/P4 → Groq
  alertWebhook: https://hooks.slack.com/xxx
  region: hetzner-eu
```

Crossplane's composition translates this into:
1. A Hetzner server provisioned via the Hetzner provider
2. A Kubernetes namespace `payments-aois`
3. A Secret with team-specific API keys
4. A Helm release for AOIS with team-specific values
5. An ArgoCD Application pointing at the team's config

```bash
# Install Crossplane
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system --create-namespace

# Install Hetzner provider
kubectl apply -f - << 'EOF'
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-hetzner
spec:
  package: "crossplane-contrib/provider-hetzner:v0.1.0"
EOF

# Apply the AoisTenant
kubectl apply -f k8s/crossplane/tenant-payments.yaml
# aoisTenant.aois.io/team-payments created

# 5 minutes later — verify everything is provisioned
kubectl get aoistenants
# NAME            SYNCED   READY   AGE
# team-payments   True     True    4m32s
```

---

## ▶ STOP — do this now

Install Crossplane and verify the CRD is registered:

```bash
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system --create-namespace --wait

kubectl get crds | grep crossplane
# compositeresourcedefinitions.apiextensions.crossplane.io
# compositions.apiextensions.crossplane.io
# providers.pkg.crossplane.io

kubectl get pods -n crossplane-system
# NAME                                       READY   STATUS
# crossplane-xxx                             1/1     Running
# crossplane-rbac-manager-xxx               1/1     Running
```

---

## Pulumi: IaC with Real Programming Languages

Terraform uses HCL — a declarative language. HCL cannot do loops over dynamic lists, cannot call functions, cannot import from external modules at runtime. When infrastructure provisioning requires real logic, HCL becomes unwieldy.

Pulumi lets you write infrastructure in Python. Same result, but with:
- For loops over real lists
- Conditional provisioning based on runtime values
- Calling Python libraries (secrets managers, REST APIs) during provisioning
- Stack outputs as typed Python objects

```python
# pulumi/aois_stack.py
"""Provision AOIS infrastructure for a new tenant using Pulumi + Python."""
import pulumi
import pulumi_kubernetes as k8s
import pulumi_hcloud as hcloud
import os

config = pulumi.Config()
tenant_name = config.require("tenantName")
model_tier = config.get("modelTier", "standard")
region = config.get("region", "nbg1")

# Provision a Hetzner server — real Python, not HCL
server = hcloud.Server(
    f"aois-{tenant_name}",
    name=f"aois-{tenant_name}",
    server_type="cx31" if model_tier == "premium" else "cx21",
    image="ubuntu-24.04",
    location=region,
    ssh_keys=[config.require_secret("hetznerSshKey")],
)

# Kubernetes namespace for the tenant
namespace = k8s.core.v1.Namespace(
    f"{tenant_name}-aois",
    metadata=k8s.meta.v1.ObjectMetaArgs(name=f"{tenant_name}-aois"),
)

# Helm release — values differ per model tier
helm_values = {
    "image": {"tag": os.getenv("AOIS_IMAGE_TAG", "latest")},
    "resources": {
        "limits": {"memory": "2Gi" if model_tier == "premium" else "1Gi"}
    },
}

# For premium tenants: enable ClickHouse analytics
if model_tier == "premium":
    helm_values["clickhouse"] = {"enabled": True}

release = k8s.helm.v3.Release(
    f"aois-{tenant_name}",
    chart="./charts/aois",
    namespace=namespace.metadata.name,
    values=helm_values,
    opts=pulumi.ResourceOptions(depends_on=[namespace]),
)

# Expose outputs
pulumi.export("server_ip", server.ipv4_address)
pulumi.export("namespace", namespace.metadata.name)
pulumi.export("helm_release_status", release.status)
```

Run:
```bash
cd pulumi
pulumi stack init aois-payments-prod
pulumi config set tenantName payments
pulumi config set modelTier premium
pulumi up --yes
```

The key: `if model_tier == "premium": helm_values["clickhouse"] = {"enabled": True}` is Python. In Terraform HCL, conditional resource creation requires `count = condition ? 1 : 0` — unwieldy for complex conditions. In Pulumi, it is an if statement.

---

## ▶ STOP — do this now

Create a Pulumi stack locally (no cloud resources yet — just plan):

```bash
pip install pulumi pulumi-kubernetes pulumi-hcloud
cd pulumi
pulumi stack init aois-dev-preview
pulumi config set tenantName dev-test
pulumi preview
```

Expected:
```
Previewing update (aois-dev-preview):
     Type                          Name              Plan
 +   pulumi:pulumi:Stack           aois-dev-preview  create
 +   ├─ hcloud:index:Server        aois-dev-test     create
 +   ├─ kubernetes:core/v1:Namespace  dev-test-aois  create
 +   └─ kubernetes:helm/v3:Release aois-dev-test     create

Resources:
    + 4 to create
```

The preview shows what would be created without actually creating it. Verify the conditionals work: change `modelTier` to `premium` and preview again — ClickHouse should appear in the plan.

---

## Semantic Kernel: AOIS as Enterprise AI Capability

Semantic Kernel (SK) is Microsoft's AI SDK for .NET (and Python). It is how enterprises in Azure/Microsoft environments build AI applications. Integrating AOIS into SK means AOIS analysis is available to any SK-based enterprise application without those teams knowing anything about AOIS internals.

```python
# semantic_kernel_plugin.py
"""Expose AOIS as a Semantic Kernel plugin — usable from any SK application."""
from semantic_kernel.functions import kernel_function
from semantic_kernel import Kernel
import httpx


class AOISPlugin:
    """AOIS as a Semantic Kernel plugin — analyze incidents and approve remediations."""

    @kernel_function(description="Analyze a Kubernetes incident and return severity + proposed action")
    async def analyze_incident(self, incident: str) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://aois-api:8000/analyze",
                json={"log": incident},
                timeout=30,
            )
            data = resp.json()
            return (
                f"Severity: {data['severity']}\n"
                f"Summary: {data['summary']}\n"
                f"Action: {data['suggested_action']}"
            )

    @kernel_function(description="List recent AOIS incidents from the last N minutes")
    async def get_recent_incidents(self, minutes: int = 30) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://aois-api:8000/api/incidents?limit=10")
            incidents = resp.json()
            recent = [i for i in incidents if i.get("severity") in ("P1", "P2")]
            return f"Found {len(recent)} P1/P2 incidents in the last {minutes} minutes."


# Register plugin with a Kernel instance
kernel = Kernel()
kernel.add_plugin(AOISPlugin(), plugin_name="AOIS")
```

An enterprise .NET application using SK can now call `AOIS.analyze_incident` as a function in its orchestration — AOIS analysis available inside Microsoft's AI ecosystem without any code duplication.

---

## Self-Service Tenant Provisioning Flow

The complete IDP flow for "team X wants AOIS":

```
1. Developer fills form on internal portal (Backstage / Port)
   ↓
2. Portal calls: kubectl apply -f aoisTenant.yaml (Crossplane)
   ↓
3. Crossplane composition creates:
   - Hetzner server or EKS namespace
   - Kubernetes namespace + RBAC
   - ExternalSecret pulling API keys from Vault
   - Helm release via ArgoCD
   ↓
4. ArgoCD syncs and deploys AOIS
   ↓
5. Developer receives Slack notification:
   "Your AOIS tenant 'payments' is ready at https://payments-aois.company.internal"
```

This flow takes 5 minutes and requires zero SRE intervention.

---

## Common Mistakes

### 1. Crossplane composition not validated before applying

Crossplane composition errors are silent — the resource appears `SYNCED` but the underlying cloud resource is never created.

```bash
# Always check the composition events
kubectl describe composite team-payments
# Look for: "Successfully composed resources" or error messages
```

### 2. Pulumi state stored locally — team cannot collaborate

Pulumi stores state in a backend. Default is local (`~/.pulumi`). For teams:

```bash
pulumi login s3://your-bucket/pulumi-state
# or
pulumi login https://app.pulumi.com  # Pulumi Cloud (free tier available)
```

---

## Troubleshooting

### `crossplane: composite resource stuck in Syncing`

Check the provider pod logs:
```bash
kubectl logs -n crossplane-system -l pkg.crossplane.io/provider=provider-hetzner
```

Usually: API credentials not configured. Create a ProviderConfig with the Hetzner API token.

### `pulumi up: TypeNotFound`

The resource type string is wrong. Check the Pulumi provider docs for the exact type path (e.g., `hcloud:index:Server` not `hcloud:Server`).

---

## Connection to Later Phases

### To v34.5 (Capstone): the IDP is how new teams onboard to AOIS in the capstone. The provisioning flow is demonstrated live — one `kubectl apply` command stands up a full AOIS instance for a new tenant in under 5 minutes.

---

## Mastery Checkpoint

1. Install Crossplane on the Hetzner cluster. Verify the CRDs are registered: `kubectl get crds | grep crossplane`. Show the output.
2. Run `pulumi preview` for a `standard` tenant. Run again for a `premium` tenant. Show the diff — ClickHouse should appear in the premium plan.
3. Register the `AOISPlugin` with a Semantic Kernel instance and call `analyze_incident` from SK. Show the output.
4. Design (no code required): what Crossplane resources would you need to provision AOIS as a new tenant on AWS EKS instead of Hetzner? List the resource types and their dependencies.
5. Explain to a CTO: why does the self-service IDP reduce SRE toil, and what is the risk if the Crossplane composition has a bug?
6. Explain to a senior engineer: what does Pulumi's Python support give you over Terraform's HCL that justifies the migration cost for complex infrastructure?

**The mastery bar:** you can provision a complete AOIS tenant (server, namespace, secrets, helm release, ArgoCD app) with a single `kubectl apply` via Crossplane, and demonstrate Pulumi's conditional provisioning handling premium vs standard tiers differently.

---

## 4-Layer Tool Understanding

### Crossplane

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Provisioning a new AOIS instance for a team requires: a server, a namespace, secrets, a helm release, an ArgoCD app — all done manually by an SRE. Crossplane lets you define "AOIS tenant" as a Kubernetes object. The SRE defines the template once; any team can provision themselves by applying the object. |
| **System Role** | Where does it sit in AOIS? | In the cluster control plane. Crossplane watches for `AoisTenant` objects and creates all the underlying resources. ArgoCD then deploys AOIS into the provisioned namespace. Together they are the IDP provisioning layer. |
| **Technical** | What is it precisely? | A Kubernetes operator that extends the Kubernetes API with Composite Resource Definitions (XRDs). Compositions define how to translate a high-level resource (AoisTenant) into low-level cloud resources (Hetzner server, k8s namespace, Helm release). Providers implement the actual cloud API calls. |
| **Remove it** | What breaks, and how fast? | Remove Crossplane → tenant provisioning is manual SRE work. Each new team files a ticket. SRE provisions manually. Mistakes happen. Time-to-tenant goes from 5 minutes to 3 days. At 10 teams, this does not scale. |

### Pulumi

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Terraform's HCL is a config language — it cannot do "if premium then also provision ClickHouse" cleanly. Pulumi lets you write infrastructure in Python: real conditionals, real loops, real imports. Complex provisioning logic is as readable as application code. |
| **System Role** | Where does it sit in AOIS? | The provisioning layer for complex infrastructure that Crossplane's YAML-based compositions cannot express. Premium tenants need ClickHouse; standard tenants do not. Pulumi handles this in 3 lines of Python. |
| **Technical** | What is it precisely? | An IaC platform where infrastructure is defined in Python (or TypeScript/Go). Resources are declared as Python objects. `pulumi up` computes the diff between current state (stored in a backend) and the desired state (your Python program) and applies only the changes. |
| **Remove it** | What breaks, and how fast? | Remove Pulumi → use Terraform for complex provisioning. Complex conditionals become `count` hacks. Dynamic resource creation requires `for_each` over complex maps. The provisioning code becomes unreadable at 20+ resources. New engineers cannot reason about what `count = var.is_premium ? 1 : 0` means in context. |

### Semantic Kernel

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Microsoft's enterprise customers build AI applications in .NET using Semantic Kernel. AOIS is built in Python. Without an SK plugin, these customers cannot use AOIS from their SK applications — they would have to rebuild the analysis logic in .NET. The plugin bridges the gap. |
| **System Role** | Where does it sit in AOIS? | An adapter layer. The `AOISPlugin` wraps AOIS's HTTP API in SK's plugin interface. Any SK kernel can `kernel.add_plugin(AOISPlugin())` and call `AOIS.analyze_incident` as a native SK function — AOIS participates in Microsoft's AI ecosystem. |
| **Technical** | What is it precisely? | Microsoft's AI orchestration SDK for .NET and Python. Skills/plugins are classes with `@kernel_function` decorated methods. The SK planner routes user requests to the right function. Plugins can call external APIs, databases, or other agents. SK is how enterprise Microsoft/Azure shops build AI applications. |
| **Remove it** | What breaks, and how fast? | Remove SK integration → enterprise Microsoft customers cannot use AOIS from their SK applications. They call the AOIS API directly (HTTP) — no planner, no orchestration, no native SK types. AOIS is invisible to the Microsoft AI ecosystem, which represents the largest enterprise AI deployment footprint on earth. |
