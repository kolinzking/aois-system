# v28 — GitHub Actions + Dagger: Full CI/CD Pipeline

⏱ **Estimated time: 6–8 hours**

*Phase 9 — Production CI/CD and Platform Engineering. v27 added auth and authorization. v28 automates every step between git push and production.*

---

## What This Version Builds

Before v28, deploying AOIS to production is manual:

1. Run tests locally (maybe)
2. Build the Docker image
3. Trivy scan (if you remember)
4. Push to GHCR
5. Update the image tag in `values.prod.yaml`
6. Push to git
7. Wait for ArgoCD to sync (or force-sync)

This works until the first time someone skips step 3 and ships a CRITICAL CVE. Or ships a prompt change that breaks severity classification. Or forgets step 5 and wonders why the cluster is still running the old version.

v28 eliminates manual deploy steps entirely. Every merge to `main` automatically: lints, tests, runs agent evals, scans the image for vulnerabilities, signs it with Cosign, pushes to GHCR, bumps the image SHA in the Helm values, and ArgoCD syncs. No human deploys anything. The pipeline is the deployment.

By the end of v28:
- **GitHub Actions**: full CI/CD pipeline — two workflows, one for PR gates (lint + test + evals) and one for merge-to-main (build + Trivy + Cosign + push + ArgoCD)
- **Dagger**: the same pipeline steps wrapped in Python so they run identically locally and in CI — no "works in CI but not on my machine"
- **OpenFeature + flagd**: safe model rollouts — ship a new Claude model to 5% of traffic, measure accuracy, promote to 100% — without a redeploy

---

## Prerequisites

Verify all of these before starting.

```bash
# GitHub CLI authenticated and showing the correct account
gh auth status
```

Expected:
```
github.com
  ✓ Logged in to github.com account kolinzking (keyring)
  - Active account: true
  - Git operations protocol: https
  - Token: gho_****
  - Token scopes: 'gist', 'read:org', 'repo', 'workflow'
```

```bash
# GHCR push access from v6 still works
docker pull ghcr.io/kolinzking/aois:v6 && echo "GHCR access ok"
```

Expected:
```
v6: Pulling from kolinzking/aois
...
GHCR access ok
```

```bash
# ArgoCD running on the Hetzner cluster
kubectl get pods -n argocd | grep argocd-server
```

Expected:
```
argocd-server-xxxxxxxxxx-xxxxx   1/1   Running   0   Xd
```

```bash
# Cosign available
cosign version
```

Expected:
```
GitVersion:    v2.x.x
```

If Cosign is not installed: `brew install cosign` or download from https://github.com/sigstore/cosign/releases.

```bash
# Dagger installed
pip install dagger-io anyio && python3 -c "import dagger; print('dagger ok')"
```

Expected:
```
dagger ok
```

---

## Learning Goals

By the end of v28 you will be able to:

- Build a complete GitHub Actions pipeline with PR gate jobs (lint, test, evals) and merge-to-main deploy jobs (build, scan, sign, push, deploy)
- Explain why Dagger solves the "works in CI but not locally" problem and how containerized pipeline steps achieve this
- Configure Cosign keyless signing with GitHub OIDC — no long-lived keys, no key rotation, the signature is cryptographically bound to the GitHub Actions workflow
- Implement a model rollout with OpenFeature: 5% of traffic gets the new model, 95% gets the stable model, rollout is deterministic per `session_id`
- Set up branch protection so no code reaches `main` without passing CI and getting a review
- Explain the `contents: write` and `id-token: write` permission requirements and why they are separate

---

## Part 1: The Pipeline Design

Before writing any YAML, design the pipeline. Two questions drive the design:

**What gate does every PR need to pass?**

```
lint (ruff)
  │
  ├─► test (pytest)
  │
  └─► agent evals (run_evals.py — must meet SLO thresholds)
```

PRs that fail any of these steps cannot be merged. The PR author fixes locally, pushes again, CI re-runs.

**What happens automatically on every merge to `main`?**

```
build Docker image
  │
  ├─► Trivy scan (HIGH/CRITICAL → pipeline fails, image not pushed)
  │
  ├─► Cosign sign (keyless, bound to GitHub Actions OIDC)
  │
  ├─► push to GHCR (tagged with SHA + latest)
  │
  ├─► bump image SHA in charts/aois/values.prod.yaml
  │
  └─► git push → ArgoCD detects → syncs cluster → new image deployed
```

This is one-way deployment: git is the source of truth, ArgoCD watches it, the cluster reflects it. There is no manual `kubectl apply` or `helm upgrade` in production ever again.

