# v12 — EKS: Enterprise Kubernetes
⏱ **Estimated time: 5–7 hours**

## What this version builds

v6 gave you k3s on Hetzner — real Kubernetes, single node, €4.15/month. That is the right choice for a learning project and for cost-sensitive production workloads. v12 gives you EKS — Kubernetes as enterprises actually run it.

The difference is not Kubernetes itself (the control plane concepts are identical). The difference is the surrounding AWS ecosystem: IAM Roles for Service Accounts (IRSA) instead of API keys, Karpenter for intelligent node provisioning, ECR for image storage, CloudWatch for logs, and the integration with every other AWS service AOIS uses (Bedrock, Lambda, Secrets Manager).

At the end of v12:
- **EKS cluster running** — provisioned with `eksctl`, managed control plane
- **AOIS deployed to EKS** — same Helm chart from v7, different values file
- **IRSA configured** — pods authenticate to Bedrock via IAM role, zero static credentials
- **ECR used for images** — GHCR replaced with AWS-native registry
- **Karpenter installed** — nodes provision in 60 seconds when load spikes
- **Hetzner vs EKS comparison made** — you know when to choose each

---

## Prerequisites

- v9–v11 complete: Helm chart at `charts/aois/`, ArgoCD on Hetzner, Lambda deployed
- AWS CLI configured: `aws sts get-caller-identity` returns `aois-dev` user
- `eksctl` installed (covered in Step 0)
- `kubectl` installed (already present from v6)

Verify:
```bash
aws sts get-caller-identity --query 'Arn' --output text
kubectl version --client --short 2>/dev/null || kubectl version --client
```
Expected:
```
arn:aws:iam::739275471358:user/aois-dev
Client Version: v1.x.x
```

---

## Learning Goals

By the end of this version you will be able to:
- Explain what EKS manages vs what you manage, and how that differs from k3s
- Provision an EKS cluster with `eksctl` and connect `kubectl` to it
- Explain IRSA — how pods get AWS credentials without static secrets
- Configure IRSA so AOIS pods can call Bedrock using a pod-scoped IAM role
- Push a Docker image to ECR and deploy it to EKS
- Deploy AOIS to EKS using the existing Helm chart with a new values file
- Install Karpenter and explain how it differs from the Cluster Autoscaler
- Compare Hetzner k3s vs EKS on cost, complexity, and when to choose each

---

## Why EKS Exists

k3s on Hetzner gives you Kubernetes. EKS gives you Kubernetes plus everything that enterprises need around it.

The control plane difference:
- **k3s**: you own the control plane. If the master node dies, your cluster is gone until you rebuild it. You manage etcd, the API server, the scheduler.
- **EKS**: AWS owns the control plane. It runs across multiple availability zones, is automatically patched, and has a 99.95% uptime SLA. You never SSH into a master node — there is no master node you can access.

The authentication difference:
- **k3s on Hetzner**: AOIS uses an API key to call Bedrock. The key is in a Kubernetes Secret. If someone reads that Secret, they have your Bedrock access permanently.
- **EKS with IRSA**: AOIS uses a temporary IAM role credential that expires in hours. The credential is injected by AWS into the pod automatically. There is no secret to steal — the credential is ephemeral and scoped to exactly the permissions the pod needs.

The node management difference:
- **k3s**: you provision nodes manually (Terraform + Hetzner). If you need more nodes, you run Terraform.
- **EKS + Karpenter**: Karpenter watches for unschedulable pods and provisions exactly the right EC2 instance type in ~60 seconds. When pods are removed, Karpenter terminates the node. You never manually manage nodes.

These differences explain why every regulated enterprise runs EKS (or GKE or AKS) and not k3s.

---

## Step 0: Install eksctl

`eksctl` is the official CLI for creating and managing EKS clusters. It generates CloudFormation stacks under the hood.

```bash
# Install eksctl
curl --silent --location "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_Linux_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin 2>/dev/null || mv /tmp/eksctl ~/.local/bin/
eksctl version
```
Expected: `0.x.x`

Verify your IAM user has the permissions needed to create an EKS cluster. `aois-dev` has `AdministratorAccess` so this is covered.

---

## Step 1: Provision the EKS Cluster

EKS has a control plane cost: **$0.10/hour** (~$72/month) regardless of whether any nodes are running. This is AWS's fee for managing the Kubernetes API server.

