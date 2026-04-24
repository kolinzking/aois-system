"""Expose AOIS as a Semantic Kernel plugin — usable from any SK application."""
import httpx
import os

try:
    from semantic_kernel.functions import kernel_function
    from semantic_kernel import Kernel
    _SK_AVAILABLE = True
except ImportError:
    _SK_AVAILABLE = False
    kernel_function = lambda **kw: (lambda f: f)  # no-op decorator


AOIS_API_URL = os.getenv("AOIS_API_URL", "http://localhost:8000")


class AOISPlugin:
    """AOIS as a Semantic Kernel plugin."""

    @kernel_function(description="Analyze a Kubernetes incident and return severity + proposed action")
    async def analyze_incident(self, incident: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{AOIS_API_URL}/analyze", json={"log": incident})
            data = resp.json()
            return (
                f"Severity: {data.get('severity', 'unknown')}\n"
                f"Summary: {data.get('summary', '')}\n"
                f"Action: {data.get('suggested_action', '')}"
            )

    @kernel_function(description="List recent P1/P2 AOIS incidents")
    async def get_recent_incidents(self, limit: int = 10) -> str:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{AOIS_API_URL}/api/incidents?limit={limit}")
            incidents = resp.json()
            critical = [i for i in incidents if i.get("severity") in ("P1", "P2")]
            return f"Found {len(critical)} P1/P2 incidents out of {len(incidents)} recent incidents."


def build_kernel() -> object:
    """Build a Semantic Kernel with the AOIS plugin registered."""
    if not _SK_AVAILABLE:
        raise ImportError("pip install semantic-kernel")
    kernel = Kernel()
    kernel.add_plugin(AOISPlugin(), plugin_name="AOIS")
    return kernel