---

## Part 2: GitHub Actions — PR Gate

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
    name: Lint, Test, Evals
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
        run: ruff check . --ignore E501

      - name: Run tests
        run: pytest tests/ -x -q
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}

      - name: Run agent evals (SLO gate)
        run: python3 evals/run_evals.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

**Why `evals` in the PR gate?** The eval suite (v23.5) enforces: severity accuracy ≥ 90%, safety rate = 100%, hallucination rate ≤ 5%. If a prompt change silently breaks accuracy, the eval suite catches it before the code merges. Without this gate, prompt regressions reach production silently — and you only notice when operators report wrong severity classifications.

**Why `actions/setup-python@v5` with `cache: pip`?** The cache key is the hash of `requirements.txt`. When dependencies have not changed, pip install is skipped — saving 60–90 seconds per run. When `requirements.txt` changes, the cache is invalidated and rebuilt.

---

## Part 3: GitHub Actions — Build and Deploy

```yaml
  build-push:
    name: Build, Scan, Sign, Push
    needs: lint-test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: write      # to push the image SHA bump commit
      packages: write      # to push to GHCR
      id-token: write      # for Cosign OIDC keyless signing

    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

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
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
          format: table
          exit-code: '1'
          severity: HIGH,CRITICAL
          ignore-unfixed: true

      - name: Install Cosign
        uses: sigstore/cosign-installer@v3

      - name: Sign image (keyless OIDC)
        run: |
          cosign sign --yes \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
        env:
          COSIGN_EXPERIMENTAL: "1"

      - name: Bump image SHA in Helm values
        run: |
          sed -i "s|tag:.*|tag: ${{ github.sha }}|" charts/aois/values.prod.yaml
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add charts/aois/values.prod.yaml
          git diff --staged --quiet || git commit -m "ci: bump image to ${{ github.sha }}"
          git push

  dashboard-build:
    name: Build React Dashboard
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
      - name: Build dashboard
        run: cd dashboard && npm ci && npm run build
```

### Key Design Decisions

**`needs: lint-test`**: the build job only starts if lint-test passes. No point building an image from code that fails tests.

**`if: github.ref == 'refs/heads/main'`**: build-push only runs on `main` branch pushes, not on PRs. PRs run lint-test only. This prevents building GHCR images for every branch — GHCR storage is not free.

**`${{ steps.build.outputs.digest }}`**: the build step outputs the image digest (a SHA256 hash of the image manifest). Using the digest for Trivy scan and Cosign sign guarantees you are scanning/signing the exact image that was pushed — not a re-pulled version that might differ due to a race condition.

**`git diff --staged --quiet || git commit`**: the SHA bump commit only happens if the file actually changed. Without this, pushing an identical SHA twice causes the commit to fail with "nothing to commit" and the step errors out, even though nothing is wrong.

**`cache-from: type=gha` / `cache-to: type=gha,mode=max`**: Docker layer caching via GitHub Actions cache. Unchanged layers (Python dependencies, OS packages) are pulled from cache instead of rebuilt. This reduces build time from ~3 minutes to ~45 seconds for typical code-only changes.

---

## ▶ STOP — do this now: Push the Workflow and Watch the First Run

First, add the required secrets to the GitHub repository:

```bash
# Add API keys as GitHub Actions secrets
gh secret set ANTHROPIC_API_KEY --body "$(grep ANTHROPIC_API_KEY .env | cut -d= -f2)"
gh secret set GROQ_API_KEY --body "$(grep GROQ_API_KEY .env | cut -d= -f2)"
```

Expected:
```
✓ Set Actions secret ANTHROPIC_API_KEY for kolinzking/aois
✓ Set Actions secret GROQ_API_KEY for kolinzking/aois
```

Push the workflow file:

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions pipeline"
git push
```

Watch the run:

```bash
gh run watch
```

Expected output (streaming, shows each step as it completes):
```
Refreshing run status every 3 seconds. Press Ctrl+C to quit.

✓ main CI · 123456789
Triggered via push about 30 seconds ago

JOBS
✓ Lint, Test, Evals (ubuntu-latest)
* Build, Scan, Sign, Push (ubuntu-latest)   ← in progress

