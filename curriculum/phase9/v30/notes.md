# v30 — Internal Developer Platform: Crossplane, Pulumi, Semantic Kernel

⏱ **Estimated time: 6–8 hours**

*Phase 9 — Production CI/CD and Platform Engineering. v29 made AI quality measurable. v30 makes AOIS self-service and enterprise-compatible.*

---

## What This Version Builds

Right now, standing up a new AOIS instance for a team takes a full day: provision a server, configure Kubernetes, create namespaces and secrets, write a Helm values override, set up ArgoCD. Every step is manual. Every step can fail. Every step requires SRE time.

At two teams, this is fine. At ten teams, it is unsustainable. At twenty teams, the SRE team is a deployment bottleneck and everyone is unhappy.

This version builds the platform layer that eliminates the bottleneck. You declare "AOIS tenant" as a Kubernetes object, and provisioning a complete instance becomes `kubectl apply -f tenant.yaml` — a 5-minute, zero-SRE-intervention operation. That is an Internal Developer Platform (IDP).

Three tools make this happen:

**Crossplane**: extends Kubernetes to provision external resources (servers, namespaces, Helm releases, ArgoCD apps) as k8s objects. The SRE defines the template once; any team provisions themselves.

**Pulumi**: Infrastructure as Code in Python. Where Crossplane's YAML-based compositions cannot express conditional logic (premium tenants get ClickHouse, standard tenants do not), Pulumi handles it in three lines of Python.

**Semantic Kernel**: Microsoft's AI SDK for .NET and Python. Integrating AOIS as an SK plugin makes AOIS analysis available to every enterprise Microsoft/Azure application without those teams knowing anything about FastAPI, LiteLLM, or Kafka. AOIS becomes a native capability in Microsoft's AI ecosystem.

By the end of v30:
- Crossplane installed, XRD and Composition defined — `kubectl apply -f tenant.yaml` provisions a complete AOIS namespace
- Pulumi stack showing conditional provisioning: `model_tier == "premium"` enables ClickHouse, `"standard"` does not — a live `pulumi preview` shows the diff
- Semantic Kernel plugin registered — `kernel.invoke("AOIS", "analyze_incident")` calls AOIS from any SK application
- Full self-service tenant provisioning flow documented end-to-end

---

## Prerequisites

```bash
# Crossplane Helm repo accessible
helm repo add crossplane-stable https://charts.crossplane.io/stable && helm repo update
helm search repo crossplane-stable | head -3
```

Expected:
```
NAME                              CHART VERSION  APP VERSION  DESCRIPTION
crossplane-stable/crossplane      1.15.x         1.15.x       Crossplane is an open source Kubernetes add-on...
```

```bash
# Pulumi CLI installed
pulumi version
```

Expected:
```
v3.x.x
```

If not installed: `curl -fsSL https://get.pulumi.com | sh`

```bash
# Python Pulumi packages installable
pip install pulumi pulumi-kubernetes 2>&1 | tail -3
python3 -c "import pulumi; print('pulumi ok')"
```

Expected:
```
pulumi ok
```

```bash
# Semantic Kernel installable
pip install semantic-kernel httpx 2>&1 | tail -2
python3 -c "from semantic_kernel import Kernel; print('sk ok')"
```

Expected:
```
sk ok
```

```bash
# kubectl access to Hetzner cluster
kubectl get nodes
```

Expected:
```
NAME   STATUS   ROLES                  AGE   VERSION
aois   Ready    control-plane,master   Xd    v1.30.x
```

---

## Learning Goals

By the end of v30 you will be able to:

- Explain what an Internal Developer Platform is and why it reduces SRE toil at scale — the specific problem it solves for a team onboarding the tenth AOIS tenant
- Install Crossplane, apply an XRD and Composition, and provision an AOIS tenant namespace with a single `kubectl apply`
- Write a Pulumi Python program with conditional resource provisioning — premium tenants get ClickHouse, standard tenants do not — using logic that Terraform's HCL cannot express cleanly
- Run `pulumi preview` for standard and premium configurations and read the diff output to confirm the conditional logic is working
- Register an AOIS plugin with Semantic Kernel and call `AOIS.analyze_incident` from Python SK code
- Design (without code) the Crossplane resources needed to provision AOIS as a new tenant on AWS EKS instead of Hetzner
- Explain what breaks if any of these three tools is removed: Crossplane, Pulumi, Semantic Kernel

---

## Part 1: What an Internal Developer Platform Is

An Internal Developer Platform (IDP) is a self-service layer on top of your infrastructure. The difference between having an IDP and not having one shows up at the moment the tenth team says "we want to use AOIS":

**Without IDP**:
- Team submits a ticket
- SRE reviews it (2 days to get to it)
- SRE provisions a server manually ($0 tooling cost, 4 hours of SRE time)
- SRE creates namespace, secrets, ArgoCD app (1 more hour)
- SRE deploys AOIS via Helm (30 minutes)
- Team gets access (total: ~3 days elapsed, 5 SRE hours)
- At team #10: SRE team is spending 50 hours per month on provisioning
- Mistakes happen (wrong secrets, wrong namespace, wrong ArgoCD target)

**With IDP**:
- Team fills form on internal portal (Backstage/Port) or runs one command
- Crossplane composition creates: namespace, secrets, ArgoCD app, Helm release — automatically
- Team gets access in 5 minutes
- At team #10: no additional SRE time. Crossplane scales to 100 teams the same as 1
- Mistakes are prevented by the composition template, not caught after the fact

For AOIS specifically, the IDP answers: "how does a new team get AOIS without requiring SRE intervention?" The composition is the answer.

