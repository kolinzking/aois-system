# v10 — Amazon Bedrock + Bedrock Agents
⏱ **Estimated time: 4–6 hours**

## What this version builds

v9 gave AOIS elastic scaling. v10 gives it enterprise deployment.

Right now AOIS calls the Anthropic API directly — your API key leaves your infrastructure, there is no compliance boundary, no audit trail of who called what when, and Anthropic manages the model endpoint. That is fine for a personal project. It is a blocker in any regulated enterprise (finance, healthcare, government).

Amazon Bedrock solves this. It is Claude — the same model — running inside AWS's compliance boundary. You authenticate with IAM roles instead of API keys. Every call is logged in CloudTrail. Data never leaves your AWS region. Enterprises can tick the boxes: SOC 2, HIPAA, GDPR.

At the end of v10:
- **AOIS routes to Claude via Bedrock** — same Pydantic output, different backend
- **IAM role authentication** — no API keys in AWS, the right way to authenticate
- **LiteLLM routes to Bedrock seamlessly** — one config change, not a code rewrite
- **Latency + cost comparison measured** — Anthropic direct vs Bedrock, real numbers
- **Bedrock Agents wired up** — AOIS exposed as a managed AWS agent with tool routing
- **You understand the enterprise AI stack** — why every large company uses Bedrock over direct API

---

## Prerequisites

- v9 complete: KEDA running, ArgoCD Synced Healthy, AOIS live at https://aois.46.225.235.51.nip.io
- AWS account with permissions to: create IAM roles/policies, enable Bedrock model access, call Bedrock APIs
- AWS CLI installed and configured

Verify AWS CLI is configured:
```bash
aws sts get-caller-identity
```
Expected:
```json
{
    "UserId": "AIDAXXXXXXXXXXXXXXXXX",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-username"
}
```

Verify Bedrock is accessible in your region:
```bash
aws bedrock list-foundation-models --region us-east-1 --query 'modelSummaries[?contains(modelId, `claude`)].modelId' --output table
```
Expected — a list including:
```
anthropic.claude-3-5-sonnet-20241022-v2:0
anthropic.claude-3-haiku-20240307-v1:0
```
If you see "Access denied" or an empty list, you need to enable model access in the AWS Bedrock console first (covered in Step 1).

---

## Learning Goals

By the end of this version you will be able to:
- Explain why enterprises use Bedrock instead of direct Anthropic API and what compliance guarantees it provides
- Enable Claude model access in the Bedrock console and call it with the AWS CLI
- Authenticate to Bedrock using IAM roles (not API keys) and explain why roles are the correct pattern in AWS
- Modify LiteLLM config to route to Bedrock with zero application code changes
- Measure and compare latency and cost between Anthropic direct and Bedrock
- Explain what Bedrock Agents adds over raw Bedrock model calls and when to use each
- Create a Bedrock Agent that uses AOIS-style analysis as a tool

---

## Why Bedrock Exists

Anthropic gives you the best model. AWS gives you the compliance wrapper around it.

When a bank or hospital deploys AI, their legal team asks: where does the data go? Who has access to it? What is the audit trail? How do we prove to regulators that PII never left our cloud environment?

Calling `api.anthropic.com` fails all of these:
- Data transits Anthropic's network
- No integration with AWS CloudTrail audit logs
- No VPC PrivateLink option (data leaves your network boundary)
- Authentication is an API key — a static secret that can leak

Bedrock answers all of them:
- Model runs inside AWS's infrastructure in your chosen region
- Every API call logged automatically in CloudTrail: who called, when, which model, how many tokens
- VPC PrivateLink available: AOIS on EKS can call Bedrock without traffic ever hitting the public internet
- Authentication via IAM roles: temporary credentials that expire, tied to your workload identity, no static secrets

The model is identical. The compliance posture is completely different. This is why every enterprise AI deployment you will encounter in production is on Bedrock (or Azure OpenAI, the Microsoft equivalent).

---

## Step 1: Enable Claude Model Access in Bedrock

AWS requires you to explicitly request access to each model before you can call it. This is a one-time console step.

1. Open the AWS Console → Amazon Bedrock → Model access (left sidebar)
2. Click "Modify model access"
3. Find "Anthropic" → check "Claude 3.5 Sonnet" and "Claude 3 Haiku"
4. Submit the request

Access is usually granted within 1–5 minutes for Claude models. Some models (like Claude 3 Opus) may require a use case description.

▶ **STOP — do this now**

Verify access was granted:
```bash
aws bedrock list-foundation-models \
  --region us-east-1 \
  --query 'modelSummaries[?contains(modelId, `claude`)].{id:modelId,access:modelLifecycle.status}' \
  --output table
```
Expected — status `ACTIVE` for the models you requested:
```
-----------------------------------------------------------------
|                    ListFoundationModels                       |
+---------------------------------------------+-----------------+
|                      id                     |     access      |
+---------------------------------------------+-----------------+
|  anthropic.claude-3-5-sonnet-20241022-v2:0  |  ACTIVE         |
|  anthropic.claude-3-haiku-20240307-v1:0     |  ACTIVE         |
+---------------------------------------------+-----------------+
```

Then make a raw CLI call to prove the model is reachable:
```bash
aws bedrock-runtime invoke-model \
  --region us-east-1 \
  --model-id anthropic.claude-3-haiku-20240307-v1:0 \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":100,"messages":[{"role":"user","content":"Reply with: Bedrock is working"}]}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/bedrock-test.json && cat /tmp/bedrock-test.json
```
Expected:
```json
{"id":"msg_...","type":"message","role":"assistant","content":[{"type":"text","text":"Bedrock is working"}],...}
```
If you see this, Claude is running inside AWS and responding through your IAM credentials. The Anthropic API key is not involved at all.