ANNOTATIONS
No annotations
```

When the run completes:

```bash
gh run list --limit 3
```

Expected:
```
STATUS      TITLE                          WORKFLOW  BRANCH  EVENT  ID
✓ completed  ci: add GitHub Actions pipeline  CI       main    push   123456789
```

If any step fails, view the logs:

```bash
gh run view 123456789 --log-failed
```

---

## Part 4: Cosign — Image Signing and Verification

Cosign solves a supply chain attack vector: if someone compromises GHCR and replaces `ghcr.io/kolinzking/aois:latest` with a malicious image, the cluster would pull and run it. With Cosign, every image is signed with a cryptographic signature. The cluster can verify the signature before pulling — an image without a valid signature is rejected.

### Keyless Signing

Traditional signing requires a long-lived private key. You generate it, secure it, rotate it, never lose it. Keyless signing (Sigstore) eliminates this:

1. The GitHub Actions runner requests a short-lived certificate from Fulcio (Sigstore's CA) using GitHub's OIDC token — the token proves "this is the Actions workflow at github.com/kolinzking/aois, triggered by the `ci.yml` workflow on the `main` branch"
2. Fulcio issues a certificate valid for 10 minutes, embedding the workflow identity
3. Cosign signs the image with this certificate and uploads the signature to Rekor (Sigstore's transparency log)
4. The signature is stored in the OCI registry alongside the image — no separate database needed

The result: the signature is cryptographically bound to a specific GitHub Actions workflow identity. No stolen key can produce a valid signature unless the attacker has access to that specific repository and workflow.

### Verifying a Signature

```bash
# After the pipeline runs, verify the signature on the pushed image
cosign verify \
  --certificate-identity-regexp="https://github.com/kolinzking/aois" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/kolinzking/aois:latest | jq '.[0].optional'
```

Expected:
```json
{
  "Issuer": "https://token.actions.githubusercontent.com",
  "Subject": "https://github.com/kolinzking/aois/.github/workflows/ci.yml@refs/heads/main",
  "githubWorkflowName": "CI",
  "githubWorkflowRef": "refs/heads/main",
  "githubWorkflowRepository": "kolinzking/aois",
  "githubWorkflowSha": "abc123..."
}
```

The `Subject` field is the workflow identity — you can confirm exactly which workflow and branch produced this image. Any image without a valid Cosign signature from the expected workflow identity is rejected by the admission webhook (configured in v30).

---

## ▶ STOP — do this now: Trigger a Pipeline Failure

Push a commit with a deliberate lint error. Observe the PR gate failing.

```bash
# Create a test branch
git checkout -b test/lint-failure

# Introduce a lint error — undefined variable
echo "
def bad_function():
    return undefined_variable
" >> main.py

git add main.py
git commit -m "test: deliberate lint failure"
git push -u origin test/lint-failure

# Open a PR
gh pr create --title "Test: lint failure gate" --body "This PR should fail CI."
```

Watch the CI run:

```bash
gh run watch
```

Expected — the lint step fails, the test and build steps never start:
```
JOBS
✗ Lint, Test, Evals (ubuntu-latest)
  ✗ Lint (ruff)     ← fails here
  - Run tests        ← skipped
  - Run agent evals  ← skipped
- Build, Scan, Sign, Push  ← never starts (needs: lint-test failed)
```

The PR is now blocked from merging. Clean up:

```bash
git checkout main
git branch -d test/lint-failure
git push origin --delete test/lint-failure
gh pr close --delete-branch
```

Revert the change to `main.py`:

```bash
# Remove the last 5 lines added to main.py
head -n -5 main.py > /tmp/main_clean.py && mv /tmp/main_clean.py main.py
git add main.py
git commit -m "revert: remove test lint error"
git push
```

---

## Part 5: Dagger — Pipeline as Code

Dagger solves a specific problem: CI YAML and local development diverge. You add a step to the GitHub Actions workflow that works in CI. Three months later, someone runs the pipeline locally on their machine with a different Python version and the step fails. Or the reverse: a step works locally but fails in CI because the CI runner doesn't have a locally-installed global package.

Dagger runs every pipeline step in a Docker container. The same container image, the same environment, whether you run it on your laptop or in GitHub Actions. If the Dagger pipeline passes locally, it will pass in CI.

### The AOIS Dagger Pipeline

```python
# dagger_pipeline.py
"""AOIS CI pipeline via Dagger — runs identically locally and in GitHub Actions."""
import anyio
import dagger


async def pipeline():
    async with dagger.Connection() as client:
        src = client.host().directory(
            ".",
            exclude=["dashboard/node_modules", "__pycache__", ".git", "*.pyc"],
        )

        # All steps run in this container — identical locally and in CI
        python = (
            client.container()
            .from_("python:3.11-slim")
            .with_directory("/app", src)
            .with_workdir("/app")
            .with_exec(["pip", "install", "-q", "-r", "requirements.txt", "ruff", "pytest"])
        )

        # Step 1: Lint
        print("Running lint...")
        lint = python.with_exec(["ruff", "check", ".", "--ignore", "E501"])
        lint_output = await lint.stdout()
        print(lint_output or "Lint: OK (no issues)")

        # Step 2: Build Docker image
        print("Building image...")
        image = client.container().build(src)
        addr = await image.publish("ghcr.io/kolinzking/aois:dagger-local")
        print(f"Published: {addr}")


