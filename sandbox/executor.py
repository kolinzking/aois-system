"""
E2B sandbox executor for AOIS remediation validation.
Runs proposed kubectl commands with --dry-run=client.
Returns stdout, stderr, and whether the command is safe to apply.
"""
import logging
import os
from dataclasses import dataclass

log = logging.getLogger("sandbox.executor")

_BLOCKED_VERBS = ["delete namespace", "delete cluster", "delete node"]


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    safe_to_apply: bool
    validation_message: str


def validate_kubectl_command(kubectl_command: str) -> SandboxResult:
    """
    Run a kubectl command with --dry-run=client in an E2B sandbox.
    Returns validation result — never applies to production.
    """
    # Block destructive verbs before reaching the sandbox
    if any(verb in kubectl_command.lower() for verb in _BLOCKED_VERBS):
        return SandboxResult(
            stdout="",
            stderr="BLOCKED: command contains forbidden verb",
            exit_code=1,
            safe_to_apply=False,
            validation_message="Command blocked before sandbox execution: destructive verb detected",
        )

    # Force --dry-run=client — strip existing flag first
    safe_command = kubectl_command.replace("--dry-run=server", "").replace("--dry-run=client", "").strip()
    safe_command = f"{safe_command} --dry-run=client"

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

    e2b_key = os.getenv("E2B_API_KEY")
    if not e2b_key:
        log.warning("E2B_API_KEY not set — skipping sandbox validation")
        return SandboxResult(
            stdout="",
            stderr="E2B_API_KEY not configured",
            exit_code=0,
            safe_to_apply=False,
            validation_message="Sandbox unavailable — E2B API key not configured. Manual review required.",
        )

    log.info("Running in sandbox: %s", safe_command[:120])
    try:
        from e2b_code_interpreter import Sandbox

        with Sandbox(api_key=e2b_key, timeout=120) as sandbox:
            sandbox.run_code(
                "import subprocess; subprocess.run(['apt-get', 'install', '-y', '-q', 'kubectl'], "
                "capture_output=True)"
            )
            result = sandbox.run_code(python_script)
            stdout = "".join(result.logs.stdout) if result.logs.stdout else ""
            stderr = "".join(result.logs.stderr) if result.logs.stderr else ""
            exit_code = 0 if result.error is None else 1
            safe_to_apply = exit_code == 0 and "error" not in stderr.lower()

            return SandboxResult(
                stdout=stdout[:1000],
                stderr=stderr[:500],
                exit_code=exit_code,
                safe_to_apply=safe_to_apply,
                validation_message=(
                    "Dry-run succeeded — command is structurally valid"
                    if safe_to_apply
                    else f"Dry-run failed: {stderr[:200]}"
                ),
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
    e2b_key = os.getenv("E2B_API_KEY")
    if not e2b_key:
        return SandboxResult(
            stdout="",
            stderr="E2B_API_KEY not configured",
            exit_code=1,
            safe_to_apply=False,
            validation_message="Sandbox unavailable — E2B API key not configured",
        )

    log.info("Running Python script in sandbox (%d chars)", len(script))
    try:
        from e2b_code_interpreter import Sandbox

        with Sandbox(api_key=e2b_key, timeout=timeout) as sandbox:
            result = sandbox.run_code(script)
            stdout = "".join(result.logs.stdout) if result.logs.stdout else ""
            stderr = "".join(result.logs.stderr) if result.logs.stderr else ""
            exit_code = 0 if result.error is None else 1

            return SandboxResult(
                stdout=stdout[:2000],
                stderr=stderr[:1000],
                exit_code=exit_code,
                safe_to_apply=exit_code == 0,
                validation_message=(
                    "Script completed"
                    if exit_code == 0
                    else f"Script error: {stderr[:200]}"
                ),
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
