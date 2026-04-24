from datetime import date

import asyncpg
import redis.asyncio as aioredis

_DAILY_PREFIX = "aois:budget:daily"
_MONTHLY_PREFIX = "aois:budget:monthly"


def _daily_key(entity_type: str, entity_id: str) -> str:
    return f"{_DAILY_PREFIX}:{entity_type}:{entity_id}:{date.today().isoformat()}"


def _monthly_key(entity_type: str, entity_id: str) -> str:
    return f"{_MONTHLY_PREFIX}:{entity_type}:{entity_id}:{date.today().strftime('%Y-%m')}"


async def check_budget(redis: aioredis.Redis, db: asyncpg.Pool,
                       team_id: str, user_id: str) -> tuple[bool, str]:
    for entity_type, entity_id in [("team", team_id), ("user", user_id)]:
        if not entity_id:
            continue
        row = await db.fetchrow(
            "SELECT daily_limit_usd FROM budget_config WHERE entity_type=$1 AND entity_id=$2",
            entity_type, entity_id,
        )
        if not row:
            continue
        limit = float(row["daily_limit_usd"])
        spent = float(await redis.get(_daily_key(entity_type, entity_id)) or 0)
        if spent >= limit:
            return False, (
                f"{entity_type}:{entity_id} daily budget exhausted "
                f"(${spent:.4f} / ${limit:.4f})"
            )
    return True, "ok"


async def debit_budget(redis: aioredis.Redis, team_id: str, user_id: str,
                       cost_usd: float) -> None:
    for entity_type, entity_id in [("team", team_id), ("user", user_id)]:
        if not entity_id:
            continue
        dk = _daily_key(entity_type, entity_id)
        await redis.incrbyfloat(dk, cost_usd)
        await redis.expire(dk, 86400)
        mk = _monthly_key(entity_type, entity_id)
        await redis.incrbyfloat(mk, cost_usd)
        await redis.expire(mk, 32 * 86400)


async def budget_status(redis: aioredis.Redis, db: asyncpg.Pool,
                        entity_type: str, entity_id: str) -> dict:
    row = await db.fetchrow(
        "SELECT daily_limit_usd, monthly_limit_usd FROM budget_config "
        "WHERE entity_type=$1 AND entity_id=$2",
        entity_type, entity_id,
    )
    if not row:
        return {"entity": f"{entity_type}:{entity_id}", "status": "no budget configured"}
    daily_spent = float(await redis.get(_daily_key(entity_type, entity_id)) or 0)
    monthly_spent = float(await redis.get(_monthly_key(entity_type, entity_id)) or 0)
    daily_limit = float(row["daily_limit_usd"])
    monthly_limit = float(row["monthly_limit_usd"] or 0)
    return {
        "entity": f"{entity_type}:{entity_id}",
        "daily": {
            "spent": round(daily_spent, 6),
            "limit": daily_limit,
            "remaining": round(daily_limit - daily_spent, 6),
        },
        "monthly": {
            "spent": round(monthly_spent, 6),
            "limit": monthly_limit,
            "remaining": round(monthly_limit - monthly_spent, 6),
        },
    }