if __name__ == "__main__":
    anyio.run(pipeline)
```

### Running Locally

```bash
python3 dagger_pipeline.py
```

Expected:
```
Running lint...
Lint: OK (no issues)
Building image...
Published: ghcr.io/kolinzking/aois:dagger-local@sha256:abc123...
```

The `client.container().from_("python:3.11-slim")` step pulls the same base image that the GitHub Actions runner would use. The `pip install` command runs inside that container. Ruff is installed inside the container. If the container has Python 3.11.x and your laptop has Python 3.11.y, it does not matter — they are both `python:3.11-slim` from the same Docker Hub image.

### Integrating Dagger into GitHub Actions

```yaml
# In .github/workflows/ci.yml, replace the manual lint step with Dagger:
      - name: Run Dagger pipeline
        run: |
          pip install dagger-io anyio
          python3 dagger_pipeline.py
        env:
          DAGGER_CLOUD_TOKEN: ${{ secrets.DAGGER_CLOUD_TOKEN }}  # optional: remote cache
```

The same Python file runs locally (`python3 dagger_pipeline.py`) and in CI (`python3 dagger_pipeline.py`). No YAML to maintain separately. No drift.

### Why Not Just Use GitHub Actions YAML?

Both work. The specific problem Dagger solves:

- **Reproducibility**: YAML steps run directly on the runner OS. If the runner has a different OS version or globally-installed tools, behavior differs. Dagger steps run in defined container images — identical everywhere.
- **Local testing**: to test a GitHub Actions step locally, you need `act` (a complex tool that imperfectly simulates GitHub's runner) or you push and wait for CI. With Dagger, you just run `python3 dagger_pipeline.py`.
- **Reusability**: Dagger pipeline code is Python — you can import it, test it, version it. GitHub Actions YAML is not reusable across repositories without copying.

The honest trade-off: Dagger adds a dependency (the Dagger engine, which is itself a Docker container). For simple pipelines, it may be overhead. For pipelines that developers run frequently locally, it is clearly worth it.

---

## Part 6: OpenFeature — Safe Model Rollouts

OpenFeature is a feature flag standard with provider-agnostic SDKs. For AOIS, it enables controlled model rollouts: ship a new Claude model to 5% of traffic first. If accuracy holds, promote to 100%. If it degrades, flip back without a redeploy.

This is how you upgrade AI models safely. Without feature flags, a model upgrade is all-or-nothing: 100% of production traffic immediately on the new model, with no ability to roll back without a full redeploy.

### The Flag Configuration

The actual flag configuration used in AOIS lives in `flags/aois-flags.yaml`:

```yaml
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
        - ['on', 5]    # 5% of requests get the new model
        - ['off', 95]  # 95% get the stable model

  enable-extended-thinking:
    state: ENABLED
    variants:
      'on': true
      'off': false
    defaultVariant: 'off'
    targeting:
      if:
        - in:
          - var: severity
          - - P1           # only P1 incidents get extended thinking
        - 'on'
        - 'off'

  model-tier-override:
    state: DISABLED          # disabled by default, enable for testing
    variants:
      haiku: 'claude-haiku-4-5-20251001'
      sonnet: 'claude-sonnet-4-6'
      opus: 'claude-opus-4-7'
    defaultVariant: haiku
```

Three flags, three use cases:
- `use-opus-4-7`: percentage-based rollout of a new model — the rollout flag
- `enable-extended-thinking`: conditional flag based on incident severity — extended thinking only where it matters
- `model-tier-override`: a testing flag that is disabled in production but can be enabled to force a specific model for debugging

### How `fractionalEvaluation` Works

The `fractionalEvaluation` splitting is deterministic per `session_id`. Given a `session_id`, the flag evaluator computes `hash(flagKey + session_id) mod 100`. If the result is < 5, the session gets `'on'`. If ≥ 5, it gets `'off'`.

This means:
- The same `session_id` always gets the same model variant throughout a rollout — a user's session does not flip models mid-conversation
- The split is genuinely uniform — 5% of unique session IDs get the new model
- No coordination is needed between AOIS pods — each pod evaluates the flag independently and gets the same result for the same `session_id`

### Integration in AOIS

```python
# openfeature_rollout.py (in main.py integration)
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

