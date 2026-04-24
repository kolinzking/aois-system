import hashlib
import json
import os

import redis.asyncio as aioredis

_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))


def _cache_key(model: str, system: str, user: str) -> str:
    payload = json.dumps({"model": model, "system": system, "user": user}, sort_keys=True)
    return "aois:cache:" + hashlib.sha256(payload.encode()).hexdigest()


async def get_cached(redis: aioredis.Redis, model: str, system: str, user: str) -> str | None:
    return await redis.get(_cache_key(model, system, user))


async def set_cached(redis: aioredis.Redis, model: str, system: str, user: str,
                     response: str) -> None:
    await redis.setex(_cache_key(model, system, user), _TTL_SECONDS, response)


async def cache_stats(redis: aioredis.Redis) -> dict:
    keys = await redis.keys("aois:cache:*")
    return {"cached_responses": len(keys), "ttl_seconds": _TTL_SECONDS}
