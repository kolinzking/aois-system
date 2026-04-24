"""OpenFGA authorization checks for AOIS resource-level access."""
import httpx
import os
import logging

log = logging.getLogger("aois.openfga")

_FGA_API_URL = os.getenv("OPENFGA_API_URL", "http://localhost:8080")
_FGA_STORE_ID = os.getenv("OPENFGA_STORE_ID", "")


async def can_approve_in_namespace(user_id: str, namespace: str) -> bool:
    """Check if user can approve remediations in a specific namespace."""
    if not _FGA_STORE_ID:
        log.warning("OPENFGA_STORE_ID not set — defaulting to deny")
        return False
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(
                f"{_FGA_API_URL}/stores/{_FGA_STORE_ID}/check",
                json={"tuple_key": {
                    "user": f"user:{user_id}",
                    "relation": "can_approve",
                    "object": f"namespace:{namespace}",
                }},
            )
            return resp.json().get("allowed", False)
        except Exception as e:
            log.warning("OpenFGA check failed: %s — defaulting to deny", e)
            return False


async def write_namespace_permission(user_id: str, namespace: str, relation: str = "can_approve"):
    """Grant a user permission on a namespace."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        await client.post(
            f"{_FGA_API_URL}/stores/{_FGA_STORE_ID}/write",
            json={"writes": {"tuple_keys": [{
                "user": f"user:{user_id}",
                "relation": relation,
                "object": f"namespace:{namespace}",
            }]}},
        )