api.set_provider(FlagdProvider(host="localhost", port=8013))
client = api.get_client("aois")


def get_model_for_request(session_id: str, severity: str) -> str:
    """
    Use OpenFeature to determine which model to use for this request.
    Allows safe rollout: 5% of traffic to new model, remainder to stable.
    """
    use_new_model = client.get_boolean_value(
        "use-opus-4-7",
        default_value=False,
        evaluation_context={
            "session_id": session_id,
            "severity": severity,
        },
    )

    use_thinking = client.get_boolean_value(
        "enable-extended-thinking",
        default_value=False,
        evaluation_context={"severity": severity},
    )

    if use_new_model and severity in ("P1", "P2"):
        model = "claude-opus-4-7"
    else:
        model = "claude-haiku-4-5-20251001"

    return model, use_thinking
```

### Running flagd

flagd is the OpenFeature flag daemon that reads the YAML config and serves flag evaluations over gRPC/HTTP:

```bash
# Run flagd locally (reads flags/aois-flags.yaml)
docker run -p 8013:8013 \
  -v $(pwd)/flags:/etc/flagd \
  ghcr.io/open-feature/flagd:latest \
  start --uri file:/etc/flagd/aois-flags.yaml
```

Expected:
```
{"level":"info","ts":1714000000,"msg":"starting flagd","port":8013}
{"level":"info","ts":1714000000,"msg":"watching file","uri":"file:/etc/flagd/aois-flags.yaml"}
```

---

## ▶ STOP — do this now: Verify OpenFeature Routing

With flagd running, test the flag evaluation:

```bash
# Evaluate the flag directly via flagd HTTP API
curl -s http://localhost:8013/flagd.evaluation.v1.Service/ResolveBoolean \
  -H "Content-Type: application/json" \
  -d '{"flagKey":"use-opus-4-7","context":{"session_id":"test-abc123"}}' | jq .
```

Expected:
```json
{
  "value": false,
  "reason": "TARGETING_MATCH",
  "variant": "off"
}
```

Try 20 different session IDs and confirm approximately 1 gets `value: true`:

```bash
for i in $(seq 1 20); do
  RESULT=$(curl -s http://localhost:8013/flagd.evaluation.v1.Service/ResolveBoolean \
    -H "Content-Type: application/json" \
    -d "{\"flagKey\":\"use-opus-4-7\",\"context\":{\"session_id\":\"session-$i\"}}" | jq -r '.variant')
  echo "session-$i: $RESULT"
done
```

Expected (approximately 1 out of 20 showing `on`, exact sessions depend on hash):
```
session-1: off
session-2: off
session-3: off
session-4: on
session-5: off
...
session-20: off
```

Now test the severity-conditional flag for extended thinking:

```bash
# P1 severity → should get extended thinking enabled
curl -s http://localhost:8013/flagd.evaluation.v1.Service/ResolveBoolean \
  -H "Content-Type: application/json" \
  -d '{"flagKey":"enable-extended-thinking","context":{"severity":"P1"}}' | jq .value
# Expected: true

# P3 severity → should not get extended thinking
curl -s http://localhost:8013/flagd.evaluation.v1.Service/ResolveBoolean \
  -H "Content-Type: application/json" \
  -d '{"flagKey":"enable-extended-thinking","context":{"severity":"P3"}}' | jq .value
