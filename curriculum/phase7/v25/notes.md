# v25 — E2B: Safe Code Execution for Autonomous Remediation

⏱ **Estimated time: 4–6 hours**

---

## Prerequisites

v24 complete. E2B account created.

```bash
# Pydantic AI agent works
python3 -c "from multi_agent.pydantic_agent import IncidentAnalysis; print('ok')"
# ok

# LangGraph agent works
python3 -c "from langgraph_agent.graph import run_investigation; print('ok')"
# ok

# E2B SDK
pip install e2b-code-interpreter
python3 -c "import e2b_code_interpreter; print('ok')"
# ok
```

---

## Learning Goals

By the end you will be able to:

- Explain what E2B is and why "run agent-generated code in production" is unsafe without a sandbox
- Execute Python and shell scripts in an E2B sandbox and inspect stdout, stderr, and exit code
- Build the AOIS remediation sandbox: AOIS generates a `kubectl` patch → runs it in E2B → validates the output → proposes to human for final apply
- Explain the trust boundary: what the sandbox can and cannot prevent
- Integrate the sandbox into the LangGraph `remediate_node` so E2B validates before any write touches production

---

## The Problem This Solves

The `remediate_node` in v23 says:

```python
result = f"[SIMULATED] Would execute: {action}"
```

That is honest — it simulates because it cannot safely run arbitrary code. AOIS is an LLM — it can generate subtly wrong commands. A wrong `kubectl patch` could take down more than the broken pod.

The gap: AOIS needs a place to run the proposed fix, see what happens, and confirm it works — before asking a human to approve applying it to production.

E2B (e2b.dev) provides secure cloud sandboxes for running AI-generated code. Each sandbox is an isolated VM that starts in seconds, runs your code, and is destroyed when done. It has no access to your production cluster. It is purpose-built for this use case: "let the AI run code where the blast radius is zero."

---

## What E2B Is

E2B is a service that provides on-demand sandboxed environments for AI agents. Each sandbox is a microVM (Firecracker) with:
- Full Linux environment
- Configurable packages
- No network access to production systems by default
- Configurable timeout (default 5 minutes)
- Full stdout/stderr capture

The Python SDK launches a sandbox, executes code, and returns the result. The sandbox is destroyed when the context manager exits.

```python
from e2b_code_interpreter import Sandbox

with Sandbox() as sandbox:
    result = sandbox.run_code("print('hello from sandboxed Python')")
    print(result.logs.stdout)  # ['hello from sandboxed Python\n']
    print(result.error)        # None if no error
```

---

## The AOIS Remediation Flow

```
LangGraph remediate_node
    ↓
Generate proposed_action (kubectl command string)
    ↓
E2B sandbox: run kubectl --dry-run=client (validates without applying)
    ↓
E2B result: stdout + stderr + exit_code
    ↓
LLM evaluates: does the dry-run output confirm the fix is safe?
    ↓
[HUMAN APPROVAL GATE]
    ↓ approved
Apply to production: kubectl (real cluster)
```

The key: `kubectl --dry-run=client` validates the command structure without touching the cluster. E2B runs this validation. If it fails (malformed manifest, wrong field name), the error is caught in the sandbox, not in production.

---

## Building the Sandbox Executor

