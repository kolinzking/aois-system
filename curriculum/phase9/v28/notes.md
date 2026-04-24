# v28 — GitHub Actions + Dagger: Full CI/CD Pipeline

⏱ **Estimated time: 6–8 hours**

---

## Prerequisites

v27 complete. GitHub repo exists. GHCR push works from v6.

```bash
# Docker login to GHCR works
docker pull ghcr.io/kolinzking/aois:v6 && echo "GHCR access ok"

# GitHub CLI authenticated
gh auth status
# ✓ Logged in to github.com

# ArgoCD running on cluster
kubectl get pods -n argocd | grep argocd-server
# argocd-server-xxx   Running
```

---

## Learning Goals

By the end you will be able to:

- Build a full GitHub Actions pipeline: lint → test → Trivy scan → Cosign sign → push → deploy
- Explain what Dagger is and why "same pipeline locally and in CI" matters for reproducibility
- Implement safe model rollouts with OpenFeature: ship Claude update to 5% of traffic, measure, promote
- Set up Cosign image signing so every production image has a verifiable signature
- Configure branch protection so no unreviewed code reaches production

---

## The Pipeline

Every PR triggers:
```
lint (ruff) → test (pytest) → trivy scan → build image
```

Every merge to main triggers:
```
build → trivy → cosign sign → push GHCR → ArgoCD sync (Hetzner) → ArgoCD sync (EKS, if enabled)
```

---

## GitHub Actions: PR Gate

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt ruff pytest

      - name: Lint (ruff)
        run: ruff check .

      - name: Test
        run: pytest tests/ -x -q
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Agent evals
        run: python3 evals/run_evals.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

  build-push:
    needs: lint-test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: read
      packages: write
      id-token: write  # for Cosign keyless signing

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push image
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Trivy vulnerability scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          format: table
          exit-code: 1
          severity: HIGH,CRITICAL

      - name: Install Cosign
        uses: sigstore/cosign-installer@v3

      - name: Sign image (keyless)
        run: |
          cosign sign --yes \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}

      - name: Update Helm values with new image SHA
        run: |
          sed -i "s|tag:.*|tag: ${{ github.sha }}|" charts/aois/values.prod.yaml
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add charts/aois/values.prod.yaml
          git commit -m "ci: bump image to ${{ github.sha }}" || echo "No changes"
          git push

  dashboard-build:
    needs: lint-test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: dashboard/package-lock.json
      - run: cd dashboard && npm ci && npm run build
```

---

## ▶ STOP — do this now

Push the workflow file and watch the first run:

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions pipeline"
git push

# Watch the run
gh run watch
```

Expected: all jobs pass on the first push to main. If Trivy finds HIGH/CRITICAL CVEs, fix them before the job passes — this is the point.

---

## Dagger: Pipeline as Code

Dagger wraps your CI pipeline in Python so the exact same code runs locally and in CI. No more "works in CI but not locally" or "I need to push to test this."

```python
# dagger_pipeline.py
"""AOIS CI pipeline — runs identically locally and in GitHub Actions."""
import anyio
import dagger


async def pipeline():
    async with dagger.Connection() as client:
        src = client.host().directory(".", exclude=["dashboard/node_modules", "__pycache__"])

        # Python container with dependencies
        python = (
            client.container()
            .from_("python:3.11-slim")
            .with_directory("/app", src)
            .with_workdir("/app")
            .with_exec(["pip", "install", "-q", "-r", "requirements.txt", "ruff", "pytest"])
        )

        # Lint
        lint = python.with_exec(["ruff", "check", "."])
        print("Lint:", await lint.stdout())

        # Test
        test = python.with_exec(["pytest", "tests/", "-x", "-q"])
        print("Tests:", await test.stdout())

        # Build Docker image
        image = client.container().build(src)
        addr = await image.publish(f"ghcr.io/kolinzking/aois:dagger-{await src.id()[:8]}")
        print("Published:", addr)


anyio.run(pipeline)
```

Run locally:
```bash
pip install dagger-io
python3 dagger_pipeline.py
```

The same Python code runs in GitHub Actions via `dagger run python3 dagger_pipeline.py`. No YAML divergence.

---

## OpenFeature: Safe Model Rollouts