# Expected: false
```

---

## Part 7: Branch Protection

Set branch protection on `main` to enforce: all code passes CI, all code is reviewed. No direct pushes to `main`.

```bash
gh api repos/kolinzking/aois/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["Lint, Test, Evals","Build, Scan, Sign, Push"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null
```

Expected:
```
{
  "url": "https://api.github.com/repos/kolinzking/aois/branches/main/protection",
  "required_status_checks": {...},
  "enforce_admins": {"enabled": true},
  "required_pull_request_reviews": {"required_approving_review_count": 1}
}
```

Test it — try to push directly to main:

```bash
# Make a local change without a PR
echo "# test" >> README.md
git add README.md
git commit -m "test direct push"
git push origin main
```

Expected (push rejected):
```
remote: error: GH006: Protected branch update failed for refs/heads/main.
remote: error: Required status check "Lint, Test, Evals" is expected.
To https://github.com/kolinzking/aois.git
 ! [remote rejected] main -> main (protected branch hook declined)
```

Revert:

```bash
git reset HEAD~1
git checkout README.md
```

---

## Common Mistakes

### 1. Trivy Scans Local Cache Instead of the Pushed Image

**Wrong pattern**:
```yaml
- name: Build and push
  uses: docker/build-push-action@v5
  with:
    tags: ghcr.io/kolinzking/aois:latest

- name: Trivy scan
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ghcr.io/kolinzking/aois:latest   # ← may pull cached version
```

**Exact problem**: if the `latest` tag already exists in GHCR from a prior build, Trivy may pull that prior image instead of the one just pushed. The CVEs you think you scanned are from the old image.

**Correct pattern — use the digest**:
```yaml
- name: Build and push
  id: build                                     # give it an id
  uses: docker/build-push-action@v5

- name: Trivy scan
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ghcr.io/kolinzking/aois@${{ steps.build.outputs.digest }}
```

The digest is the SHA256 hash of the image manifest — it uniquely identifies exactly what was just pushed. No ambiguity.

### 2. `git push` in CI Fails — Missing `contents: write` Permission

**Exact error** (in the SHA bump step):
```
remote: Permission to kolinzking/aois.git denied to github-actions[bot].
fatal: unable to access 'https://github.com/...': The requested URL returned error: 403
```

**Cause**: the job does not have the `contents: write` permission. By default, the `GITHUB_TOKEN` has read-only permissions on the repository contents.

**Fix**: add explicit permissions to the job:
```yaml
jobs:
  build-push:
    permissions:
      contents: write   # needed for git push
      packages: write   # needed for GHCR push
      id-token: write   # needed for Cosign OIDC signing
```

All three are needed in the build-push job. The `lint-test` job needs none of them.

### 3. Cosign Sign Fails — Missing `id-token: write`

**Exact error**:
```
error: error getting Sigstore rekor client: OIDC error: failed to get OIDC token: could not request OIDC token: ...
```

**Cause**: Cosign keyless signing requires a GitHub OIDC token to authenticate with Fulcio. The OIDC token is only available if the job has `id-token: write` permission.

**Fix**: add `id-token: write` to the job's `permissions` block (see above).

### 4. SHA Bump Commit Fails — Nothing to Commit

**Exact error**:
```
error: nothing to commit, working tree clean
```

**Cause**: the image SHA in `values.prod.yaml` is already set to the current SHA (same commit re-run, or a run triggered by the SHA bump commit itself — creating an infinite loop).

**Fix**: make the commit conditional:
```bash
git diff --staged --quiet || git commit -m "ci: bump image to ${{ github.sha }}"
```

The `||` means: if `git diff --staged --quiet` succeeds (no diff = nothing to commit), skip the commit. If it fails (there is a diff), run the commit.

### 5. ArgoCD Not Picking Up New Image After SHA Bump

**Symptom**: the SHA bump commit appears in git, but the cluster is still running the old image.

**Diagnosis**:
```bash
argocd app get aois
# Look for: Sync Status: OutOfSync
argocd app history aois
# Look for: last sync time vs. last commit time
```

**Cause**: ArgoCD polls the git repository every 3 minutes by default. The new commit may not have been detected yet.

**Fix 1 — wait**: ArgoCD will pick it up within 3 minutes.

**Fix 2 — force sync**: `argocd app sync aois --force`

**Fix 3 — add a webhook** (recommended): in the GitHub repository, add a webhook pointing to ArgoCD's webhook endpoint. ArgoCD syncs within seconds of a push.

```bash
# Get the ArgoCD webhook URL
echo "https://$(kubectl get ingress -n argocd argocd-server-ingress -o jsonpath='{.spec.rules[0].host}')/api/webhook"
# Add this URL to GitHub Settings → Webhooks → Add webhook
# Content-Type: application/json
# Events: Push events
```

---

## Troubleshooting

### `cosign: command not found` in CI

The `sigstore/cosign-installer@v3` action installs Cosign in the PATH for subsequent steps. It must appear as a step **before** the `cosign sign` step. If the steps are reordered, Cosign is not in PATH.

```yaml
# Correct order
- name: Install Cosign
  uses: sigstore/cosign-installer@v3

- name: Sign image
  run: cosign sign --yes ...
```

### Dagger Pipeline Hangs on `client.container().build(src)`

Dagger builds the Dockerfile from the local source. If the Dockerfile has a step that hangs (network timeout, missing package), the build hangs silently.

Debug by running the Dockerfile build directly:
```bash
docker build --no-cache -t aois-debug .
```

If this hangs too, the problem is in the Dockerfile, not Dagger.

### `ruff: line too long (E501)` Failing CI

The AOIS codebase has some long lines in auto-generated files and Kafka consumer log format strings. E501 is disabled in the `ruff check . --ignore E501` invocation. If CI is failing on E501:

```bash
# Confirm the flag is being passed
ruff check . --ignore E501 --verbose 2>&1 | head -20
```

If the issue persists, add a `ruff.toml` or `pyproject.toml` entry:
```toml
[tool.ruff.lint]
ignore = ["E501"]
```

### flagd Not Resolving Flags — `PROVIDER_NOT_READY`

**Exact error** (in Python):
```
openfeature.exception.ProviderFatalError: PROVIDER_NOT_READY
```

**Cause**: `api.set_provider(FlagdProvider(...))` is asynchronous — the provider takes a moment to connect to flagd and load flag configs.

**Fix**: add initialization wait:
```python
import time
api.set_provider(FlagdProvider(host="localhost", port=8013))
time.sleep(1)  # wait for provider initialization
client = api.get_client("aois")
```

Or check provider state:
```python
from openfeature.provider import ProviderStatus
while api.get_provider_details().status != ProviderStatus.READY:
    time.sleep(0.1)
```

---

## Connection to Later Phases

**v29 (W&B)**: the GitHub Actions pipeline runs agent evals on every merge. v29 adds W&B logging to those evals — every merge creates a W&B run with accuracy, latency, and cost metrics. The trend over time is the evidence that AOIS quality is improving, not degrading.

**v30 (IDP)**: Crossplane tenant provisioning uses the same GHCR images that the CI pipeline builds and signs. The Cosign signature is verified before the image is pulled into any tenant namespace — the admission webhook built in v30 enforces this. The CI pipeline is the supply chain security layer for the IDP.

**v34.5 (Capstone)**: the pipeline is the enforcement layer for agent SLOs. No agent prompt change ships without passing the eval suite (accuracy ≥ 90%, safety = 100%). The pipeline is not just "run tests" — it is "run the quality gates that we committed to in our SLO." Without this pipeline, the SLOs are aspirational. With it, they are enforced.

---

## Mastery Checkpoint

You have completed v28 when you can do all of the following:

1. **Trigger a lint failure**: push a commit with a deliberate ruff error. Confirm the CI job fails on the lint step, the build step never starts, and the PR cannot be merged. Show the GitHub Actions job output.

2. **Verify image signing**: after a successful merge-to-main run, run `cosign verify` on the pushed image. Show the output including the `Subject` field that contains the GitHub Actions workflow identity.

3. **Explain the permission trifecta**: what are `contents: write`, `packages: write`, and `id-token: write`, which step in the pipeline needs each one, and what breaks if any is missing?

4. **OpenFeature rollout test**: with flagd running, send 20 requests with different `session_id` values. Confirm approximately 1 gets the new model. Change the percentage from 5 to 50 in `flags/aois-flags.yaml` and confirm approximately 10 get the new model. Explain why the split is deterministic per `session_id`.

5. **Explain Dagger vs. GitHub Actions YAML**: what specific failure mode does Dagger prevent? When would you choose Dagger over plain YAML? When is plain YAML sufficient?

6. **Run the Dagger pipeline locally**: `python3 dagger_pipeline.py` completes successfully, lint passes, image is published to `ghcr.io/kolinzking/aois:dagger-local`. Show the output.

7. **Fix a Trivy HIGH CVE**: introduce a known-vulnerable dependency (e.g., an old version of `requests`), push, observe the Trivy step fail with `HIGH` severity. Update the dependency, push, observe the pipeline pass.

8. **Force-sync ArgoCD after a SHA bump**: after the pipeline pushes a new SHA to `values.prod.yaml`, force ArgoCD to sync immediately rather than waiting for the polling interval. Confirm the new pod is running the correct image SHA.

**The mastery bar:** every push to `main` automatically builds, scans, signs, and deploys AOIS. No manual deploy steps exist. No unsigned images run in production. A model change ships to 5% of traffic first. You can demonstrate all of this with zero manual intervention after `git push`.

---

## 4-Layer Tool Understanding

---

### GitHub Actions

| Layer | |
|---|---|
| **Plain English** | Without CI, deploying AOIS means manually remembering to run tests, build the image, scan it, and push it — in the right order, every time. GitHub Actions does all of this automatically on every push. Nothing gets skipped because someone was in a hurry. |
| **System Role** | Between `git push` and production. Every merge to `main` triggers: lint → test → evals → build → Trivy scan → Cosign sign → push → ArgoCD sync. Every step must pass for the next to start. Manual deploy steps are eliminated entirely. |
| **Technical** | A YAML-defined workflow runner hosted by GitHub. Jobs run in ephemeral Ubuntu VMs. Steps call Actions (pre-built Docker containers or JavaScript) or run shell commands directly. Secrets are injected as environment variables — never exposed in logs. `outputs` from one step pass data to subsequent steps (e.g., the build step outputs the image digest for the scan step). |
| **Remove it** | Remove CI → deployments are manual. Trivy scans get skipped under deadline pressure. Agent evals do not run on every change. The first time an unscanned image ships with a CRITICAL CVE, or a prompt change silently breaks P1 classification, the missing gate becomes obvious. In a regulated environment, manual deployments fail audit on the first review. |

---

### Cosign / Sigstore

| Layer | |
|---|---|
| **Plain English** | If someone replaces your production Docker image with a malicious one, your cluster would pull and run it without knowing. Cosign puts a verifiable signature on every image. The cluster checks the signature before running anything — an image without a valid signature from your build pipeline is rejected. |
| **System Role** | At the end of the build pipeline (sign before push) and optionally at the cluster admission layer (verify before pull). The signature is stored in the OCI registry alongside the image — no separate signature database. The signature is cryptographically bound to the GitHub Actions workflow identity that produced it. |
| **Technical** | A tool from the Sigstore project. Keyless signing uses GitHub's OIDC token (no long-lived private key to manage). Fulcio issues a short-lived certificate embedding the workflow identity. The signature is uploaded to Rekor (a public transparency log). `cosign sign --yes` runs in the pipeline. `cosign verify --certificate-identity-regexp --certificate-oidc-issuer` verifies. |
| **Remove it** | Remove Cosign → any image that passes Trivy can be deployed to production, including one replaced by a supply chain attack. In regulated industries (finance, healthcare, government), unsigned container images fail compliance checks immediately — it is not optional. |

---

### Dagger

| Layer | |
|---|---|
| **Plain English** | Your GitHub Actions pipeline passes but the same steps fail on your laptop. "Works in CI" is not "works anywhere." Dagger runs each pipeline step in a defined Docker container — the same container in CI and locally. If the Dagger pipeline passes locally, it passes in CI. The environment divergence problem is eliminated. |
| **System Role** | A wrapper around the pipeline steps. The same `dagger_pipeline.py` runs on any developer's machine and in the GitHub Actions runner. Docker is the only required dependency. Steps that pass locally pass in CI. Steps that fail in CI can be reproduced and debugged locally without pushing to GitHub. |
| **Technical** | A programmable CI/CD engine that runs pipelines as containerized DAGs. Written in Python (or TypeScript/Go/Java). Each step runs in an ephemeral container with a defined input directory. Outputs from one step can be passed as inputs to the next. Caching is automatic — unchanged layers are not rebuilt. Dagger Cloud provides remote caching and run history. |
| **Remove it** | Remove Dagger → CI-local divergence returns. A CI step uses `python:3.11.9-slim`; the local machine has `python:3.11.6`. A package works locally because it is installed globally but missing from `requirements.txt`. These divergences are discovered during urgent incidents when someone tries to run the pipeline locally, not during normal development. |

---

### OpenFeature (Model Rollouts)

| Layer | |
|---|---|
| **Plain English** | Shipping a new Claude model to 100% of production traffic at once is risky — you cannot see if accuracy drops until operators are affected. OpenFeature sends 5% of traffic to the new model first. If accuracy holds for 24 hours, promote to 50%, then 100%. If accuracy drops, flip back in 30 seconds without a redeploy. |
| **System Role** | In the model selection layer, between the incident classifier and the LLM call. `get_model_for_request(session_id, severity)` checks the OpenFeature flag for each request. The split is deterministic per `session_id` — a session always gets the same model throughout a rollout. Flag configuration lives in `flags/aois-flags.yaml`. |
| **Technical** | An open standard for feature flag evaluation with provider-agnostic SDKs. AOIS uses the flagd provider — flagd is a sidecar that reads YAML flag configs and serves evaluations over gRPC. The `fractionalEvaluation` targeting uses `hash(flagKey + contextValue) mod 100` for deterministic, uniform splits. The same evaluation logic runs whether the SDK is Python, TypeScript, or Go. |
| **Remove it** | Remove OpenFeature → model updates are all-or-nothing. A new Claude model ships to 100% of traffic immediately. If it has worse P1 accuracy, every operator is affected simultaneously. Rollback requires a full redeploy — 5-10 minutes of degraded classification. With OpenFeature, rollback is a YAML edit and a flagd reload: 30 seconds, no downtime, no redeploy. |