**Important: tear down the cluster when you are done with this version.** The teardown command is in the Mastery Checkpoint. Running EKS 24/7 costs real money.

Create the cluster configuration:

```bash
cat > /tmp/eks-cluster.yaml << 'EOF'
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig

metadata:
  name: aois-cluster
  region: us-east-1
  version: "1.31"

iam:
  withOIDC: true   # Required for IRSA — enables the OIDC provider

managedNodeGroups:
  - name: aois-nodes
    instanceType: t3.medium   # 2 vCPU, 4GB RAM — sufficient for AOIS
    minSize: 1
    maxSize: 3
    desiredCapacity: 1
    privateNetworking: false   # public nodes for simplicity in learning
    labels:
      role: worker
EOF
```

Provision the cluster:
```bash
eksctl create cluster -f /tmp/eks-cluster.yaml
```

This takes **15–20 minutes**. It creates:
- VPC with public and private subnets across 2 AZs
- EKS control plane (managed by AWS)
- 1 t3.medium worker node (managed node group)
- OIDC provider (required for IRSA)
- kubeconfig entry so `kubectl` connects to EKS automatically

Watch the progress — `eksctl` prints each CloudFormation stack as it creates. You will see: VPC → subnets → security groups → EKS control plane → node group → OIDC provider.

▶ **STOP — do this now**

Once the cluster is up, verify `kubectl` is pointed at EKS:
```bash
kubectl config current-context
kubectl get nodes
```
Expected:
```
kolinzking@aois-cluster.us-east-1.eksctl.io

NAME                          STATUS   ROLES    AGE   VERSION
ip-192-168-x-x.ec2.internal   Ready    <none>   2m    v1.31.x
```
`STATUS: Ready` — your EKS node is running. Check cost awareness:
```bash
# This cluster is now costing $0.10/hour for the control plane
# plus ~$0.046/hour for the t3.medium node
# Total: ~$0.146/hour = ~$3.50/day if left running
echo "Cluster running. Remember to delete when done: eksctl delete cluster --name aois-cluster --region us-east-1"
```

---

## Step 2: IRSA — The Right Way to Authenticate in AWS

IRSA (IAM Roles for Service Accounts) is how pods on EKS get AWS credentials without static secrets. This is the pattern every AWS-native application uses.

**How it works:**

```
Pod starts
  → AWS injects a projected service account token (a JWT) into the pod
  → Pod's code calls AWS STS: "I am this service account, here is my JWT"
  → STS validates the JWT against the EKS OIDC provider
  → STS returns temporary credentials (15min–12hr lifetime)
  → Pod uses temporary credentials to call Bedrock
  → Credentials expire, pod gets new ones automatically
```

No API key. No Kubernetes Secret with credentials. No rotation needed. If someone steals the temporary credentials, they expire in hours.

**Set up IRSA for AOIS:**

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create the IAM role that AOIS pods will assume
eksctl create iamserviceaccount \
  --name aois-service-account \
  --namespace aois \
  --cluster aois-cluster \
  --region us-east-1 \
  --attach-policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/AOISBedrockPolicy \
  --approve \
  --override-existing-serviceaccounts
```

This command:
1. Creates a Kubernetes ServiceAccount named `aois-service-account` in the `aois` namespace
2. Creates an IAM role with a trust policy that allows the EKS OIDC provider to assume it
3. Attaches `AOISBedrockPolicy` to the role
4. Annotates the ServiceAccount with the role ARN

Verify the ServiceAccount was created with the annotation:
```bash
kubectl get serviceaccount aois-service-account -n aois -o yaml
```
Expected — look for the annotation:
```yaml
metadata:
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::739275471358:role/eksctl-aois-cluster-addon-iamserviceaccount-...
```
This annotation is what IRSA reads. When a pod uses this ServiceAccount, AWS automatically injects the temporary credentials for the annotated role.

▶ **STOP — do this now**

Verify the IAM role was created and has the right trust policy:
```bash
ROLE_NAME=$(aws iam list-roles \
  --query 'Roles[?contains(RoleName, `aois-cluster-addon-iamserviceaccount`)].RoleName' \
  --output text)

echo "Role: $ROLE_NAME"

aws iam get-role --role-name $ROLE_NAME \
  --query 'Role.AssumeRolePolicyDocument.Statement[0].Principal' \
  --output json