---

## Step 2: IAM — The Right Way to Authenticate in AWS

You just called Bedrock using the credentials from `aws sts get-caller-identity` — likely a user with an access key. That works, but it is not the production pattern.

In production, services authenticate with **IAM roles**, not access keys. The difference:

| Access Key | IAM Role |
|------------|----------|
| Static credential (doesn't expire by default) | Temporary credentials (expire in hours) |
| If leaked, attacker has permanent access | If leaked, access expires soon |
| Requires secret rotation | Rotated automatically by AWS STS |
| Tied to a user | Tied to a workload (EC2, Lambda, EKS pod) |
| Can be accidentally committed to git | Never stored in code or environment |

For AOIS on EKS (v12), pods will use **IRSA** (IAM Roles for Service Accounts) — each pod gets temporary credentials scoped to exactly the Bedrock permissions it needs. No API keys anywhere.

For now, create an IAM policy and role that grants Bedrock access:

```bash
# Create the policy document
cat > /tmp/bedrock-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ListFoundationModels"
      ],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
      ]
    }
  ]
}
EOF

# Create the policy
aws iam create-policy \
  --policy-name AOISBedrockPolicy \
  --policy-document file:///tmp/bedrock-policy.json \
  --query 'Policy.Arn' \
  --output text
```
Expected: `arn:aws:iam::123456789012:policy/AOISBedrockPolicy`

Note the principle of least privilege: the policy only grants `InvokeModel` on the two specific Claude models AOIS uses — not `bedrock:*` on `*`. This is the pattern. In v12, this policy attaches to an IRSA role so AOIS pods on EKS get exactly these permissions and nothing else.

▶ **STOP — do this now**

Verify the policy exists and read its permissions:
```bash
aws iam get-policy --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/AOISBedrockPolicy
aws iam get-policy-version \
  --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/AOISBedrockPolicy \
  --version-id v1 \
  --query 'PolicyVersion.Document.Statement[0]' \
  --output json
```
Expected output shows `Allow` on the two specific model ARNs. If it shows `Resource: "*"`, the least-privilege constraint is missing — fix it before proceeding.

---

## Step 3: Route AOIS to Bedrock via LiteLLM

This is where the LiteLLM investment from v2 pays off. The application code in `main.py` does not change. LiteLLM's config changes.

The LiteLLM Bedrock provider uses your AWS credentials (from `~/.aws/credentials` or environment variables) and translates the OpenAI-compatible API calls to Bedrock's API format automatically.

Update the LiteLLM configuration. First, look at the current config:
```bash
cat litellm_config.yaml 2>/dev/null || grep -n "litellm\|model_list" main.py | head -20
```

Add the Bedrock model to the routing tiers. In `main.py` or your LiteLLM config, the Bedrock model ID follows this format:

```python
# LiteLLM Bedrock model IDs — prefix with "bedrock/"
BEDROCK_SONNET = "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
BEDROCK_HAIKU  = "bedrock/anthropic.claude-3-haiku-20240307-v1:0"
```

The LiteLLM call is identical to calling any other model:
```python
import litellm
import os

response = litellm.completion(
    model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
    messages=[{"role": "user", "content": "Analyze this log: OOMKilled in production"}],
    aws_region_name="us-east-1",
    # No API key needed — uses AWS credential chain automatically
)
print(response.choices[0].message.content)
```

LiteLLM resolves AWS credentials in this order:
1. `aws_access_key_id` / `aws_secret_access_key` passed directly (avoid — static secrets)
2. Environment variables `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
3. `~/.aws/credentials` file
4. IAM instance profile / IRSA (production pattern — zero secrets)

On your local machine, option 3 is active. On EKS in v12, option 4 takes over automatically.

▶ **STOP — do this now**

Write a test that calls AOIS through Bedrock and times the response:

```python
# test_bedrock.py
import litellm
import time

log_sample = "pod/auth-service-7d9f CrashLoopBackOff — OOMKilled, 5 restarts in 10 minutes"

models = {
    "anthropic_direct": "claude-3-haiku-20240307",
    "bedrock_haiku":    "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
    "bedrock_sonnet":   "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
}

for label, model in models.items():
    start = time.time()
    try:
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": f"Analyze this k8s log in one sentence: {log_sample}"}],
            max_tokens=100,
            aws_region_name="us-east-1",
        )
        elapsed = time.time() - start
        print(f"{label:25} | {elapsed:.2f}s | {resp.usage.total_tokens} tokens | {resp.choices[0].message.content[:80]}")
    except Exception as e:
        print(f"{label:25} | ERROR: {e}")
```

Run it:
```bash
python test_bedrock.py
```
Expected output (your numbers will differ):
```
anthropic_direct          | 1.23s | 87 tokens | The auth service pod is crash-looping due to OOM...
bedrock_haiku             | 1.41s | 87 tokens | The auth service pod is crash-looping due to OOM...
bedrock_sonnet            | 2.18s | 94 tokens | The auth service pod is experiencing repeated cra...
```

Key observations:
- Bedrock adds ~150–300ms of latency vs direct — this is the AWS API Gateway overhead
- Token counts are identical — same model, same tokenizer
- For most SRE use cases, 150ms is irrelevant against a 1–2 second base latency
- The compliance, audit trail, and IAM authentication is worth every millisecond

---

## Step 4: Add Bedrock as a Routing Tier in AOIS

Now wire Bedrock into AOIS's actual routing logic. Open `main.py` and update the tier mapping:
