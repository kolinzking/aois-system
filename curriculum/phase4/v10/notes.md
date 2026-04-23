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
- AWS account (free to create at aws.amazon.com — requires a credit card for identity verification)
- AWS CLI installed and configured (covered in Step 0 below)

### Step 0 — AWS Account Setup (do this once, skip if already done)

**0a — Create an AWS account (if you don't have one)**
Go to aws.amazon.com → Create a Free Account. You need a credit card for verification. The account itself is free — you only pay for services you use. For v10, the total spend is under $0.10 (Bedrock charges per token; our test calls cost pennies).

**Important:** AWS Skill Builder (the learning subscription at skillbuilder.aws) is NOT the same as an AWS infrastructure account. Skill Builder is a course platform — cancel it if you have it. The AWS infrastructure account is what you need here.

**0b — Create an IAM user (never use root for CLI access)**
Your AWS root account is the master account — using it directly for CLI work is a security risk. Create a dedicated IAM user instead:

1. Log into console.aws.amazon.com
2. Search **IAM** in the top bar → click **IAM**
3. Left sidebar → **Users** → **Create user**
4. Username: `aois-dev`
5. Leave "Provide user access to the AWS Management Console" **unchecked** (CLI only)
6. Click **Next**
7. Select **"Attach policies directly"**
8. Search for `AdministratorAccess` → check it
9. Click **Next** → **Create user**

**0c — Create access keys**
1. Click **aois-dev** in the users list
2. Click the **Security credentials** tab
3. Scroll to **Access keys** → **Create access key**
4. Select **Local code** → **Next** → **Create access key**
5. Copy the **Access key ID** and **Secret access key** — the secret is shown only once

**0d — Install and configure AWS CLI**
```bash
# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
~/.local/bin/aws --version 2>/dev/null || /tmp/aws/install --bin-dir ~/.local/bin --install-dir ~/.local/aws-cli
export PATH=$HOME/.local/bin:$PATH
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
```

Configure with your keys:
```bash
aws configure
```
Enter:
- `AWS Access Key ID` — the key ID from step 0c
- `AWS Secret Access Key` — the secret from step 0c
- `Default region name` — `us-east-1`
- `Default output format` — `json`

**Where do the keys go?** `aws configure` writes to `~/.aws/credentials` — a file in your home directory, outside the repo. Git never tracks it. Never paste keys directly into a terminal command (e.g. `AWS_SECRET=sk-... aws ...`) — that lands in shell history. `aws configure` is the safe way: it prompts interactively and writes to the credentials file only.

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

## Step 1: Verify Bedrock Model Access

As of 2025, AWS retired the manual model access page. Serverless foundation models are now **automatically enabled on first invocation** — no console action needed. The Model access page now reads: "Model access page has been retired."

Account administrators still control access via IAM policies and Service Control Policies — which is what the `AOISBedrockPolicy` you create in Step 2 does. The console gate is gone; the IAM gate remains.

**Important — confirm your region is US East (N. Virginia).** Bedrock model availability varies by region. `us-east-1` has the widest selection. Check the top-right corner of the console before making any API calls — if it shows anything other than US East (N. Virginia), click it and switch.

**Anthropic use case form (first-time accounts only):** Even though the Model access page is retired, Anthropic models require a one-time use case submission for new accounts. If your first API call returns:
```
ResourceNotFoundException: Model use case details have not been submitted for this account.
Fill out the Anthropic use case details form before using the model.
```
Fix:
1. Go to Bedrock console → left sidebar → **Playground**
2. Select any Claude model — the console will prompt you to fill out the use case form
3. Describe your use case (e.g. "Building an SRE log analysis system for learning AI engineering")
4. Submit — wait up to 15 minutes, then retry

This is a one-time step per AWS account.

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

The tier logic in `main.py` currently maps severity to a model. Add Bedrock as the enterprise tier:

```python
# main.py — updated tier routing
TIER_MODELS = {
    "enterprise": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",  # NEW — AWS Bedrock
    "premium":    "claude-3-5-sonnet-20241022",                          # Anthropic direct
    "standard":   "gpt-4o-mini",                                         # OpenAI
    "fast":       "groq/llama3-8b-8192",                                 # Groq
    "local":      "ollama/llama3",                                       # Local
}

# Route P1 incidents to Bedrock when AWS_BEDROCK_ENABLED=true
def select_model(severity: str, tier_override: str = None) -> str:
    if tier_override:
        return TIER_MODELS.get(tier_override, TIER_MODELS["standard"])
    if severity == "P1" and os.getenv("AWS_BEDROCK_ENABLED", "false") == "true":
        return TIER_MODELS["enterprise"]
    if severity in ("P1", "P2"):
        return TIER_MODELS["premium"]
    if severity == "P3":
        return TIER_MODELS["standard"]
    return TIER_MODELS["fast"]
```

The `AWS_BEDROCK_ENABLED` flag lets you switch between Anthropic direct and Bedrock without code changes — useful for comparing in production or for environments where Bedrock isn't available (local dev, Hetzner).

Update `main.py` now with the enterprise tier and the updated `select_model` function.

---

## Step 5: Bedrock Agents — Managed Agent Infrastructure

So far you have been calling Bedrock as a raw model — send a prompt, get a response. Bedrock Agents is a layer above this.

**Raw Bedrock model call:**
```
You → Bedrock API → Claude → text response → You parse it
```

**Bedrock Agent:**
```
You → Bedrock Agent → Claude + tool routing + knowledge base → structured action → You
```

A Bedrock Agent has:
- **Instructions** — the agent's role and behavior (like a system prompt, but managed by AWS)
- **Action groups** — tools the agent can call (your Lambda functions, OpenAPI specs)
- **Knowledge bases** — documents the agent can retrieve from (S3 + vector store)
- **Session memory** — optional cross-turn context (multi-step investigations)

This is what enterprises mean when they say "we deployed an AI agent on AWS." They built a Bedrock Agent — AWS handles the orchestration loop (decide → tool call → observe → decide again), they just define the tools and the data.

### Create a Bedrock Agent for AOIS

The agent will take a log input and call AOIS's analysis logic as a tool via Lambda.

**Step 5a — Create a Lambda function that wraps AOIS analysis**

The Lambda is the bridge: Bedrock Agent calls it, it runs the AOIS analysis logic, returns structured output.

```bash
# Create the Lambda execution role
cat > /tmp/lambda-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name AOISLambdaRole \
  --assume-role-policy-document file:///tmp/lambda-trust-policy.json \
  --query 'Role.Arn' --output text

# Attach basic Lambda execution + Bedrock invoke permissions
aws iam attach-role-policy \
  --role-name AOISLambdaRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam attach-role-policy \
  --role-name AOISLambdaRole \
  --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/AOISBedrockPolicy
```

Create the Lambda handler:
```python
# lambda/aois_handler.py
import json
import litellm
import os

def handler(event, context):
    """
    Called by Bedrock Agent when it needs to analyze a log.
    Input: {"log": "...", "context": "..."}
    Output: {"severity": "P1", "summary": "...", "suggested_action": "..."}
    """
    body = json.loads(event.get("requestBody", {}).get("content", {}).get("application/json", {}).get("body", "{}"))
    log_text = body.get("log", "")

    response = litellm.completion(
        model="bedrock/anthropic.claude-3-haiku-20240307-v1:0",
        messages=[
            {"role": "system", "content": "You are an SRE. Analyze the log and return JSON with keys: severity (P1/P2/P3/P4), summary, suggested_action, confidence (0.0-1.0)."},
            {"role": "user", "content": f"Log: {log_text}"}
        ],
        aws_region_name="us-east-1",
        max_tokens=300,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "severity": "P2",
            "summary": response.choices[0].message.content,
            "suggested_action": "Review logs and metrics",
            "confidence": 0.85
        })
    }
```

Package and deploy:
```bash
cd lambda
pip install litellm -t . -q
zip -r aois-lambda.zip . -q
aws lambda create-function \
  --function-name aois-analyzer \
  --runtime python3.12 \
  --role arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/AOISLambdaRole \
  --handler aois_handler.handler \
  --zip-file fileb://aois-lambda.zip \
  --timeout 30 \
  --region us-east-1
```

**Step 5b — Create the Bedrock Agent**

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create the agent role (Bedrock needs permission to invoke Lambda and models)
cat > /tmp/agent-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "bedrock.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name AOISBedrockAgentRole \
  --assume-role-policy-document file:///tmp/agent-trust-policy.json

aws iam attach-role-policy \
  --role-name AOISBedrockAgentRole \
  --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/AOISBedrockPolicy

# Create the agent
AGENT_ID=$(aws bedrock-agent create-agent \
  --agent-name "aois-sre-agent" \
  --agent-resource-role-arn arn:aws:iam::${ACCOUNT_ID}:role/AOISBedrockAgentRole \
  --foundation-model "anthropic.claude-3-haiku-20240307-v1:0" \
  --instruction "You are an SRE agent. When given Kubernetes logs or events, call the analyze_log tool to get a structured severity assessment. Then explain the finding and recommend next steps based on the severity." \
  --region us-east-1 \
  --query 'agent.agentId' \
  --output text)

echo "Agent ID: $AGENT_ID"
```

▶ **STOP — do this now**

Verify the agent was created:
```bash
aws bedrock-agent get-agent --agent-id $AGENT_ID --region us-east-1 \
  --query 'agent.{name:agentName,status:agentStatus,model:foundationModel}' \
  --output json
```
Expected:
```json
{
    "name": "aois-sre-agent",
    "status": "NOT_PREPARED",
    "model": "anthropic.claude-3-haiku-20240307-v1:0"
}
```
`NOT_PREPARED` is correct — the agent needs action groups attached and then a prepare step before it can be invoked.

**Step 5c — Attach the AOIS Lambda as an action group**

```bash
LAMBDA_ARN=$(aws lambda get-function \
  --function-name aois-analyzer \
  --region us-east-1 \
  --query 'Configuration.FunctionArn' \
  --output text)

# Allow Bedrock to invoke the Lambda
aws lambda add-permission \
  --function-name aois-analyzer \
  --statement-id bedrock-agent-invoke \
  --action lambda:InvokeFunction \
  --principal bedrock.amazonaws.com \
  --region us-east-1

# Create the action group schema (tells the agent what inputs the tool expects)
cat > /tmp/action-schema.json << 'EOF'
{
  "openapi": "3.0.0",
  "info": {"title": "AOIS Analyzer", "version": "1.0"},
  "paths": {
    "/analyze": {
      "post": {
        "operationId": "analyze_log",
        "description": "Analyze a Kubernetes log entry and return severity, summary, and suggested action",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "log": {"type": "string", "description": "The raw log text or Kubernetes event to analyze"}
                },
                "required": ["log"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Analysis result",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "severity": {"type": "string"},
                    "summary": {"type": "string"},
                    "suggested_action": {"type": "string"},
                    "confidence": {"type": "number"}
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
EOF

aws bedrock-agent create-agent-action-group \
  --agent-id $AGENT_ID \
  --agent-version DRAFT \
  --action-group-name "aois-analysis" \
  --action-group-executor '{"lambda": "'$LAMBDA_ARN'"}' \
  --api-schema '{"payload": "'$(cat /tmp/action-schema.json | base64 -w 0)'"}' \
  --region us-east-1
```

Prepare and invoke the agent:
```bash
# Prepare makes the agent ready for invocation
aws bedrock-agent prepare-agent --agent-id $AGENT_ID --region us-east-1

# Wait for preparation (usually 10-20 seconds)
sleep 20

# Create an alias (required for invocation)
ALIAS_ID=$(aws bedrock-agent create-agent-alias \
  --agent-id $AGENT_ID \
  --agent-alias-name "prod" \
  --region us-east-1 \
  --query 'agentAlias.agentAliasId' \
  --output text)

# Invoke the agent
aws bedrock-agent-runtime invoke-agent \
  --agent-id $AGENT_ID \
  --agent-alias-id $ALIAS_ID \
  --session-id "test-session-001" \
  --input-text "Analyze this: pod/payment-service-7d9f CrashLoopBackOff — 8 restarts, last exit code 137 (OOMKilled)" \
  --region us-east-1 \
  /tmp/agent-response.json && cat /tmp/agent-response.json
```

Expected — the agent calls `analyze_log` via Lambda, gets the result, and returns a natural-language response:
```
The payment service pod is experiencing critical memory issues (P1 severity). 
Exit code 137 indicates the process was killed by the OS due to exceeding its 
memory limit (OOMKilled). The pod has restarted 8 times, suggesting the memory 
issue is persistent rather than transient.

Suggested action: Immediately increase the memory limit for the payment-service 
container, check for memory leaks in the application code, and review the 
pod's memory requests/limits in the deployment spec.
```

---

## Step 6: Anthropic Direct vs Bedrock — Decision Framework

Both call the same Claude model. The choice is about context, not capability.

| Scenario | Use | Why |
|----------|-----|-----|
| Personal project, Hetzner, no compliance requirements | Anthropic direct | Simpler, cheaper (no AWS markup), faster setup |
| Enterprise, regulated industry (finance/health/gov) | Bedrock | Compliance, audit trail, IAM, data residency |
| Already on AWS, using EKS, Secrets Manager, CloudTrail | Bedrock | IAM auth is free, everything is already integrated |
| Multi-cloud, want portability | LiteLLM + both | Switch backends via config, measure, choose per-region |
| Lowest latency is critical (e.g., real-time user-facing) | Anthropic direct | Bedrock adds ~150–300ms overhead |
| Cost-sensitive, high volume | Bedrock on-demand or provisioned throughput | Bedrock offers Provisioned Throughput for predictable pricing at scale |

**The AOIS production stance:** Use Bedrock for enterprise/regulated contexts (v12 EKS deployment), Anthropic direct for Hetzner (lower latency, no AWS overhead). LiteLLM makes this a config switch, not a code change.

▶ **STOP — do this now**

Run the latency comparison from Step 3 again, this time with 5 iterations each to get stable numbers:
```python
# test_bedrock_comparison.py
import litellm, time, statistics

log = "pod/api-gateway OOMKilled, CrashLoopBackOff, 3 restarts"

def benchmark(model, n=5):
    times = []
    for _ in range(n):
        start = time.time()
        litellm.completion(
            model=model,
            messages=[{"role": "user", "content": f"One sentence analysis: {log}"}],
            max_tokens=50,
            aws_region_name="us-east-1",
        )
        times.append(time.time() - start)
    return statistics.mean(times), statistics.stdev(times)

for label, model in [
    ("anthropic_direct", "claude-3-haiku-20240307"),
    ("bedrock_haiku",    "bedrock/anthropic.claude-3-haiku-20240307-v1:0"),
]:
    mean, std = benchmark(model)
    print(f"{label:20} | mean: {mean:.3f}s | stddev: {std:.3f}s")
```

Record your numbers. The delta between direct and Bedrock is the measurable cost of the compliance layer. In most production systems this is acceptable. In a real-time user-facing system with a 200ms SLA, it might not be.

---

## Common Mistakes

**Model not enabled — `AccessDeniedException` on invoke** *(recognition)*
Calling a Bedrock model before requesting access in the console produces:
```
botocore.exceptions.ClientError: An error occurred (AccessDeniedException) when 
calling the InvokeModel operation: Your account is not authorized to invoke this 
API operation.
```
*(recall — trigger it)*
```bash
# Try invoking a model you haven't enabled yet
aws bedrock-runtime invoke-model \
  --model-id anthropic.claude-3-opus-20240229-v1:0 \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":10,"messages":[{"role":"user","content":"test"}]}' \
  --cli-binary-format raw-in-base64-out /tmp/out.json 2>&1
```
Expected error: `AccessDeniedException`. Fix: go to Bedrock console → Model access → enable the specific model. The fix takes 1–5 minutes to propagate.

---

**Wrong model ID format for LiteLLM** *(recognition)*
LiteLLM requires the `bedrock/` prefix AND the exact AWS model ID (not the friendly name).
```python
# Wrong — this is the Anthropic API model ID
litellm.completion(model="claude-3-haiku-20240307", ...)  # calls Anthropic direct, not Bedrock

# Wrong — missing the version suffix
litellm.completion(model="bedrock/anthropic.claude-3-haiku", ...)  # ResourceNotFoundException

# Correct
litellm.completion(model="bedrock/anthropic.claude-3-haiku-20240307-v1:0", ...)
```
*(recall — trigger it)*
```bash
python -c "
import litellm
litellm.completion(
    model='bedrock/anthropic.claude-3-haiku',  # wrong ID
    messages=[{'role':'user','content':'test'}],
    aws_region_name='us-east-1',
    max_tokens=10
)
" 2>&1 | grep -E "Error|Exception|error"
```
Expected: `ResourceNotFoundException` or `ValidationException`. Fix: use the exact model ID from `aws bedrock list-foundation-models`.

---

**IAM permissions on wrong resource scope** *(recognition)*
A common mistake is to create a Bedrock policy with `Resource: "*"` thinking it's more permissive, then being confused when you can't call a specific model. In fact, Bedrock model ARNs must match exactly:
```
# Wrong ARN format (region in wrong place)
arn:aws:bedrock::us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0

# Correct
arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0
```
*(recall — trigger it)*
```bash
# Check the policy you created
aws iam get-policy-version \
  --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/AOISBedrockPolicy \
  --version-id v1 \
  --query 'PolicyVersion.Document.Statement[0].Resource'
```
Verify the ARN format matches `arn:aws:bedrock:REGION::foundation-model/MODEL_ID`. If the region is missing or in the wrong position, update the policy.

---

**Bedrock Agent stuck in `NOT_PREPARED` after adding action group** *(recognition)*
After creating or modifying an action group, the agent must be re-prepared before invocation. Calling `invoke-agent` on an unprepared agent silently falls back to the base model (no tool use).
*(recall — trigger it)*
```bash
# Invoke without preparing first
aws bedrock-agent-runtime invoke-agent \
  --agent-id $AGENT_ID \
  --agent-alias-id $ALIAS_ID \
  --session-id "test-noprepare" \
  --input-text "Analyze: OOMKilled pod" \
  --region us-east-1 /tmp/out.json 2>&1
```
The response will come back but the agent won't call the Lambda tool — it answers from the model directly. Fix: always run `prepare-agent` after any change to the agent's configuration.

---

**Lambda not returning the expected schema — agent gives generic response** *(recognition)*
Bedrock Agent parses the Lambda response body and maps it to the OpenAPI schema. If the Lambda returns a response shape that doesn't match the schema (e.g., nesting the result under an extra key), the agent cannot extract the tool output and gives a vague generic answer instead of using the tool result.
*(recall — trigger it)*
```bash
# Test the Lambda directly before the agent calls it
aws lambda invoke \
  --function-name aois-analyzer \
  --payload '{"requestBody":{"content":{"application/json":{"body":"{\"log\":\"OOMKilled test\"}"}}}}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/lambda-out.json && cat /tmp/lambda-out.json
```
The response body must match the OpenAPI schema exactly. If the keys are wrong or the JSON is double-encoded, the agent won't use it. Fix: compare the Lambda output shape against the `responses` section of your OpenAPI schema.

---

## Troubleshooting

**`NoCredentialsError` when calling Bedrock via LiteLLM:**
```
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```
LiteLLM uses boto3 under the hood, which follows the standard AWS credential chain. Check in order:
```bash
aws sts get-caller-identity          # confirms credentials are present
aws configure list                   # shows which credential source is active
echo $AWS_ACCESS_KEY_ID             # check if env vars are set
cat ~/.aws/credentials               # check file-based credentials
```
If running in a container, ensure the container can reach the EC2 metadata service for instance profile credentials: `curl http://169.254.169.254/latest/meta-data/iam/security-credentials/`

**`ThrottlingException` on Bedrock invoke:**
```
botocore.exceptions.ClientError: ThrottlingException: Too many requests
```
Bedrock on-demand has per-model rate limits (tokens per minute). For Claude 3 Haiku in us-east-1, the default limit is relatively generous but a burst of parallel requests can hit it. Options:
1. Add exponential backoff retry (LiteLLM has built-in retry: `litellm.completion(..., num_retries=3)`)
2. Request a quota increase in the AWS console (Service Quotas → Bedrock)
3. Use Bedrock Provisioned Throughput for predictable capacity at scale

**ArgoCD shows `OutOfSync` after updating `main.py`:**
```bash
kubectl get application aois -n argocd -o jsonpath='{.status.conditions}'
```
This is expected if you changed `main.py` — ArgoCD manages Helm chart changes, not application code. Application code changes require a new Docker image + updated image tag in `values.prod.yaml` + git push. The GitOps flow is: code change → build image → push to GHCR → update values.prod.yaml → git push → ArgoCD syncs.

**Bedrock Agent invoke returns empty response:**
```bash
# Check CloudWatch logs for the Lambda
aws logs tail /aws/lambda/aois-analyzer --follow --region us-east-1
```
The Lambda is the most common failure point. Check: does it have the right permissions? Is the response body valid JSON matching the schema? Is LiteLLM installed in the Lambda package?

---

## Connection to later phases

- **v11 (Lambda)**: The `aois-analyzer` Lambda you built here becomes the core of a fully serverless AOIS deployment. API Gateway fronts it. The Lambda code is already written — v11 is about wiring it up properly with API Gateway, environment variables, and cold start optimization.
- **v12 (EKS)**: IRSA (IAM Roles for Service Accounts) replaces the manual IAM role approach from Step 2. The AOIS pod on EKS gets temporary Bedrock credentials automatically from the pod's service account — zero static secrets. The `AOISBedrockPolicy` you created here attaches to the IRSA role in v12.
- **v20 (Claude Tool Use)**: The Bedrock Agent pattern (model + tools + orchestration) is conceptually identical to what you'll build with Claude tool use directly. The difference: Bedrock Agents is fully managed (AWS orchestrates the loop), while v20 gives you full control of the agent loop in code. Knowing both gives you the ability to choose the right abstraction.
- **v28 (CI/CD)**: The GitHub Actions pipeline will need AWS credentials to push images to ECR and update EKS. The IAM pattern you built here (least-privilege policy, role assumption) is the same pattern used for GitHub Actions OIDC — no static AWS keys in GitHub secrets.

---

## Mastery Checkpoint

**1. Prove Bedrock is running Claude, not a different model**
Make identical requests to `anthropic_direct` and `bedrock_haiku` with the same seed prompt. Compare the response content and token counts. They should be functionally identical (same model weights). Then call `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` with the same prompt. The quality difference between Haiku and Sonnet should be visible in the response depth — confirm you can see it.

**2. Explain the credential chain without notes**
Without looking at the notes: explain the four ways LiteLLM/boto3 finds AWS credentials, in priority order. Explain which method is used in local dev on your machine right now, and which method will be used when AOIS runs on EKS in v12. If you cannot answer this in two sentences each, re-read Step 2.

**3. Measure the Bedrock latency overhead**
Run the benchmark from Step 6 with 10 iterations. Calculate the p50 and p95 latency for both direct and Bedrock. Is the overhead consistent (low stddev) or variable (high stddev)? A consistent 200ms overhead is engineerable. A variable 50–800ms overhead requires a different approach (fallback, retry, circuit breaker). Know which you have.

**4. Break and fix the Bedrock Agent**
Modify the Lambda to return the response under a different key (`result` instead of `summary`). Re-deploy the Lambda. Invoke the agent. Observe that it no longer uses the tool result correctly — it falls back to generic model output. Fix the schema or the Lambda response to re-align them. This is the most common failure mode when integrating Bedrock Agents with existing services.

**5. Least-privilege audit**
Run this against your `AOISBedrockPolicy`:
```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/AOISBedrockPolicy \
  --action-names bedrock:InvokeModel bedrock:DeleteFoundationModel bedrock:CreateModelCustomizationJob \
  --resource-arns "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0" \
  --query 'EvaluationResults[].{action:EvalActionName,decision:EvalDecision}'
```
Expected: `InvokeModel` → `allowed`, `DeleteFoundationModel` and `CreateModelCustomizationJob` → `implicitDeny`. If anything other than `InvokeModel` and `InvokeModelWithResponseStream` shows `allowed`, your policy is too permissive — fix it.

**6. The compliance argument**
Without notes: explain to a skeptical colleague why a regulated company would use Bedrock over Anthropic direct even though Bedrock costs more and has higher latency. Cover: audit trail, data residency, IAM vs API keys, VPC PrivateLink, and CloudTrail integration. If you can make this argument convincingly, you understand enterprise AI deployment — not just the commands, but the why behind the architecture.

**The mastery bar:** You can call Claude via Bedrock using IAM credentials (not API keys), route AOIS through Bedrock via LiteLLM with a config change, invoke a Bedrock Agent that calls a Lambda tool, and explain the compliance rationale for Bedrock in a production enterprise context. You know exactly what changes in v12 (IRSA replaces manual IAM role) and v11 (Lambda becomes the primary deployment surface).

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels. Read this after completing the exercises — it turns what you did into something you can explain.*

---

### Amazon Bedrock

| Layer | |
|---|---|
| **Plain English** | AWS's managed service for running frontier AI models — Claude, Titan, Llama — without managing any GPU infrastructure or API keys from individual providers. |
| **System Role** | The enterprise deployment surface for AOIS in AWS. Replaces direct Anthropic API calls when compliance, data residency, and audit trail are requirements. LiteLLM routes to it via the `bedrock/` prefix. |
| **Technical** | A fully managed inference endpoint backed by AWS infrastructure. Authentication uses IAM roles (not static API keys). Every invocation is logged in CloudTrail. Data stays in your AWS region. Pricing is per-token, typically 10–20% higher than direct API. |
| **Remove it** | Without Bedrock, AOIS cannot be deployed in regulated enterprise environments (HIPAA, FedRAMP, SOC2-audited accounts). You lose CloudTrail audit logs, VPC PrivateLink routing, and data residency guarantees. Static API keys replace IAM roles — every enterprise security team will flag this. |

**Say it at three levels:**
- *Non-technical:* "Bedrock lets big companies use AI without worrying about where their data goes or who can see it. Everything stays inside their AWS account."
- *Junior engineer:* "Bedrock is Claude via AWS. Same models, same API shape — but authentication is IAM roles instead of API keys, every call is logged in CloudTrail, and data stays in your region. LiteLLM routes to it with a prefix change. Costs ~15% more but unlocks enterprise compliance."
- *Senior engineer:* "Bedrock's value is not inference — it is the compliance posture: CloudTrail audit trail, VPC PrivateLink for network isolation, AWS data processing addendum, and no static credentials to rotate. IRSA (v12) binds a k8s ServiceAccount to an IAM role via OIDC — the pod gets automatic credential rotation through the AWS SDK credential chain, no manual AssumeRole needed. The latency premium (~200ms vs. direct API) is the cost of that compliance layer."

---

### AWS IAM (Identity and Access Management)

| Layer | |
|---|---|
| **Plain English** | The system that controls who — people or services — can do what inside an AWS account. Every AWS API call passes through IAM. |
| **System Role** | AOIS on AWS authenticates to Bedrock using an IAM role, not an API key. The role carries exactly the permissions needed (`bedrock:InvokeModel` on specific model ARNs) and nothing else. This is the credential model for every AWS workload in AOIS. |
| **Technical** | IAM policies are JSON documents attached to users, roles, or groups. Roles are assumed by EC2 instances, Lambda functions, EKS pods (IRSA), or other AWS services — they issue temporary credentials with a short TTL. Policy evaluation: explicit Deny > explicit Allow > implicit Deny. |
| **Remove it** | Without IAM roles, you use static API keys. Static keys do not expire, can leak via git, and cannot be scoped to specific Bedrock model ARNs. Every security audit flags static credentials in a production AI system. IRSA in v12 eliminates even the manual AssumeRole step. |

**Say it at three levels:**
- *Non-technical:* "IAM is like a keycard system — every person and every program gets a card that only opens the doors it needs."
- *Junior engineer:* "IAM roles issue temporary credentials that expire in hours. My pod gets a role scoped to `bedrock:InvokeModel` on specific model ARNs only. If credentials are compromised, they expire quickly and are too narrow to do real damage."
- *Senior engineer:* "Least-privilege means resource ARNs (specific model IDs), not `*`. In v12, IRSA uses the EKS OIDC provider to bind a Kubernetes ServiceAccount to an IAM role — the pod environment gets `AWS_ROLE_ARN` and `AWS_WEB_IDENTITY_TOKEN_FILE`, and the AWS SDK credential chain handles AssumeRoleWithWebIdentity transparently. No secrets to rotate, no ambient EC2 instance profile risk."

---

### Amazon Bedrock Agents

| Layer | |
|---|---|
| **Plain English** | AWS's managed orchestration layer for AI agents — give it a prompt, a set of tools (Lambda functions), and optionally a knowledge base, and Bedrock runs the reasoning loop automatically. |
| **System Role** | An alternative agent runtime to LangGraph. Enterprises already invested in AWS use Bedrock Agents to build agentic workflows without managing orchestration infrastructure. In AOIS, it demonstrates the fully-managed-agent pattern versus the self-managed LangGraph pattern introduced in Phase 7. |
| **Technical** | Bedrock Agents use a ReAct-style planning loop internally. An action group maps agent intent to Lambda functions (described by an OpenAPI schema). A knowledge base is backed by an S3-managed vector store. The agent decides which tools to invoke, calls them via Lambda, and synthesizes results. Session context is managed by AWS. |
| **Remove it** | Without Bedrock Agents, you own the orchestration loop (LangGraph in v23). The trade-off: Bedrock Agents ships faster with less infrastructure overhead, but LangGraph gives full control over state transitions, retry logic, cost attribution per step, and evaluation tooling. Bedrock Agents is right when you are inside an enterprise AWS account and cannot maintain an orchestration framework. |

**Say it at three levels:**
- *Non-technical:* "Bedrock Agents is like a smart assistant who decides which phone calls to make and in what order to answer your question — you don't need to script every step."
- *Junior engineer:* "You define tools as Lambda functions with an OpenAPI spec. Bedrock decides when to call them. You do not write the for-loop — AWS runs the ReAct loop. Right for teams that are AWS-native and do not want to maintain an agent framework."
- *Senior engineer:* "Bedrock Agents abstracts the planning loop but also hides it — you cannot customize the system prompt, inject custom state between steps, or reproduce a failure trace without CloudTrail. It trades flexibility for operational simplicity. The right call for enterprise lift-and-shift; the wrong call for a system you need to evaluate and improve systematically (use LangGraph + Langfuse instead, which you build in v23)."