An IDP is not just about speed — it is about consistency. Every provisioned AOIS instance has the same namespace naming convention, the same RBAC structure, the same secrets pattern, the same ArgoCD application config. No snowflake instances. No "the payments team's AOIS is slightly different because Collins set it up manually on a Friday afternoon."

---

## Part 2: Crossplane — Kubernetes as the Control Plane for Everything

Crossplane installs as a Kubernetes operator. Once installed, you can create Custom Resources that provision external resources — a Hetzner server, an AWS RDS instance, a Kubernetes namespace, a Helm release — by applying a YAML file to Kubernetes. The infrastructure lives in Kubernetes's etcd, managed by the same GitOps workflow (ArgoCD) that manages everything else.

The mental model: Kubernetes is not just for containers. With Crossplane, it is the control plane for all infrastructure.

### Installing Crossplane

```bash
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace \
  --version 1.15.0 \
  --wait
```

Expected:
```
NAME: crossplane
LAST DEPLOYED: Fri Apr 25 10:00:00 2026
NAMESPACE: crossplane-system
STATUS: deployed
REVISION: 1
```

Wait for all pods to be ready:

```bash
kubectl get pods -n crossplane-system
```

Expected:
```
NAME                                       READY   STATUS    RESTARTS   AGE
crossplane-xxxxxxxxxx-xxxxx                1/1     Running   0          2m
crossplane-rbac-manager-xxxxxxxxxx-xxxxx   1/1     Running   0          2m
```

Verify the Crossplane CRDs are installed:

```bash
kubectl get crds | grep crossplane | head -6
```

Expected:
```
compositeresourcedefinitions.apiextensions.crossplane.io   2026-04-25T10:00:00Z
compositions.apiextensions.crossplane.io                   2026-04-25T10:00:00Z
configurationpackages.pkg.crossplane.io                    2026-04-25T10:00:00Z
functions.pkg.crossplane.io                                2026-04-25T10:00:00Z
locks.pkg.crossplane.io                                    2026-04-25T10:00:00Z
providers.pkg.crossplane.io                                2026-04-25T10:00:00Z
```

### The AOIS Tenant XRD

The XRD (CompositeResourceDefinition) is the schema. It defines what an `AoisTenant` object looks like — what fields it accepts, what types they are, what defaults apply.

The actual XRD for AOIS is in `k8s/crossplane/aois-tenant-xrd.yaml`. The key fields of the schema:

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: aoistenants.aois.io
spec:
  group: aois.io
  names:
    kind: AoisTenant
    plural: aoistenants
  versions:
    - name: v1alpha1
      served: true
      referenceable: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: [teamName, modelTier]   # these two are mandatory
              properties:
                teamName:
                  type: string
                  description: "Team name — used for namespace and resource naming"
                modelTier:
                  type: string
                  enum: [standard, premium]
                  default: standard
                alertWebhook:
                  type: string
                  description: "Slack/PagerDuty webhook for P1 alerts"
                region:
                  type: string
                  default: nbg1
```

The Composition translates an `AoisTenant` object into the underlying resources — in the AOIS case, a Kubernetes `Object` resource (using the Kubernetes provider) that creates the actual namespace:

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: aoistenants.aois.io
spec:
  compositeTypeRef:
    apiVersion: aois.io/v1alpha1
    kind: AoisTenant
  resources:
    - name: namespace
      base:
        apiVersion: kubernetes.crossplane.io/v1alpha1
        kind: Object
        spec:
          forProvider:
            manifest:
              apiVersion: v1
              kind: Namespace
              metadata:
                labels:
                  aois.io/managed: "true"
      patches:
        - fromFieldPath: spec.teamName
          toFieldPath: spec.forProvider.manifest.metadata.name
          transforms:
            - type: string
              string:
                fmt: "%s-aois"   # payments → payments-aois
```

The `patches` section is how values from the tenant spec flow into the underlying resources. `spec.teamName` → `metadata.name` (transformed with the `-aois` suffix). The composition can have multiple resources with patches, building a complete provisioning chain.

### Provisioning a Tenant

With the XRD and Composition applied, creating a new AOIS tenant is one command:

```bash
kubectl apply -f - <<EOF
apiVersion: aois.io/v1alpha1
kind: AoisTenant
metadata:
  name: team-payments
spec:
  teamName: payments
  modelTier: premium
  alertWebhook: https://hooks.slack.com/services/xxx/yyy/zzz
  region: nbg1
EOF
```

Expected:
```
aoisTenant.aois.io/team-payments created
```

Check status:

```bash
kubectl get aoistenants
```

Expected (after Crossplane reconciles):
```
NAME            SYNCED   READY   COMPOSITION                 AGE
team-payments   True     True    aoistenants.aois.io         2m
```

Check the namespace was created:

```bash
kubectl get namespace payments-aois
```

Expected:
```
NAME            STATUS   AGE
payments-aois   Active   2m
```

---

## ▶ STOP — do this now: Install Crossplane and Apply the XRD

```bash
# Install Crossplane
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace \
  --wait

# Verify
kubectl get pods -n crossplane-system
# Expected: crossplane and crossplane-rbac-manager both Running

# Apply the XRD and Composition
kubectl apply -f k8s/crossplane/aois-tenant-xrd.yaml

# Verify the CRD is registered
kubectl get crds | grep aois.io
```

Expected:
```
aoistenants.aois.io   2026-04-25T10:00:00Z
```

Try creating a tenant:

```bash
kubectl apply -f - <<EOF
apiVersion: aois.io/v1alpha1
kind: AoisTenant
metadata:
  name: team-platform
spec:
  teamName: platform
  modelTier: standard
EOF
```

Expected:
```
aoisTenant.aois.io/team-platform created
```

Check the tenant:

```bash
kubectl get aoistenants
kubectl describe aoisTenant team-platform
```

Look at the `Conditions` section in the describe output. `SYNCED: True` means Crossplane has applied the composition. `READY: True` means all composed resources are healthy. If either is `False`, the events section will show the error.

---

## Part 3: Pulumi — Infrastructure as Code with Real Programming Languages

Terraform uses HCL — a declarative configuration language. HCL is designed for describing infrastructure state, not for expressing logic. When your infrastructure provisioning has conditions ("if premium, also provision ClickHouse"), loops ("provision these 10 RBAC rules from a list"), or external API calls ("look up this team's Slack channel from our internal API"), HCL becomes awkward.

Pulumi lets you write infrastructure in Python. Everything you can do in Python — loops, conditionals, imports, function calls, type checking — is available in your infrastructure code. The result: complex provisioning logic is as readable as application code.

### What Pulumi Does vs. What Terraform Does

They solve the same problem: declare infrastructure state, compute diffs, apply changes. The difference is expressiveness:

```python
# Pulumi — this is valid Python
if model_tier == "premium":
    clickhouse = ClickHouseCluster("aois-clickhouse", ...)
    helm_values["clickhouse"] = {"enabled": True, "host": clickhouse.host}

for env in ["staging", "production"]:
    Namespace(f"{tenant_name}-aois-{env}", ...)
```

```hcl
# Terraform HCL — conditional resource
resource "kubernetes_namespace" "clickhouse" {
  count = var.model_tier == "premium" ? 1 : 0
  # The conditional is possible but the pattern is limited
  # Loops require for_each with complex map structures
}
```

For simple infrastructure (static number of resources, no conditionals), HCL is fine. For AOIS's tenant provisioning — where premium tenants get different resources than standard tenants, and the provisioning logic may need to call external APIs — Python wins.

### The AOIS Pulumi Stack

The actual stack in `pulumi/aois_stack.py`:

```python
"""Provision AOIS infrastructure for a new tenant using Pulumi + Python."""
import pulumi
import os

config = pulumi.Config()
tenant_name = config.require("tenantName")     # required — raises if not set
model_tier = config.get("modelTier", "standard")  # optional, defaults to standard
region = config.get("region", "nbg1")


def build_helm_values() -> dict:
    """Build Helm values dict. This is Python — full conditional logic."""
    values = {
        "image": {"tag": os.getenv("AOIS_IMAGE_TAG", "latest")},
        "resources": {
            "limits": {"memory": "2Gi" if model_tier == "premium" else "1Gi"},
            "requests": {"memory": "512Mi" if model_tier == "premium" else "256Mi"},
        },
        "replicaCount": 2 if model_tier == "premium" else 1,
    }

    if model_tier == "premium":
        values["clickhouse"] = {"enabled": True}
        values["agentEvals"] = {"schedule": "0 * * * *"}   # hourly evals for premium
    # Standard tenants: no ClickHouse, no hourly evals

    return values


try:
    import pulumi_kubernetes as k8s

    # Kubernetes namespace for this tenant
    namespace = k8s.core.v1.Namespace(
        f"{tenant_name}-aois",
        metadata=k8s.meta.v1.ObjectMetaArgs(
            name=f"{tenant_name}-aois",
            labels={
                "aois.io/tenant": tenant_name,
                "aois.io/tier": model_tier,
            },
        ),
    )

    # Helm release — values differ per model tier
    release = k8s.helm.v3.Release(
        f"aois-{tenant_name}",
        chart="./charts/aois",
        namespace=namespace.metadata.name,
        values=build_helm_values(),
        opts=pulumi.ResourceOptions(depends_on=[namespace]),
    )

    pulumi.export("namespace", namespace.metadata.name)
    pulumi.export("helm_release_status", release.status)

except ImportError:
    pulumi.log.warn("pulumi_kubernetes not installed — run: pip install pulumi-kubernetes")
    pulumi.export("namespace", f"{tenant_name}-aois (preview only)")
```

The `try/except ImportError` block is the "dry run" pattern: without `pulumi_kubernetes`, the stack still initializes and can produce a preview (using `pulumi preview`), but does not create real resources. This lets you test the configuration without having cluster access.

### Running Pulumi

Initialize a stack and configure it:

```bash
cd pulumi
pulumi stack init aois-payments-prod
pulumi config set tenantName payments
pulumi config set modelTier premium
```

Preview what would be created (no resources created yet):

```bash
pulumi preview
```

Expected:
```
Previewing update (aois-payments-prod):

     Type                              Name                Plan
 +   pulumi:pulumi:Stack               aois-payments-prod  create
 +   ├─ kubernetes:core/v1:Namespace   payments-aois       create
 +   └─ kubernetes:helm/v3:Release     aois-payments       create

Resources:
    + 3 to create

Outputs:
    namespace:           "payments-aois"
    helm_release_status: output<string>
```

The key: 3 resources will be created — the stack itself, the namespace, and the Helm release.

---

## ▶ STOP — do this now: Compare Standard vs. Premium Pulumi Preview

Initialize two stacks and compare their previews:

```bash
# Standard tenant
cd pulumi
pulumi stack init aois-standard-preview
pulumi config set tenantName standard-test
pulumi config set modelTier standard
pulumi preview
```