OpenFeature is a feature flag SDK. For AOIS, it enables A/B testing new Claude models: ship claude-opus-4-7 to 5% of traffic, measure severity_accuracy vs claude-haiku-4-5-20251001, then promote.

```python
# openfeature_rollout.py
"""Model selection via OpenFeature — safe A/B rollout of LLM versions."""
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

api.set_provider(FlagdProvider())
client = api.get_client("aois")


def get_model_for_request(session_id: str, severity: str) -> str:
    """
    Use OpenFeature to determine which model to use.
    Allows safe rollout: 5% of P1 traffic to new model.
    """
    # Flag: "use-opus-4-7" with percentage rollout
    use_new_model = client.get_boolean_value(
        "use-opus-4-7",
        default_value=False,
        evaluation_context={"session_id": session_id, "severity": severity},
    )
    if use_new_model and severity in ("P1", "P2"):
        return "claude-opus-4-7"
    return "claude-haiku-4-5-20251001"
```

Flag config (flagd format):

```yaml
# flags/aois-flags.yaml
flags:
  use-opus-4-7:
    state: ENABLED
    variants:
      'on': true
      'off': false
    defaultVariant: 'off'
    targeting:
      fractionalEvaluation:
        - '$flagd/flagKey'
        - ['on', 5]   # 5% of traffic gets new model
        - ['off', 95]
```

---

## ▶ STOP — do this now

Verify image signing is working after the first pipeline run:

```bash
# Verify the cosign signature on the latest image
cosign verify \
  --certificate-identity-regexp="https://github.com/kolinzking/aois" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/kolinzking/aois:latest | jq .
```

Expected: JSON with `"verified": true` and the workflow ref. Any image without a valid signature is rejected by the admission webhook in v30.

---

## Branch Protection

Set branch protection on `main` via GitHub CLI:

```bash
gh api repos/kolinzking/aois/branches/main/protection \
  --method PUT \
  -F required_status_checks='{"strict":true,"contexts":["lint-test","build-push"]}' \
  -F enforce_admins=true \
  -F required_pull_request_reviews='{"required_approving_review_count":1}' \
  -F restrictions=null
```

After this: no direct push to main. Every change requires a PR, passes CI, and gets one review.

---

## Common Mistakes

### 1. Trivy scan runs before push — scans the local build not the pushed image

```yaml
# Wrong — scans build cache, not the pushed image
- name: Build and push
  id: build
  uses: docker/build-push-action@v5
  with:
    push: true
    tags: myimage:latest

- name: Trivy scan
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: myimage:latest  # may pull from cache, not registry

# Correct — use the digest from the build step
- name: Trivy scan
  with:
    image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
```

### 2. `git push` in CI fails — actions bot lacks write permission

Add to the job:
```yaml
permissions:
  contents: write
  packages: write
```

---

## Troubleshooting

### `cosign: command not found`

The `sigstore/cosign-installer@v3` action installs Cosign in the PATH for subsequent steps. It must come before the `cosign sign` step.

### ArgoCD not picking up new image SHA

ArgoCD polls the git repo every 3 minutes by default. To force immediate sync:
```bash
argocd app sync aois --force
```
Or configure webhook: Settings → Webhooks → add the ArgoCD webhook URL.

---

## Connection to Later Phases

### To v29 (W&B): the pipeline uploads eval results to W&B as experiment metrics after each run.
### To v34.5 (Capstone): the pipeline is the enforcement layer for agent SLOs — no agent change ships without passing evals + Trivy + Cosign.

---

## Mastery Checkpoint

1. Push a commit that introduces a ruff lint error. Confirm the CI job fails on the lint step and the build does not proceed.
2. Push a commit that fixes the error. Confirm the full pipeline passes and ArgoCD syncs.
3. Run `cosign verify` on the newly pushed image. Show the verified output.
4. Enable the OpenFeature flag for 10% of traffic. Run 20 test requests. Confirm approximately 2 use `claude-opus-4-7` and 18 use `claude-haiku-4-5-20251001`.
5. Explain to a senior engineer why Dagger matters over plain GitHub Actions YAML. What specific failure mode does it prevent?
6. Run `python3 dagger_pipeline.py` locally. Confirm it builds and publishes an image identical to what the GitHub Actions job produces.

**The mastery bar:** every push to main automatically builds, scans, signs, and deploys AOIS. No manual deploy steps. No unsigned images in production.