```
Expected — the trust principal is the OIDC provider, not `lambda.amazonaws.com` or a user:
```json
{
    "Federated": "arn:aws:iam::739275471358:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/XXXX"
}
```
This is the IRSA trust relationship. The role can only be assumed by pods running on this specific EKS cluster with this specific ServiceAccount. Not by users, not by Lambda, not by any other cluster.

---

## Step 3: Push AOIS Image to ECR

EKS can pull from GHCR, but the production pattern is to use ECR — AWS's container registry. It integrates with IAM, has no rate limits, and doesn't require external credentials.

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

# Create the ECR repository
aws ecr create-repository \
  --repository-name aois \
  --region $REGION \
  --query 'repository.repositoryUri' \
  --output text
```
Expected: `739275471358.dkr.ecr.us-east-1.amazonaws.com/aois`

Authenticate Docker to ECR and push the image:
```bash
# Login to ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin \
  ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Pull the existing image from GHCR and retag for ECR
docker pull ghcr.io/kolinzking/aois:v6
docker tag ghcr.io/kolinzking/aois:v6 \
  ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/aois:v12

# Push to ECR
docker push ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/aois:v12
```

Verify the image is in ECR:
```bash
aws ecr describe-images \
  --repository-name aois \
  --region $REGION \
  --query 'imageDetails[0].{tag:imageTags[0],pushed:imagePushedAt,size:imageSizeInBytes}' \
  --output json
```
Expected:
```json
{
    "tag": "v12",
    "pushed": "2026-xx-xxTxx:xx:xxZ",
    "size": 89234567
}
```

---

## Step 4: Deploy AOIS to EKS

The same Helm chart from v7 deploys to EKS — that was the point of parameterising it. Create an EKS-specific values file:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > charts/aois/values.eks.yaml << EOF
replicaCount: 2

image:
  repository: ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/aois
  tag: v12

serviceAccount:
  create: false
  name: aois-service-account   # uses the IRSA service account

ingress:
  enabled: false   # no ingress on EKS for now — use kubectl port-forward

resources:
  requests:
    memory: "512Mi"
    cpu: "200m"
  limits:
    memory: "1Gi"
    cpu: "1000m"

keda:
  enabled: false   # KEDA not installed on EKS yet — added in v17
EOF
```

The ServiceAccount templates in the Helm chart need a small addition to support IRSA. Update `charts/aois/templates/deployment.yaml` to reference the service account:

```bash
# Check if serviceAccountName is already in the deployment template
grep -n "serviceAccountName\|serviceAccount" charts/aois/templates/deployment.yaml
```

If not present, the deployment needs `spec.template.spec.serviceAccountName`. This is what tells Kubernetes which ServiceAccount (and therefore which IAM role) the pod uses.

Deploy to EKS:
```bash
# Ensure kubectl is pointing at EKS
kubectl config use-context kolinzking@aois-cluster.us-east-1.eksctl.io

# Create the namespace
kubectl create namespace aois --dry-run=client -o yaml | kubectl apply -f -

# Deploy
helm upgrade --install aois ./charts/aois \
  -f charts/aois/values.eks.yaml \
  -n aois

# Watch pods come up
kubectl get pods -n aois -w
```
Expected:
```
NAME                    READY   STATUS    RESTARTS   AGE
aois-7d9f4b8c6-xk2mj   1/1     Running   0          45s
aois-7d9f4b8c6-p9mn2   1/1     Running   0          45s
```

▶ **STOP — do this now**

Verify IRSA is working — exec into a pod and check that AWS credentials are present:
```bash
kubectl exec -it -n aois $(kubectl get pod -n aois -o name | head -1) -- env | grep AWS
```
Expected:
```
AWS_ROLE_ARN=arn:aws:iam::739275471358:role/eksctl-aois-cluster-addon-iamserviceaccount-...
AWS_WEB_IDENTITY_TOKEN_FILE=/var/run/secrets/eks.amazonaws.com/serviceaccount/token
```
These two environment variables are injected by the EKS Pod Identity Webhook. `AWS_WEB_IDENTITY_TOKEN_FILE` is the JWT that gets exchanged for temporary credentials. There is no `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` — credentials are fetched on demand from STS. This is IRSA in action.

Test that the pod can actually reach Bedrock (once daily quota is reset):
```bash
kubectl exec -it -n aois $(kubectl get pod -n aois -o name | head -1) -- \
  python3 -c "