Expected — note what is NOT in the plan:
```
Previewing update (aois-standard-preview):

     Type                              Name                      Plan
 +   pulumi:pulumi:Stack               aois-standard-preview     create
 +   ├─ kubernetes:core/v1:Namespace   standard-test-aois        create
 +   └─ kubernetes:helm/v3:Release     aois-standard-test        create

Resources:
    + 3 to create
```

```bash
# Premium tenant — same code, different config
pulumi stack init aois-premium-preview
pulumi config set tenantName premium-test
pulumi config set modelTier premium
pulumi preview
```

Expected — ClickHouse appears in the plan:
```
Previewing update (aois-premium-preview):

     Type                              Name                      Plan
 +   pulumi:pulumi:Stack               aois-premium-preview      create
 +   ├─ kubernetes:core/v1:Namespace   premium-test-aois         create
 +   └─ kubernetes:helm/v3:Release     aois-premium-test         create

Resources:
    + 3 to create

Outputs:
    namespace:           "premium-test-aois"
    helm_release_status: output<string>

Note: 'helm_release_status' includes values="{"clickhouse":{"enabled":true},"agentEvals":{"schedule":"0 * * * *"},...}"
```

The Helm values in the preview show the ClickHouse and agentEvals keys for premium, absent for standard. The conditional logic worked — same code, different output based on `modelTier`. That `if model_tier == "premium":` block in Python is doing work that would require `count` hacks and complex variable structures in Terraform HCL.

Verify the diff exists by comparing the two stacks:

```bash
pulumi stack ls
```

Expected:
```
NAME                    LAST UPDATE  RESOURCE COUNT  URL
aois-standard-preview*  n/a          0               https://app.pulumi.com/...
aois-premium-preview    n/a          0               https://app.pulumi.com/...
```

The asterisk marks the currently selected stack.

---

## Part 4: Semantic Kernel — AOIS in the Microsoft AI Ecosystem

Semantic Kernel (SK) is Microsoft's AI SDK for .NET (and Python). It is how enterprise applications in the Azure ecosystem build AI orchestration. An SK application defines "skills" (collections of functions), an "orchestrator" routes user requests to the right function, and a "planner" can automatically compose multi-step workflows from available skills.

The question for AOIS: Microsoft's enterprise customers are building AI applications in .NET using SK. AOIS is built in Python. If a Microsoft enterprise shop wants to add "infrastructure incident analysis" to their SK application, do they:

a) Rebuild AOIS's analysis logic in .NET
b) Call AOIS's HTTP API directly (no SK integration, no planner, no native types)
c) Install the AOIS SK plugin and call `AOIS.analyze_incident` as a native SK function

Option (c) is the right answer. It means AOIS participates in the SK orchestration layer — the planner can automatically compose AOIS analysis with other SK skills (ticketing, alerting, documentation search). AOIS becomes a first-class capability in Microsoft's AI ecosystem.

### The AOIS Plugin

The actual plugin in `semantic_kernel_plugin.py`:

```python
"""Expose AOIS as a Semantic Kernel plugin — usable from any SK application."""
import httpx
import os

try:
    from semantic_kernel.functions import kernel_function
    from semantic_kernel import Kernel
    _SK_AVAILABLE = True
except ImportError:
    _SK_AVAILABLE = False
    kernel_function = lambda **kw: (lambda f: f)   # no-op decorator for non-SK environments

AOIS_API_URL = os.getenv("AOIS_API_URL", "http://localhost:8000")


class AOISPlugin:
    """AOIS as a Semantic Kernel plugin."""

    @kernel_function(description="Analyze a Kubernetes incident and return severity + proposed action")
    async def analyze_incident(self, incident: str) -> str:
        """
        Call AOIS /analyze endpoint and return formatted result.
        The @kernel_function decorator registers this as a callable SK function.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{AOIS_API_URL}/analyze",
                json={"log": incident},
            )
            data = resp.json()
            return (
                f"Severity: {data.get('severity', 'unknown')}\n"
                f"Summary: {data.get('summary', '')}\n"
                f"Action: {data.get('suggested_action', '')}"
            )

    @kernel_function(description="List recent P1/P2 AOIS incidents")
    async def get_recent_incidents(self, limit: int = 10) -> str:
        """Retrieve recent critical incidents from AOIS."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{AOIS_API_URL}/api/incidents?limit={limit}")
            incidents = resp.json()
            critical = [i for i in incidents if i.get("severity") in ("P1", "P2")]
            return (
                f"Found {len(critical)} P1/P2 incidents "
                f"out of {len(incidents)} recent incidents."
            )


def build_kernel() -> object:
    """Build a Semantic Kernel with the AOIS plugin registered."""
    if not _SK_AVAILABLE:
        raise ImportError("pip install semantic-kernel")
    kernel = Kernel()
    kernel.add_plugin(AOISPlugin(), plugin_name="AOIS")
    return kernel
```

The `@kernel_function(description=...)` decorator is the entire SK integration. The description string is used by SK's planner to decide when to call this function — it is essentially a natural language description that the planner uses to route requests. Good descriptions matter for planner accuracy.

The `try/except ImportError` pattern with the no-op decorator means this file imports cleanly even without `semantic-kernel` installed — the AOIS codebase does not have a hard dependency on SK. Teams that do not use SK do not need to install it.

### Using the Plugin

From Python:

```python
import asyncio
from semantic_kernel_plugin import build_kernel

async def main():
    kernel = build_kernel()

    # Direct invocation
    result = await kernel.invoke(
        plugin_name="AOIS",
        function_name="analyze_incident",
        incident="pod/payment-processor-7d9f OOMKilled, exit code 137, memory limit 512Mi",
    )
    print(str(result))

asyncio.run(main())
```