---

## 4-Layer Tool Understanding

### GitHub Actions

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Without CI, deploying AOIS means remembering to run tests, build the image, scan it, and push it — in the right order, every time. GitHub Actions does all of this automatically on every push. |
| **System Role** | Where does it sit in AOIS? | Between git push and production. Every merge to main triggers: lint → test → evals → build → scan → sign → push → ArgoCD sync. Manual deploy steps are eliminated. |
| **Technical** | What is it precisely? | A YAML-defined workflow runner hosted by GitHub. Jobs run in ephemeral Ubuntu VMs. Steps call Actions (pre-built Docker containers or JavaScript) or run shell commands. Secrets are injected as environment variables. Outputs from one step can be consumed by subsequent steps. |
| **Remove it** | What breaks, and how fast? | Remove CI → deployments are manual. Trivy scans get skipped. Agent evals do not run on every change. The first time an unscanned image ships with a critical CVE, or an agent prompt change silently breaks severity classification, the cost of the missing gate becomes obvious. |

### Cosign / Sigstore

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | If someone compromises GHCR and replaces your image with a malicious one, your cluster would pull and run it. Cosign signs every image with a verifiable signature. The cluster rejects any image without a valid signature. |
| **System Role** | Where does it sit in AOIS? | At the end of the build pipeline (sign before push) and at the cluster admission layer (verify before pull). The signature is stored in the OCI registry alongside the image — no separate database needed. |
| **Technical** | What is it precisely? | A tool from the Sigstore project. Keyless signing uses GitHub OIDC token (no long-lived key to manage) — the signature is bound to the GitHub Actions workflow that produced it. `cosign sign` writes the signature to the registry. `cosign verify` checks it, including the workflow identity. |
| **Remove it** | What breaks, and how fast? | Remove Cosign → any image that passes Trivy can be deployed, including a replaced image from a compromised registry. Supply chain attack surface is open. In regulated environments, unsigned container images fail compliance checks immediately. |

### Dagger

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Your GitHub Actions pipeline passes but the same steps fail locally. "Works in CI" is not the same as "works anywhere." Dagger runs the pipeline inside containers — the exact same containers in CI and locally. If the Dagger pipeline passes locally, it will pass in CI. |
| **System Role** | Where does it sit in AOIS? | A wrapper around the GitHub Actions pipeline steps. The same `dagger_pipeline.py` runs on a developer's laptop and in the GitHub Actions runner. The Docker engine is the only required dependency. |
| **Technical** | What is it precisely? | A programmable CI/CD engine that runs pipelines as containerized DAGs (directed acyclic graphs). Written in Python (or TypeScript/Go). Each step runs in an ephemeral container with a defined input directory. Caching is automatic — unchanged steps are skipped. The Dagger Cloud service provides remote caching and run history. |
| **Remove it** | What breaks, and how fast? | Remove Dagger → CI-local divergence returns. A step that works in CI uses a different Python version than local. A step that passes locally uses a package installed globally that is not in requirements.txt. These divergences are discovered during deploys, not during development. |

### OpenFeature (Model Rollouts)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What does this solve? | Shipping a new Claude model to 100% of production traffic immediately is risky — you cannot tell if accuracy drops until users are affected. OpenFeature lets you send 5% of traffic to the new model first. If accuracy holds, increase to 100%. If it drops, flip back. |
| **System Role** | Where does it sit in AOIS? | In the model selection layer (between the incident classifier and the LLM call). `get_model_for_request()` checks the OpenFeature flag for each request. Flag config lives in `flags/aois-flags.yaml`. The flag evaluation is deterministic: the same session_id always gets the same model during a rollout. |
| **Technical** | What is it precisely? | An open standard for feature flag evaluation with provider-agnostic SDKs. AOIS uses the flagd provider (a sidecar that reads YAML flag configs). The flag spec defines variants (model names), default variant, and targeting rules (fractional rollout by session_id hash). |
| **Remove it** | What breaks, and how fast? | Remove OpenFeature → model updates are all-or-nothing. A new Claude model ships to 100% of traffic immediately. If it has worse P1 classification accuracy, every operator is affected simultaneously. The rollback requires a new deploy (5-10 minutes of degraded classification). With OpenFeature, rollback is a flag flip: 30 seconds. |