```python
# sandbox/executor.py
"""
E2B sandbox executor for AOIS remediation validation.
Runs proposed kubectl commands with --dry-run=client.
Returns stdout, stderr, and whether the command is safe to apply.
"""
import logging
import os
from dataclasses import dataclass

log = logging.getLogger("sandbox.executor")


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    safe_to_apply: bool
    validation_message: str


def validate_kubectl_command(kubectl_command: str, kubeconfig: str = "") -> SandboxResult:
    """
    Run a kubectl command with --dry-run=client in an E2B sandbox.
    Returns validation result — never applies to production.
    """
    from e2b_code_interpreter import Sandbox

    # Force dry-run — strip any existing --dry-run flag first, then add ours
    safe_command = kubectl_command.replace("--dry-run=server", "").replace("--dry-run=client", "").strip()
    safe_command = f"{safe_command} --dry-run=client"

    # Reject immediately if command contains destructive verbs we never want to sandbox-test
    _blocked_verbs = ["delete namespace", "delete cluster", "delete node"]
    if any(verb in safe_command.lower() for verb in _blocked_verbs):
        return SandboxResult(
            stdout="",
            stderr="BLOCKED: command contains forbidden verb",
            exit_code=1,
            safe_to_apply=False,
            validation_message="Command blocked before sandbox execution: destructive verb detected",
        )

    python_script = f"""
import subprocess, sys
result = subprocess.run(
    {repr(safe_command.split())},
    capture_output=True,
    text=True,
    timeout=30,
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("EXIT_CODE:", result.returncode)
sys.exit(result.returncode)
"""

    log.info("Running in sandbox: %s", safe_command[:120])
    try:
        with Sandbox(
            api_key=os.getenv("E2B_API_KEY"),
            timeout=60,
        ) as sandbox:
            # Install kubectl in sandbox
            sandbox.run_code("import subprocess; subprocess.run(['apt-get', 'install', '-y', '-q', 'kubectl'], capture_output=True)")

            result = sandbox.run_code(python_script)
            stdout = "".join(result.logs.stdout) if result.logs.stdout else ""
            stderr = "".join(result.logs.stderr) if result.logs.stderr else ""
            exit_code = 0 if result.error is None else 1

            safe_to_apply = exit_code == 0 and "error" not in stderr.lower()
            validation_message = (
                "Dry-run succeeded — command is structurally valid"
                if safe_to_apply
                else f"Dry-run failed: {stderr[:200]}"
            )

            return SandboxResult(
                stdout=stdout[:1000],
                stderr=stderr[:500],
                exit_code=exit_code,
                safe_to_apply=safe_to_apply,
                validation_message=validation_message,
            )

    except Exception as e:
        log.warning("Sandbox execution failed: %s", e)
        return SandboxResult(
            stdout="",
            stderr=str(e)[:500],
            exit_code=1,
            safe_to_apply=False,
            validation_message=f"Sandbox error: {e}",
        )


def run_python_in_sandbox(script: str, timeout: int = 60) -> SandboxResult:
    """
    Run arbitrary Python in a sandboxed environment.
    Used for testing remediation scripts before production apply.
    """
    from e2b_code_interpreter import Sandbox

    log.info("Running Python script in sandbox (%d chars)", len(script))
    try:
        with Sandbox(
            api_key=os.getenv("E2B_API_KEY"),
            timeout=timeout,
        ) as sandbox:
            result = sandbox.run_code(script)
            stdout = "".join(result.logs.stdout) if result.logs.stdout else ""
            stderr = "".join(result.logs.stderr) if result.logs.stderr else ""
            exit_code = 0 if result.error is None else 1

            return SandboxResult(
                stdout=stdout[:2000],
                stderr=stderr[:1000],
                exit_code=exit_code,
                safe_to_apply=exit_code == 0,
                validation_message="Script completed" if exit_code == 0 else f"Script error: {stderr[:200]}",
            )

    except Exception as e:
        log.warning("Python sandbox failed: %s", e)
        return SandboxResult(
            stdout="",
            stderr=str(e)[:500],
            exit_code=1,
            safe_to_apply=False,
            validation_message=f"Sandbox error: {e}",
        )
```

---

## ▶ STOP — do this now

Test the sandbox executor with a safe kubectl command:

```bash
# Set E2B API key
export E2B_API_KEY=your_e2b_api_key_here

python3 - << 'EOF'
from sandbox.executor import run_python_in_sandbox

result = run_python_in_sandbox("""
import json
# Simulate what a kubectl dry-run output looks like
manifest = {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {"name": "test"},
    "spec": {"containers": [{"name": "app", "resources": {"limits": {"memory": "512Mi"}}}]}
}
print(json.dumps(manifest, indent=2))
print("Dry-run: pod/test configured (dry run)")
""")
print("stdout:", result.stdout)
print("exit_code:", result.exit_code)
print("safe_to_apply:", result.safe_to_apply)
print("validation_message:", result.validation_message)
EOF
```

Expected:
```
stdout: {"apiVersion": "v1", ...}
Dry-run: pod/test configured (dry run)
exit_code: 0
safe_to_apply: True
validation_message: Script completed
```

---

## Integrating E2B into the LangGraph remediate_node

Replace the simulated remediation in `langgraph_agent/nodes.py`:

```python
# Updated remediate_node with E2B validation
async def remediate_node(state: InvestigationState) -> dict:
    """
    Validate the proposed action in E2B sandbox, then await human approval for production apply.
    """
    log.info("[REMEDIATE] action=%s", state.get("proposed_action", "")[:60])
    if not state.get("human_approved", False):
        return {"remediation_result": "BLOCKED — human approval required"}

    action = state.get("proposed_action", "")

    # If the proposed action looks like a kubectl command, validate it in sandbox
    if action.startswith("kubectl"):
        from sandbox.executor import validate_kubectl_command
        sandbox_result = validate_kubectl_command(action)
        if not sandbox_result.safe_to_apply:
            return {
                "remediation_result": (
                    f"SANDBOX VALIDATION FAILED — action not applied.\n"
                    f"Reason: {sandbox_result.validation_message}\n"
                    f"stderr: {sandbox_result.stderr}"
                )
            }
        result = (
            f"[SANDBOX VALIDATED] Dry-run succeeded.\n"
            f"Command: {action}\n"
            f"Validation: {sandbox_result.validation_message}\n"
            f"PRODUCTION APPLY: would run '{action}' (requires final operator confirm)"
        )
    else:
        # Non-kubectl action: log for human to apply manually
        result = f"[HUMAN APPLY REQUIRED] Proposed: {action}"

    log.info("Remediation validated: %s", result[:100])
    publish_node_event("remediate", state["session_id"], {"result": result[:200]})
    return {"remediation_result": result}
```

---

## AOIS Generates the kubectl Command

The full flow: AOIS receives an OOMKill alert → `hypothesize_node` proposes a memory increase → `remediate_node` generates the kubectl command → E2B validates it → human approves production apply.

```python
# sandbox/generate_kubectl.py
"""
Use Claude to generate a kubectl command from a proposed action description.
The command is then validated in E2B before being presented for human approval.
"""
import anthropic
import os
import re

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def generate_kubectl_patch(proposed_action: str, namespace: str = "default") -> str:
    """
    Ask Claude to generate a specific kubectl command from a natural language action.
    Returns a kubectl command string suitable for dry-run validation.
    """
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"Convert this SRE action to a single kubectl command:\n"
                f"Action: {proposed_action}\n"
                f"Namespace: {namespace}\n\n"
                f"Rules:\n"
                f"- Return ONLY the kubectl command, no explanation\n"
                f"- Use --dry-run=client format\n"
                f"- Never use delete, drain, cordon without explicit instruction\n"
                f"- Prefer 'kubectl set resources' or 'kubectl patch' over editing manifests\n"
                f"- If the action cannot be expressed as a safe kubectl command, return: CANNOT_GENERATE"
            ),
        }],
    )
    text = response.content[0].text.strip()

    # Reject if model says it cannot generate safely
    if "CANNOT_GENERATE" in text or not text.startswith("kubectl"):
        return ""

    # Strip any accidentally included explanation
    first_line = text.split("\n")[0].strip()
    return first_line if first_line.startswith("kubectl") else ""
```

---

## ▶ STOP — do this now

Generate a kubectl command from a natural language action and validate it:

```python
from sandbox.generate_kubectl import generate_kubectl_patch
from sandbox.executor import validate_kubectl_command

action = "increase memory limit for auth-service deployment to 512Mi"
kubectl_cmd = generate_kubectl_patch(action, namespace="default")
print(f"Generated command: {kubectl_cmd}")

if kubectl_cmd:
    result = validate_kubectl_command(kubectl_cmd)
    print(f"Validation: {result.validation_message}")
    print(f"Safe to apply: {result.safe_to_apply}")
else:
    print("No safe command could be generated for this action")
```

Expected output:
```
Generated command: kubectl set resources deployment/auth-service --limits=memory=512Mi --dry-run=client
Validation: Dry-run succeeded — command is structurally valid
Safe to apply: True
```

---

## The Trust Boundary

E2B prevents:
- Running kubectl commands that misconfigure production pods
- Executing scripts that have syntax errors or runtime failures
- Generating invalid manifests that would be rejected by the API server
- Accidental destructive commands (blocked before execution)

E2B does NOT prevent:
- A command that is syntactically valid but semantically wrong (e.g., setting memory to 1Mi instead of 512Mi — valid command, wrong value)
- Kubernetes admission webhooks that reject at apply time but not dry-run time
- Multi-step remediations where step 2 is wrong (E2B only validates each command)

This is why human approval remains in the loop even after E2B validation. E2B is a structural validator — it catches obviously wrong commands. Human review catches semantically wrong commands.

---

## ▶ STOP — do this now

Test the blocked verbs protection:

```python
from sandbox.executor import validate_kubectl_command

blocked = validate_kubectl_command("kubectl delete namespace production")
print(f"Exit code: {blocked.exit_code}")      # 1
print(f"Safe: {blocked.safe_to_apply}")        # False
print(f"Message: {blocked.validation_message}") # BLOCKED: destructive verb
```

Then test a valid command:

```python
valid = validate_kubectl_command(
    "kubectl set resources deployment/auth-service --limits=memory=512Mi -n default"
)
print(f"Safe: {valid.safe_to_apply}")
print(f"Message: {valid.validation_message}")
```

---

## Common Mistakes

### 1. Not stripping --dry-run from user-supplied commands before re-adding it

If `proposed_action` contains `--dry-run=server` and the executor adds `--dry-run=client`, the command has two `--dry-run` flags and fails.

```python
# Wrong — may result in duplicate flags
safe_command = f"{kubectl_command} --dry-run=client"

# Correct — strip existing dry-run first
safe_command = kubectl_command.replace("--dry-run=server", "").replace("--dry-run=client", "").strip()
safe_command = f"{safe_command} --dry-run=client"
```

---

### 2. Treating E2B validation as production safety

E2B validates structure. It does not validate semantics. A command that sets memory to `1Mi` (not `512Mi`) will pass dry-run. Human review is still required.

Avoid: "E2B validated it, so we can skip human approval."
Correct: "E2B validated structure. Human reviews for semantic correctness."

---

### 3. Sandbox timeout too short for kubectl install

E2B sandboxes start fresh — kubectl must be installed on each sandbox start. The install takes 10–15 seconds. With a 30-second timeout, the kubectl install alone may consume most of the budget.

Set `timeout=120` for kubectl operations:

```python
with Sandbox(api_key=os.getenv("E2B_API_KEY"), timeout=120) as sandbox:
```

---

## Troubleshooting

### `e2b.exceptions.AuthenticationException: Invalid API key`

```bash
# Verify the key is set
echo $E2B_API_KEY

# If empty, set it
export E2B_API_KEY=your_key_here
```

---

### `TimeoutError: Sandbox timed out after 60s`

The kubectl install in the sandbox is slow on cold starts. Increase timeout:

```python
with Sandbox(api_key=os.getenv("E2B_API_KEY"), timeout=180) as sandbox:
```

---

### `SandboxResult.safe_to_apply=False` for a valid command

Check `stderr` — the kubectl dry-run may have failed due to missing kubeconfig in the sandbox. The sandbox does not have access to your cluster kubeconfig. For real kubectl validation:

Option 1: Use `kubectl --dry-run=client` which validates only locally (manifest structure, not cluster state)
Option 2: Export a read-only kubeconfig and inject it into the sandbox via environment variable

For v25, option 1 is sufficient — structural validation without cluster access.

---

## Connection to Later Phases

### To v26 (React Dashboard)
The remediation flow (validate → human approval → apply) becomes a UI interaction in v26. The dashboard shows the E2B validation result alongside the proposed action. The human reads the dry-run output and clicks "Apply" or "Reject."

### To v33 (Evals + Red-teaming)
E2B is the safe environment for adversarial testing. PyRIT generates malicious inputs designed to make AOIS produce destructive commands. All PyRIT-generated commands pass through E2B's blocked_verbs check. Any command that bypasses the check and survives sandbox validation is a security finding.

### To v34.5 (Capstone)
The full remediation pipeline (generate → sandbox validate → human approve → production apply) is the capstone's autonomous response system. The capstone measures how often the sandbox catches structurally invalid commands before they reach human review.

---

## Mastery Checkpoint

1. Run `validate_kubectl_command("kubectl delete namespace production")`. Confirm it is blocked before reaching the sandbox. Show the output.

2. Run `generate_kubectl_patch("increase memory limit for auth-service to 512Mi")`. Confirm it generates a structurally valid kubectl command. Run the command through `validate_kubectl_command`. Show the sandbox output.

3. Run `run_python_in_sandbox` with a script that deliberately raises an exception. Confirm the `SandboxResult.exit_code` is 1 and `safe_to_apply` is False.

4. Explain the trust boundary in plain English to a product manager: "E2B validates the command, so the remediation is safe." Is this statement correct? What is missing from it?

5. Update the `langgraph_agent/nodes.py` remediate_node to call `validate_kubectl_command` before returning. Run the LangGraph graph end-to-end against a memory pressure incident and confirm the remediation_result contains "SANDBOX VALIDATED."

6. What happens if the E2B API is down during a P1 incident response? What is the right fallback behavior? Implement it in `validate_kubectl_command`.

7. Explain to a senior engineer: how does E2B differ from just running `subprocess.run` locally on the AOIS server? What specific isolation does it provide?

**The mastery bar:** you can generate a kubectl command from a natural language proposed action, validate it in an E2B sandbox without touching production, and integrate the result into the LangGraph remediation gate — producing a `remediation_result` that includes the sandbox validation output before any human approval prompt.

---

## Advanced: Custom E2B Sandbox Templates

The default E2B sandbox starts with a bare Ubuntu image. For AOIS, you want kubectl, Python 3.11, and a kubeconfig stub pre-installed so sandbox startup does not spend 20 seconds installing dependencies every time.

E2B supports custom templates: define a `Dockerfile`-like template, build it once, and reuse it. The sandbox starts with your pre-installed packages.

```bash
# Install the E2B CLI
npm install -g @e2b/cli

# Login with API key
e2b auth login

# Create a custom template
mkdir aois-sandbox && cd aois-sandbox
cat > e2b.Dockerfile << 'EOF'
FROM e2b/code-interpreter-python:latest

# Install kubectl
RUN apt-get update -q && apt-get install -y -q apt-transport-https ca-certificates curl && \
    curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg && \
    echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | tee /etc/apt/sources.list.d/kubernetes.list && \
    apt-get update -q && apt-get install -y -q kubectl

# Install AOIS Python dependencies
RUN pip install anthropic pydantic

# Create a stub kubeconfig (structure only — no real cluster access)
RUN mkdir -p /root/.kube && cat > /root/.kube/config << 'KUBECONFIG'
apiVersion: v1
clusters:
- cluster:
    server: https://localhost:6443
  name: aois-dry-run
contexts:
- context:
    cluster: aois-dry-run
    user: aois-validator
  name: aois-dry-run
current-context: aois-dry-run
kind: Config
users:
- name: aois-validator
  user:
    token: dry-run-only
KUBECONFIG
EOF

# Build the template (creates a reusable sandbox image)
e2b template build --name aois-validator
# Template ID: xyz123abc (use this in your code)
```

Using the custom template in code:

```python
# sandbox/executor.py — use custom template
with Sandbox(
    template="aois-validator",  # pre-built template ID
    api_key=os.getenv("E2B_API_KEY"),
    timeout=60,
) as sandbox:
    # kubectl is already installed — no installation step needed
    result = sandbox.run_code(python_script)
```

With a custom template, sandbox startup drops from 20+ seconds to under 2 seconds. At scale — running 50 remediation validations per hour — this matters.

---

## E2B vs Local Subprocess vs Docker

Why E2B instead of just `subprocess.run()` on the AOIS server, or `docker run`?

| | Local subprocess | Docker run | E2B |
|---|---|---|---|
| **Isolation** | None — same process, same filesystem | Container isolation | Full microVM (Firecracker) — kernel-level isolation |
| **Network access** | Full access to production systems | Configurable | No access to production by default |
| **Startup time** | Instant | 2–10 seconds | <1 second (template) |
| **Cleanup** | Must be explicit | Must stop/rm container | Automatic on context manager exit |
| **Cost** | Free (but dangerous) | Infrastructure overhead | Per-second billing ($0.000017/s) |
| **Multi-tenancy** | Unsafe (shared process) | Safer (shared kernel) | Full isolation (separate kernel) |

The key difference: a subprocess runs on the same machine as AOIS. If AOIS has cluster credentials, the subprocess inherits them. A malicious or buggy command could use those credentials. E2B runs in an isolated environment with no credential inheritance.

---

## 4-Layer Tool Understanding

### E2B (Code Sandbox)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | An AI agent generating shell commands and running them on your production server is dangerous — one wrong command can take down more than you intended. E2B gives the agent a disposable sandbox to run the command first, see what happens, and confirm it works — before asking a human to approve applying it for real. |
| **System Role** | Where does it sit in AOIS? | Between `hypothesize_node` (which proposes an action) and the human approval gate (which authorizes production apply). E2B validates the proposed kubectl command structurally. If validation fails, the human never sees the command — it is caught before review. If it passes, the human sees the dry-run output alongside the approval request. |
| **Technical** | What is it, precisely? | A service providing on-demand Firecracker microVMs for AI code execution. The Python SDK (`e2b-code-interpreter`) launches a sandbox, executes Python or shell code via `sandbox.run_code()`, captures stdout/stderr, and destroys the sandbox when the context manager exits. Sandboxes have no network access to production systems by default. Each sandbox starts in under 1 second. |
| **Remove it** | What breaks, and how fast? | Remove E2B → proposed kubectl commands cannot be validated before human review. The human sees a natural language action ("increase memory limit to 512Mi") without proof that the command is structurally valid. A malformed command (wrong field name, invalid value format) is caught by the Kubernetes API server at apply time — in production. With E2B, the malformed command was caught in the sandbox. |