Expected (with AOIS running locally on port 8000):
```
Severity: P1
Summary: payment-processor pod killed by kernel OOM at 512Mi limit
Action: Increase memory limit to 1Gi, investigate memory leak in payment processing logic
```

For a .NET enterprise application, the same call looks like:

```csharp
// .NET SK integration (conceptual — AOIS HTTP API is language-agnostic)
var result = await kernel.InvokeAsync("AOIS", "analyze_incident", new KernelArguments {
    ["incident"] = "pod/payment-processor OOMKilled, exit code 137"
});
```

The SK planner can also automatically compose AOIS with other plugins:

```python
# SK planner composing AOIS + Jira + Slack (conceptual)
# User prompt: "Investigate the OOM kill and file a Jira ticket"
# Planner: 1. AOIS.analyze_incident → 2. Jira.create_ticket → 3. Slack.notify
result = await planner.invoke_async(
    "Investigate the OOM kill in payment-processor and file a Jira ticket"
)
```

---

## ▶ STOP — do this now: Register the AOIS Plugin and Call It

Start AOIS locally (if not already running):

```bash
docker compose up -d aois
curl -s http://localhost:8000/health | jq .
# Expected: {"status": "ok"}
```

Run the SK integration:

```python
# Save as test_sk.py
import asyncio
from semantic_kernel_plugin import build_kernel

async def main():
    kernel = build_kernel()
    print(f"Plugins registered: {list(kernel.plugins.keys())}")

    result = await kernel.invoke(
        plugin_name="AOIS",
        function_name="analyze_incident",
        incident="CrashLoopBackOff: auth-service failed 8 times in 10 minutes, last exit code 1",
    )
    print("\n--- AOIS Analysis ---")
    print(str(result))

asyncio.run(main())
```

```bash
python3 test_sk.py
```

Expected:
```
Plugins registered: ['AOIS']

--- AOIS Analysis ---
Severity: P1
Summary: auth-service repeatedly crashing with non-zero exit code, crash loop indicates persistent failure
Action: Check pod logs for root cause: kubectl logs auth-service-xxx --previous; check for config errors or missing dependencies
```

Now list the functions available in the AOIS plugin:

```python
# Add to test_sk.py after build_kernel():
aois_plugin = kernel.plugins["AOIS"]
print("AOIS plugin functions:")
for name, func in aois_plugin.functions.items():
    print(f"  {name}: {func.description}")
```

Expected:
```
AOIS plugin functions:
  analyze_incident: Analyze a Kubernetes incident and return severity + proposed action
  get_recent_incidents: List recent P1/P2 AOIS incidents
```

---

## Part 5: The Complete Self-Service Tenant Provisioning Flow

With all three pieces in place (Crossplane, Pulumi, ArgoCD from v8), the complete flow for "team X wants AOIS":

```
Step 1: Developer fills form on internal portal (Backstage or Port)
  ↓  (portal generates YAML and calls kubectl apply)

Step 2: kubectl apply -f aoisTenant-teamx.yaml
  ↓  (Crossplane watches for AoisTenant objects)

Step 3: Crossplane Composition creates:
  ├─ Kubernetes namespace: teamx-aois
  ├─ RBAC: team X gets read/write on their namespace
  ├─ ExternalSecret: pulls API keys from Vault → Secret in teamx-aois
  ├─ HelmRelease (via Flux or ArgoCD Application)
  └─ Notification: Slack message "Your AOIS tenant is ready"
  ↓

Step 4: ArgoCD detects the HelmRelease, syncs, deploys AOIS
  ↓

Step 5: Developer receives:
  "Your AOIS tenant 'teamx' is ready at https://teamx-aois.internal.company.com"

Total time: 5 minutes.
Total SRE time: 0 hours.
```

For premium tenants, Pulumi handles the parts Crossplane's YAML cannot express:

```
Crossplane creates: namespace, secrets, basic RBAC
Pulumi creates: conditional ClickHouse (premium only), hourly eval CronJob (premium only)
```

The split is deliberate: Crossplane handles the declarative, template-based parts. Pulumi handles the logic-heavy parts. They are complementary, not competing.

### Backstage vs. Port

Both are IDP portals. The choice depends on what the company already uses:

**Backstage** (open source, from Spotify): self-hosted, highly customizable, large plugin ecosystem, requires significant configuration effort. Good fit if you want full control and have engineering resources to maintain it.

**Port** (commercial): managed SaaS, faster to set up, good API for automation, less customization. Good fit if you want a working IDP in days instead of months.

For AOIS, the portal is a thin layer on top of Crossplane. Either tool calls `kubectl apply -f tenant.yaml` after the user fills the form. The portal is UX; Crossplane is the actual provisioning.

---

## Common Mistakes

### 1. Crossplane Composition Not Validated Before Applying

**Symptom**: `kubectl apply -f aois-tenant-xrd.yaml` succeeds, you create an `AoisTenant`, it shows `SYNCED: True` but the namespace is never created. No error appears.

**Cause**: the Composition has a bug (wrong patch path, wrong API version for the composed resource) but Crossplane's reconciler does not surface this clearly in the resource status.

**Fix**: check the composition events explicitly:

```bash
kubectl describe composite team-platform
# Look at Events section at the bottom
kubectl get events --field-selector reason=ComposeResources -n crossplane-system
```

Also check the Crossplane operator logs:

```bash
kubectl logs -n crossplane-system -l app=crossplane | grep -i error | tail -20
```

### 2. Pulumi State Stored Locally — Team Cannot Collaborate

