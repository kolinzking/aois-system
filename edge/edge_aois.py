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
LOCAL_QUEUE_PATH = Path(os.getenv("AOIS_QUEUE_PATH", "/var/aois/offline_queue.jsonl"))
LOCAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


async def analyze_local(incident: str) -> dict:
    """Analyze using local Ollama — works offline."""
    async with httpx.AsyncClient(timeout=60) as client:
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


async def queue_for_sync(incident: str, local_result: dict) -> None:
    """Store the incident and local result for later sync to central."""
    entry = {
        "timestamp": time.time(),
        "incident": incident,
        "local_result": local_result,
    }
    with open(LOCAL_QUEUE_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    log.info("Queued for sync: %s", incident[:60])


async def sync_to_central() -> int:
    """Send offline queue to central AOIS when connectivity returns."""
    if not CENTRAL_SYNC_URL:
        log.warning("AOIS_CENTRAL_URL not set — cannot sync")
        return 0

    if not LOCAL_QUEUE_PATH.exists():
        return 0

    raw = LOCAL_QUEUE_PATH.read_text().strip()
    if not raw:
        return 0

    queue = [line for line in raw.split("\n") if line]
    synced = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for line in queue:
            try:
                entry = json.loads(line)
                await client.post(f"{CENTRAL_SYNC_URL}/api/edge_sync", json=entry)
                synced += 1
            except Exception as e:
                log.warning("Sync failed for entry: %s", e)
                break  # stop on first failure — connectivity may be gone again

    if synced == len(queue):
        LOCAL_QUEUE_PATH.unlink()
        log.info("Sync complete — %d entries uploaded, queue cleared", synced)
    else:
        # rewrite only the unsynced entries
        remaining = queue[synced:]
        LOCAL_QUEUE_PATH.write_text("\n".join(remaining) + "\n")
        log.info("Partial sync — %d/%d entries uploaded", synced, len(queue))

    return synced


async def edge_analyze(incident: str) -> dict:
    """Main edge entry point: analyze locally and queue for sync."""
    result = await analyze_local(incident)
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
        if online and LOCAL_QUEUE_PATH.exists():
            synced = await sync_to_central()
            log.info("Auto-sync: %d incidents uploaded to central", synced)
        await asyncio.sleep(poll_interval)