import boto3
client = boto3.client('bedrock', region_name='us-east-1')
models = client.list_foundation_models()
print('Bedrock reachable from EKS pod via IRSA:', len(models['modelSummaries']), 'models')
"
```
Expected: `Bedrock reachable from EKS pod via IRSA: N models`

---

## Step 5: Install Karpenter

The managed node group from `eksctl` uses the Cluster Autoscaler pattern: you define min/max nodes, and the autoscaler adds/removes nodes within those bounds. Karpenter is different — it does not need predefined node groups. It reads the pod requirements and provisions the exact right instance type.

```bash
# Set environment variables
export KARPENTER_NAMESPACE=kube-system
export KARPENTER_VERSION=1.0.0
export CLUSTER_NAME=aois-cluster
export AWS_DEFAULT_REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create the Karpenter node role
cat > /tmp/karpenter-node-trust.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ec2.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name KarpenterNodeRole-${CLUSTER_NAME} \
  --assume-role-policy-document file:///tmp/karpenter-node-trust.json

for policy in AmazonEKSWorkerNodePolicy AmazonEKS_CNI_Policy AmazonEC2ContainerRegistryReadOnly AmazonSSMManagedInstanceCore; do
  aws iam attach-role-policy \
    --role-name KarpenterNodeRole-${CLUSTER_NAME} \
    --policy-arn arn:aws:iam::aws:policy/${policy}
done

# Create instance profile for the node role
aws iam create-instance-profile --instance-profile-name KarpenterNodeInstanceProfile-${CLUSTER_NAME}
aws iam add-role-to-instance-profile \
  --instance-profile-name KarpenterNodeInstanceProfile-${CLUSTER_NAME} \
  --role-name KarpenterNodeRole-${CLUSTER_NAME}

# Install Karpenter via Helm
helm registry logout public.ecr.aws 2>/dev/null || true
helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
  --version ${KARPENTER_VERSION} \
  --namespace ${KARPENTER_NAMESPACE} \
  --set settings.clusterName=${CLUSTER_NAME} \
  --set settings.interruptionQueue=${CLUSTER_NAME} \
  --wait
```

Create a NodePool and NodeClass — these tell Karpenter what kinds of nodes to provision:

```bash
cat << EOF | kubectl apply -f -
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["t3.medium", "t3.large", "t3a.medium"]
  limits:
    cpu: "10"
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 1m
---
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiSelectorTerms:
    - alias: al2023@latest
  role: KarpenterNodeRole-${CLUSTER_NAME}
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: ${CLUSTER_NAME}
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: ${CLUSTER_NAME}
EOF
```

▶ **STOP — do this now**

Scale AOIS to more replicas than the current node can handle — watch Karpenter provision a new node:
```bash
# Scale to 5 replicas (likely to exceed current node capacity)
kubectl scale deployment aois -n aois --replicas=5

# Watch for unschedulable pods — Karpenter should respond within 60 seconds
kubectl get pods -n aois -w &
kubectl get nodes -w
```
Expected: within 60 seconds, a new node appears with status `Ready`, and the pending pods move to `Running`. This is Karpenter in action — no predefined node group, no manual intervention.

```bash
# Scale back down — Karpenter will terminate the extra node after consolidation
kubectl scale deployment aois -n aois --replicas=2
```

---

## Step 6: Hetzner k3s vs EKS — The Decision Framework

You now have both running. Here is the honest comparison:

| Dimension | Hetzner k3s | AWS EKS |
|-----------|------------|---------|
| Control plane cost | ~€0 (included in node) | $0.10/hr ($72/month) |
| Node cost | €4.15/month (CX11) | ~$0.046/hr t3.medium ($33/month) |
| Total minimum cost | ~€4.15/month | ~$105/month |
| Control plane HA | Manual (single node = single point of failure) | Managed, multi-AZ, 99.95% SLA |
| Authentication | API keys in Secrets | IRSA — zero static credentials |
| Node provisioning | Manual Terraform | Karpenter — automatic in 60s |
| AWS service integration | Via API keys | Native via IAM |
| Compliance (SOC2/HIPAA) | Requires custom work | Built-in audit trail, controls |
| Best for | Learning, personal projects, cost-sensitive | Enterprise, regulated, AWS-native |

**When to choose Hetzner k3s:**
- Personal project or startup with no compliance requirements
- Monthly budget under $20
- Team is comfortable managing the control plane
- Workload does not need native AWS service integration

**When to choose EKS:**
- Enterprise or regulated environment
- Using Bedrock, Lambda, Secrets Manager extensively
- Need IRSA (no static credentials policy)
- Need Karpenter for intelligent autoscaling
- SLA requirements for the control plane

**AOIS production stance:** Hetzner for the learning project (this repo). EKS for enterprise deployment. Same Helm chart, different values file — which is why v7 parameterised everything.

---

## Common Mistakes

**`kubectl` still pointing at Hetzner after EKS creation** *(recognition)*
`eksctl create cluster` updates your kubeconfig automatically, but if you have multiple clusters, context can drift.
```bash
kubectl get nodes  # shows Hetzner nodes instead of EKS
```
*(recall — trigger it)*
```bash
# List all contexts
kubectl config get-contexts

# Switch to EKS
kubectl config use-context kolinzking@aois-cluster.us-east-1.eksctl.io

# Switch back to Hetzner
kubectl config use-context default

# Verify which you're on
kubectl config current-context
```
Always check `kubectl config current-context` before running cluster operations. Running `kubectl delete` on the wrong cluster is a bad day.

---

**IRSA not working — pod cannot call Bedrock despite correct policy** *(recognition)*
IRSA requires three things to be aligned: the ServiceAccount annotation, the IAM role trust policy referencing the OIDC provider, and the pod's `serviceAccountName`. If any one is missing, AWS credentials are not injected.
```
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```
*(recall — trigger it)*
```bash
# Deploy a pod without the IRSA service account
kubectl run test-no-irsa --image=amazon/aws-cli --restart=Never -n aois \
  -- aws sts get-caller-identity

kubectl logs test-no-irsa -n aois
# Unable to locate credentials
kubectl delete pod test-no-irsa -n aois

# Deploy with the IRSA service account
kubectl run test-with-irsa --image=amazon/aws-cli --restart=Never -n aois \
  --overrides='{"spec":{"serviceAccountName":"aois-service-account"}}' \
  -- aws sts get-caller-identity

kubectl logs test-with-irsa -n aois
# Shows the assumed role ARN — credentials injected successfully
kubectl delete pod test-with-irsa -n aois
```
The difference is `serviceAccountName`. Without it: no credentials. With it: IRSA injects temporary credentials automatically.

---

**EKS nodes in `NotReady` after creation** *(recognition)*
The managed node group takes 3–5 minutes to join the cluster after `eksctl` reports success. Nodes go through: `Pending → NotReady → Ready`.
```bash
kubectl get nodes
# NAME    STATUS     ROLES    AGE   VERSION
# ip-... NotReady   <none>   30s   v1.31.x
```
*(recall — trigger it)*
```bash
# Check node conditions
kubectl describe node $(kubectl get node -o name | head -1) | grep -A5 "Conditions:"
# Look for: KubeletReady — False, reason: NodeStatusUnknown
```
Fix: wait 2–3 minutes. If still `NotReady` after 5 minutes:
```bash
kubectl get events --sort-by='.lastTimestamp' | tail -10
# Usually shows: "Failed to pull image" or "NetworkPlugin not initialized"
```

---

**Karpenter not provisioning nodes — pods stuck in `Pending`** *(recognition)*
Karpenter requires the subnet and security group tags `karpenter.sh/discovery: CLUSTER_NAME` to find where to launch nodes. If `eksctl` did not tag subnets correctly, Karpenter cannot find them.
```bash
kubectl get pods -n aois   # Pending for >2 minutes
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter | grep -i "error\|failed"
```
*(recall — trigger it)*
```bash
# Check if subnets have the required tag
aws ec2 describe-subnets --region us-east-1 \
  --filters "Name=tag:karpenter.sh/discovery,Values=aois-cluster" \
  --query 'Subnets[].SubnetId' --output text