**Symptom**: you run `pulumi up` from your laptop and it works. Your colleague runs `pulumi up` from their laptop and Pulumi creates duplicate resources, because they have a different local state file.

**Cause**: by default, Pulumi stores state in `~/.pulumi` on the local machine. Different machines have different state files — they do not know about each other's resources.

**Fix**: configure a shared backend:

```bash
# Option 1: Pulumi Cloud (free tier for personal use)
pulumi login https://app.pulumi.com

# Option 2: S3-backed state (for teams with AWS)
pulumi login s3://your-bucket/pulumi-state

# Option 3: self-hosted Pulumi backend
pulumi login file:///shared/nfs/pulumi-state   # NFS mount
```

After switching backend, migrate existing stacks:

```bash
pulumi stack export --stack aois-payments-prod | \
  pulumi stack import --stack aois-payments-prod
```

### 3. Crossplane Kubernetes Provider Not Configured — Composition Silently Does Nothing

**Symptom**: `AoisTenant` shows `SYNCED: True, READY: False`. The namespace is never created.

**Cause**: the Composition uses `kubernetes.crossplane.io/v1alpha1` resources, but the Crossplane Kubernetes provider is not installed.

**Fix**: install the Kubernetes provider:

```bash
kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-kubernetes
spec:
  package: "xpkg.upbound.io/crossplane-contrib/provider-kubernetes:v0.14.0"
EOF

# Wait for the provider to be healthy
kubectl get provider provider-kubernetes
# Expected: INSTALLED: True, HEALTHY: True
```

Then create a ProviderConfig that tells the provider to use the in-cluster kubeconfig:

```bash
kubectl apply -f - <<EOF
apiVersion: kubernetes.crossplane.io/v1alpha1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: InjectedIdentity   # use the pod's service account
EOF
```

### 4. `@kernel_function` Decorator Not Applied — SK Can't Discover the Function

**Symptom**: `kernel.plugins["AOIS"]` is registered but `kernel.plugins["AOIS"].functions` is empty.

**Cause**: the `@kernel_function` decorator is missing from the method, or the method is not `async`.

**Fix**: ensure the decorator is applied and the method signature is correct:

```python
class AOISPlugin:
    @kernel_function(description="Analyze a Kubernetes incident")   # ← required
    async def analyze_incident(self, incident: str) -> str:          # ← must be async
        ...
```

SK 1.x requires methods to be `async`. Synchronous methods decorated with `@kernel_function` are not discoverable in the plugin.

### 5. `pulumi preview` Shows Wrong Resources — Old Stack Selected

**Symptom**: `pulumi preview` shows resources for the standard stack even though you switched to the premium stack.

**Cause**: `pulumi stack select` selects a stack for the current session. If you opened a new terminal, the default stack is selected again (the one with the asterisk in `pulumi stack ls`).

**Fix**:
```bash
# Check which stack is selected
pulumi stack ls  # asterisk = currently selected

# Select the right stack
pulumi stack select aois-premium-preview
pulumi preview  # now shows premium resources
```

---

## Troubleshooting

### `crossplane: composite resource stuck in Syncing`

```bash
kubectl get events -n crossplane-system | grep -i error | tail -10
kubectl describe composite team-payments
```

Common causes:
- The provider is not installed (see Common Mistake #3 above)
- The ProviderConfig is missing or references the wrong service account
- The composed resource type in the Composition does not match the installed provider's API version

### `pulumi up: TypeNotFoundError`

**Exact error**:
```
error: resource type 'hcloud:index:Server' does not exist in the schema
```

**Cause**: the Pulumi provider for Hetzner (`pulumi-hcloud`) is not installed, or the type path is wrong.

**Fix**:
```bash
pip install pulumi-hcloud
# Correct type path: hcloud.Server (not hcloud:index:Server — that's Terraform syntax)
```

In Pulumi Python, resource types are Python classes, not strings. Check the provider's Python documentation for the correct class name and import path.

### `semantic_kernel: PluginInitializationError`

**Exact error**:
```
semantic_kernel.exceptions.PluginInitializationError: Plugin 'AOIS' could not be initialized.
```

**Cause**: the plugin class has a method that SK cannot introspect — usually because the method signature does not match SK's expected pattern (missing `self`, missing return type annotation, or not async).

**Fix**: ensure every `@kernel_function` method has this exact signature pattern:

```python
@kernel_function(description="...")
async def method_name(self, arg_name: str) -> str:
    ...
```

All arguments must be typed. The return type must be `str`. SK 1.x does not support other return types for `@kernel_function` methods without additional configuration.

### Crossplane XRD Shows `ESTABLISHED: False`

```bash
kubectl get xrd aoistenants.aois.io
# ESTABLISHED: False

kubectl describe xrd aoistenants.aois.io
# Look at Conditions section
```

Common cause: the XRD schema has a validation error — a field type mismatch or an invalid OpenAPI v3 schema. Fix the schema in `aois-tenant-xrd.yaml` and re-apply. The XRD only transitions to `ESTABLISHED: True` when the schema is valid.

---

## Connection to Later Phases

**v34.5 (Capstone)**: the IDP is how new teams onboard to AOIS in the capstone. The provisioning flow is demonstrated live — one `kubectl apply` command stands up a complete AOIS instance for a new tenant in under 5 minutes. The SRE on-call runbook references the IDP as the standard path for tenant provisioning. Without the IDP, the capstone is a single-tenant system — with it, it is a scalable platform.

**v33 (Red-teaming)**: when red-teaming is integrated into the CI pipeline, every new tenant provisioned via Crossplane automatically inherits the security posture defined in the composition — rate limits, input sanitization, guardrails. New tenants are not a new attack surface; they are copies of the hardened template. This is a key benefit of the IDP model.

---

## Mastery Checkpoint

You have completed v30 when you can do all of the following:

1. **Crossplane install and verify**: install Crossplane on the Hetzner cluster, apply the XRD and Composition, and verify `kubectl get crds | grep aois.io` shows the CRD. Show the full output.

2. **Provision a tenant**: run `kubectl apply` with an `AoisTenant` manifest. Wait for `SYNCED: True, READY: True`. Confirm `kubectl get namespace payments-aois` shows the namespace. Show both outputs.

3. **Pulumi standard vs. premium diff**: run `pulumi preview` for a standard tenant, then for a premium tenant. Show both outputs. Identify which resources appear only in the premium preview (ClickHouse, agentEvals CronJob). Explain how the `if model_tier == "premium":` Python conditional produces this difference.

4. **SK plugin invocation**: with AOIS running locally, run `test_sk.py` and get a valid analysis response from `kernel.invoke("AOIS", "analyze_incident", ...)`. Show the output.

5. **AWS EKS design** (no code required): what Crossplane resources would you need to provision AOIS as a new tenant on AWS EKS instead of Hetzner? List: the provider (AWS or EKS), the resources (namespace, IRSA service account, ECR pull credentials, Helm release), and their dependency order.

6. **SRE toil reduction argument**: explain to a CTO why the self-service IDP reduces SRE toil and what the risk is if the Crossplane Composition has a bug. What is the failure mode? How do you catch it before it affects 20 tenants?

7. **Python vs. HCL argument**: explain to a senior engineer what Pulumi's Python support gives you over Terraform's HCL that justifies the learning curve for teams that already know Terraform. Name one specific AOIS provisioning scenario where Python's expressiveness is needed and HCL would require a workaround.

8. **SK ecosystem argument**: explain to a Microsoft Azure architect why integrating AOIS as a Semantic Kernel plugin is more valuable than telling them to call the AOIS HTTP API directly. What does SK integration give them that a direct HTTP call does not?

**The mastery bar:** you can provision a complete AOIS tenant — namespace, RBAC, secrets, Helm release, ArgoCD app — with a single `kubectl apply` via Crossplane in under 5 minutes, with zero SRE intervention. You can demonstrate Pulumi's conditional provisioning handling premium vs. standard tiers differently from a single Python file. Any Microsoft enterprise AI application can call AOIS analysis as a native SK function.

---

## 4-Layer Tool Understanding

---

### Crossplane

| Layer | |
|---|---|
| **Plain English** | Provisioning a new AOIS instance for a team requires a server, a namespace, secrets, a Helm release, and an ArgoCD app — all done manually by an SRE today. Crossplane lets you define "AOIS tenant" as a Kubernetes object. The SRE defines the template once. Any team can provision themselves by creating the object. The provisioning takes 5 minutes instead of 3 days. |
| **System Role** | In the cluster control plane layer, above the infrastructure and below the application. Crossplane watches for `AoisTenant` objects and creates all underlying resources automatically. ArgoCD then deploys AOIS into the provisioned namespace. Together they are the self-service provisioning layer — Crossplane for infra, ArgoCD for app deployment. |
| **Technical** | A Kubernetes operator that extends the API with Composite Resource Definitions (XRDs). XRDs define the schema for composite resources (what fields an `AoisTenant` has). Compositions define how to translate a composite resource into underlying cloud resources (Kubernetes Objects, Helm Releases, cloud provider resources). Providers implement the actual API calls. The controller loop: watch for CRD objects → apply composition → reconcile actual state to desired. |
| **Remove it** | Without Crossplane: every new AOIS tenant is manually provisioned. The SRE creates the namespace, the secret, the Helm release, the ArgoCD app — in that order, without forgetting a step. At 10 teams, this is 50 hours of SRE time per month. Mistakes accumulate: missing namespace labels, wrong secret names, ArgoCD targeting the wrong cluster. Crossplane makes every tenant identical by construction. |

**Say it at three levels:**

- *Non-technical:* "Crossplane is a vending machine for infrastructure. You press a button (apply a YAML file), and a fully configured AOIS environment appears. The SRE configures the vending machine once; every team uses it self-service."

- *Junior engineer:* "`kubectl apply -f aois-tenant-xrd.yaml` creates the schema. `kubectl apply -f tenant-payments.yaml` creates the AoisTenant object. Crossplane's controller sees the object and creates the underlying resources (namespace, secrets, Helm release). Check status: `kubectl get aoistenants`. Describe for errors: `kubectl describe composite team-payments`. If `READY: True` and the namespace exists: provisioning succeeded."

- *Senior engineer:* "Crossplane's composition model has limits: compositions are YAML with patches and transforms — logic-heavy provisioning (conditionals, loops, external API calls) requires Crossplane Functions (a newer feature) or deferring to Pulumi. The practical split in AOIS: Crossplane handles the declarative, template-based parts (namespace, RBAC, standard secrets); Pulumi handles conditional provisioning (ClickHouse for premium only). State management: Crossplane keeps provisioned resource references in the composite resource's status. If you delete the `AoisTenant`, Crossplane garbage-collects all composed resources. This is correct behavior in production; it is dangerous in development if you accidentally delete a tenant object."

---

### Pulumi

| Layer | |
|---|---|
| **Plain English** | Terraform's configuration language cannot cleanly say "if this tenant is premium, also provision ClickHouse." Pulumi lets you write infrastructure in Python — real if statements, real loops, real function calls. The AOIS provisioning logic is 20 lines of Python that any developer can read. The equivalent Terraform is 80 lines of HCL that requires knowing Terraform's `count`, `for_each`, and `dynamic` block patterns. |
| **System Role** | The provisioning layer for complex, conditional AOIS infrastructure that Crossplane's YAML-based compositions cannot express. Premium tenants need ClickHouse and hourly eval CronJobs; standard tenants do not. Pulumi handles this in three lines of Python. The same Pulumi Python file provisions both tenant types — the `model_tier` config value drives the conditional logic. |
| **Technical** | An IaC platform where infrastructure is declared as Python objects. `pulumi up` computes a diff between current state (stored in a configured backend — local, S3, or Pulumi Cloud) and the desired state (the Python program). Only changed resources are updated. `pulumi preview` shows the diff without applying it. Stacks are named environments (`aois-payments-prod`, `aois-analytics-staging`) — each has independent state and config. |
| **Remove it** | Without Pulumi: use Terraform for complex provisioning. Every conditional becomes `count = condition ? 1 : 0`. Loops require `for_each` over complex map structures. External API calls during provisioning are not possible — Terraform is declarative, not imperative. When the provisioning logic has real complexity (different resources per tier, API lookups, computed values), Terraform's HCL becomes unmaintainable. New engineers take weeks to understand it. With Pulumi in Python, the provisioning code reads like application code. |

**Say it at three levels:**

- *Non-technical:* "Pulumi is like Terraform but written in Python instead of a special configuration language. If you already know Python, you can read and modify Pulumi infrastructure code. The `if model_tier == 'premium':` line is exactly what it says."

- *Junior engineer:* "`pulumi stack init my-stack` creates a stack. `pulumi config set key value` sets configuration. `pulumi preview` shows what would happen. `pulumi up` applies it. `pulumi destroy` tears it down. Every resource is a Python object: `k8s.core.v1.Namespace('name', metadata=k8s.meta.v1.ObjectMetaArgs(name='...'))`. The `pulumi.ResourceOptions(depends_on=[namespace])` is how you express dependencies — the Helm release waits for the namespace."

- *Senior engineer:* "Pulumi's state model is explicit — the backend stores the current state as a JSON blob. The diff is computed by running the Python program (desired state) and comparing to the stored JSON (current state). This means the Python program is executed on every `preview` and `up` — side effects in the Python program happen on every run, which is a footgun. Keep infrastructure Python side-effect-free outside of Pulumi resource declarations. The Pulumi Automation API enables calling Pulumi from within application code (e.g., an IDP portal triggers `pulumi up` programmatically) — this is the production path for the self-service provisioning flow."

---

### Semantic Kernel

| Layer | |
|---|---|
| **Plain English** | Microsoft's enterprise customers build AI applications in .NET using Semantic Kernel. AOIS is Python. Without an SK plugin, enterprise Microsoft teams cannot use AOIS from their SK apps — they would need to rebuild the analysis logic in .NET. The plugin bridges the gap: AOIS analysis is available as a native SK function to any SK application, in any language. |
| **System Role** | An adapter layer. The `AOISPlugin` wraps AOIS's HTTP `/analyze` API in SK's plugin interface. Any SK kernel that calls `kernel.add_plugin(AOISPlugin())` can invoke `AOIS.analyze_incident` as a native SK function. AOIS participates in Microsoft's AI orchestration ecosystem — the planner can automatically chain AOIS analysis with Jira ticket creation, Slack notification, and PagerDuty escalation. |
| **Technical** | Microsoft's AI orchestration SDK for .NET (and Python). Plugins are classes with `@kernel_function` decorated async methods. The SK planner routes user requests to the right function based on the method's description string. `Kernel.invoke(plugin_name, function_name, **kwargs)` calls the function directly. `Kernel.add_plugin(plugin_instance, plugin_name)` registers a plugin. The `@kernel_function` description is used for automatic function selection by the planner — it is essentially a natural language routing hint. |
| **Remove it** | Without SK integration: enterprise Microsoft customers call AOIS's HTTP API directly. No SK planner. No automatic composition with other skills. No native SK types. AOIS is invisible to the Microsoft AI ecosystem. Microsoft has the largest enterprise AI deployment footprint in the world — enterprises building on Azure + Copilot + SK represent the majority of enterprise AI spend. Being absent from SK means being absent from that ecosystem. |

**Say it at three levels:**

- *Non-technical:* "Semantic Kernel is the AI assistant framework for Microsoft enterprise applications. The AOIS plugin makes AOIS available as a tool that Microsoft AI assistants can use. When an enterprise's internal AI assistant needs to analyze a Kubernetes incident, it calls AOIS through Semantic Kernel — no custom integration required."

- *Junior engineer:* "`kernel = Kernel()` creates the kernel. `kernel.add_plugin(AOISPlugin(), plugin_name='AOIS')` registers the plugin. `await kernel.invoke('AOIS', 'analyze_incident', incident='...')` calls the function. The `@kernel_function(description='...')` decorator is how SK discovers the function — without it, the method is invisible to the kernel. All `@kernel_function` methods must be `async`."

- *Senior engineer:* "The SK plugin model is function-calling at the SDK level. The description string in `@kernel_function` is used by the planner for automatic function selection — the quality of the description affects planner accuracy. For AOIS, 'Analyze a Kubernetes incident and return severity + proposed action' is good; 'Analyze thing' is not. The SK planner is an LLM that receives all registered function descriptions and decides which to call — the planner's underlying model (GPT-4o or Claude) affects the orchestration quality. In production: the plugin description is as important as the function implementation."
