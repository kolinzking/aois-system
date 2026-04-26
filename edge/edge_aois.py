"""AOIS edge node — runs on Ollama when offline, syncs to central when online."""
import asyncio
import httpx
import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("aois.edge")

CENTRAL_SYNC_URL = os.getenv("AOIS_CENTRAL_URL", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def _queue_path() -> Path:
    """Lazy queue path — creates parent dir on first call, not at import time."""
    p = Path(os.getenv("AOIS_QUEUE_PATH", "/var/aois/offline_queue.jsonl"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


async def analyze_local(incident: str) -> dict:
    """Analyze using local Ollama — works offline."""
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": (
                        f"SRE incident: {incident}\n"
                        f"Classify severity P1-P4 and propose action.\n"
                        f'Return JSON: {{"severity":"P1","proposed_action":"...","confidence":0.8}}'
                    ),
                    "stream": False,
                    "format": "json",
                },
            )
            data = resp.json()
            result = json.loads(data.get("response", "{}"))
            return {**result, "model": f"ollama/{OLLAMA_MODEL}", "source": "edge"}
        except Exception as e:
            log.error("Ollama analysis failed: %s", e)
            return {
                "severity": "P3",
                "proposed_action": "manual review — Ollama unavailable",
                "confidence": 0.0,
                "source": "edge_fallback",
            }


async def analyze_local_with_retry(incident: str, max_attempts: int = 3) -> dict:
    """Analyze with Ollama, retrying with stricter JSON instructions on parse failure."""
    base_prompt = (
        f"SRE incident: {incident}\n"
        f"Classify severity P1-P4 and propose one remediation action.\n"
    )
    for attempt in range(max_attempts):
        if attempt == 0:
            json_hint = 'Return JSON: {"severity":"P1","proposed_action":"...","confidence":0.8}'
        elif attempt == 1:
            json_hint = (
                'IMPORTANT: Return ONLY valid JSON. No text before or after.\n'
                'Format: {"severity":"P1","proposed_action":"...","confidence":0.8}'
            )
        else:
            json_hint = (
                '{"severity":"P1","proposed_action":"restart the pod","confidence":0.8}\n'
                'Output EXACTLY that format with real values for this incident.'
            )
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": base_prompt + json_hint,
                        "stream": False,
                        "format": "json",
                    },
                )
                data = resp.json()
                result = json.loads(data.get("response", "{}"))
                return {**result, "model": f"ollama/{OLLAMA_MODEL}", "source": "edge", "attempts": attempt + 1}
        except Exception as e:
            log.warning("Attempt %d failed: %s", attempt + 1, e)

    return {
        "severity": "P3",
        "proposed_action": "manual review — all Ollama retries failed",
        "confidence": 0.0,
        "source": "edge_fallback",
        "attempts": max_attempts,
    }


async def queue_for_sync(incident: str, local_result: dict) -> None:
    """Store the incident and local result for later sync to central."""
    entry = {
        "timestamp": time.time(),
        "incident": incident,
        "local_result": local_result,
    }
    queue_path = _queue_path()
    with open(queue_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    log.info("Queued for sync: %s", incident[:60])


async def sync_to_central() -> int:
    """Send offline queue to central AOIS when connectivity returns."""
    if not CENTRAL_SYNC_URL:
        log.warning("AOIS_CENTRAL_URL not set — cannot sync")
        return 0

    queue_path = _queue_path()
    if not queue_path.exists():
        return 0

    raw = queue_path.read_text().strip()
    if not raw:
        return 0

    queue = [line for line in raw.split("\n") if line.strip()]
    synced = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for line in queue:
            try:
                entry = json.loads(line)
                await client.post(f"{CENTRAL_SYNC_URL}/api/edge_sync", json=entry)
                synced += 1
            except Exception as e:
                log.warning("Sync failed at entry %d: %s", synced + 1, e)
                break  # stop on first failure — connectivity may be gone again

    if synced == len(queue):
        queue_path.unlink()
        log.info("Sync complete — %d entries uploaded, queue cleared", synced)
    else:
        remaining = queue[synced:]
        queue_path.write_text("\n".join(remaining) + "\n")
        log.info("Partial sync — %d/%d entries uploaded", synced, len(queue))

    return synced


async def edge_analyze(incident: str) -> dict:
    """Main edge entry point: analyze locally with retry, queue for sync."""
    result = await analyze_local_with_retry(incident)
    await queue_for_sync(incident, result)
    return result


async def connectivity_check() -> bool:
    """Return True if central AOIS is reachable."""
    if not CENTRAL_SYNC_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{CENTRAL_SYNC_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def edge_loop(poll_interval: int = 30) -> None:
    """Continuous edge loop: analyze incoming incidents, sync when online."""
    log.info("Edge AOIS loop started. Ollama: %s, Model: %s", OLLAMA_URL, OLLAMA_MODEL)
    while True:
        online = await connectivity_check()
        queue_path = _queue_path()
        if online and queue_path.exists():
            synced = await sync_to_central()
            log.info("Auto-sync: %d incidents uploaded to central", synced)
        await asyncio.sleep(poll_interval)