```
Expected: 2–3 subnet IDs. If empty, the subnets are not tagged — `eksctl create cluster` with `withOIDC: true` should tag them automatically. If missing: tag them manually and restart Karpenter.

---

## Troubleshooting

**`eksctl create cluster` fails with `AlreadyExistsException`:**
A cluster with that name already exists (possibly from a previous failed run).
```bash
eksctl get cluster --region us-east-1
eksctl delete cluster --name aois-cluster --region us-east-1
# Then re-run create
```

**Helm deploy fails with `ServiceAccount not found`:**
The IRSA service account creation (`eksctl create iamserviceaccount`) must complete before the Helm deploy. Check:
```bash
kubectl get serviceaccount -n aois
# If aois-service-account is not listed, re-run the eksctl iamserviceaccount command
```

**Pod crashes with `exec /usr/local/bin/python3: exec format error`:**
The Docker image in ECR was built for a different architecture. Verify:
```bash
docker manifest inspect 739275471358.dkr.ecr.us-east-1.amazonaws.com/aois:v12 | grep architecture
# Must show: "amd64" — EKS t3 nodes are x86_64
```

**`kubectl exec` into pod fails — no shell available:**
The distroless image from v4 has no shell. Use `kubectl debug` instead:
```bash
kubectl debug -it -n aois $(kubectl get pod -n aois -o name | head -1) \
  --image=busybox --target=aois
```

---

## Connection to later phases

- **v16 (OpenTelemetry)**: EKS pods emit OTel traces exactly like k3s pods — same instrumentation code. The difference is where traces go: on EKS you can route to AWS X-Ray natively or to your Grafana stack. Both options shown in v16.
- **v17 (Kafka)**: Strimzi Kafka operator deploys to EKS identically to k3s. KEDA on EKS scales pods based on Kafka lag — same ScaledObject from v9 works here. The production pattern is EKS + Kafka + KEDA.
- **v23 (LangGraph)**: The autonomous agent loop runs on EKS with IRSA — each agent node gets the exact AWS permissions it needs. The Detector agent gets Bedrock + CloudWatch read. The Remediation agent gets additional k8s write permissions.
- **v28 (CI/CD)**: GitHub Actions will build, push to ECR, and deploy to EKS. OIDC authentication between GitHub and AWS means no AWS credentials in GitHub Secrets — the same IRSA pattern applied to CI/CD.

---

## Mastery Checkpoint

**1. The IRSA flow from memory**
Without notes: draw or describe the IRSA flow step by step — from "pod starts" to "pod has temporary AWS credentials." Include: the JWT token file, the STS AssumeRoleWithWebIdentity call, the OIDC provider validation, and the temporary credential lifetime. If you cannot describe this, re-read Step 2 until you can explain it to someone who has never heard of IRSA.

**2. Context switching**
```bash
# Switch to Hetzner, verify AOIS is running there
kubectl config use-context default
kubectl get pods -n aois

# Switch to EKS, verify AOIS is running there
kubectl config use-context kolinzking@aois-cluster.us-east-1.eksctl.io
kubectl get pods -n aois
```
AOIS should be running on both clusters simultaneously. Same code, same Helm chart, different infrastructure. This is why Helm values files exist.

**3. Prove IRSA works without a secret**
```bash
kubectl get secret -n aois   # should show no AWS credential secrets
kubectl exec -it -n aois $(kubectl get pod -n aois -o name | head -1) \
  -- env | grep -E "AWS_ROLE|AWS_WEB_IDENTITY"
```
The pod has AWS access (IRSA env vars present) and no secret. Explain to yourself why this is more secure than the k3s setup where the Anthropic API key lives in a Kubernetes Secret.

**4. Karpenter scale test**
Scale AOIS to 8 replicas. Time how long it takes from `kubectl scale` to all pods `Running`. Then scale back to 2. Time how long Karpenter takes to terminate the extra node (consolidation). Record both numbers — these are your Karpenter SLA.

**5. The cost calculation**
Calculate the monthly cost of running this EKS cluster (1 t3.medium node, 2 AOIS replicas) vs the Hetzner k3s setup. At what point (requests/day, team size, compliance requirement) does the EKS cost become justified? Write a 3-sentence answer.

**6. Teardown — prove you can destroy and rebuild**
```bash
# Delete AOIS from EKS
helm uninstall aois -n aois

# Delete the EKS cluster (stops the $0.10/hr control plane charge)
eksctl delete cluster --name aois-cluster --region us-east-1
```
This takes 10–15 minutes. Watch the CloudFormation stacks delete in order. Verify in the AWS console that no EKS resources remain. The cluster is gone — you can rebuild it from the config file in under 20 minutes. That is infrastructure as code working correctly.

**The mastery bar:** You can provision an EKS cluster, configure IRSA so pods authenticate to AWS without static credentials, deploy AOIS using the existing Helm chart, install Karpenter, and explain the cost and compliance trade-offs between Hetzner k3s and EKS. You can tear down the cluster completely and rebuild it from the config file.
