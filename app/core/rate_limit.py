from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Final

from redis.asyncio import Redis

from app.core.config import settings

_redis_client: Redis | None = None
_inmemory_lock = asyncio.Lock()
_inmemory_counters: dict[str, tuple[int, float]] = {}
_DEFAULT_TTL: Final[int] = 60


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def rate_limit_hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    try:
        redis = get_redis()
        value = await redis.incr(key)
        if value == 1:
            await redis.expire(key, window_seconds)
        ttl = await redis.ttl(key)
        allowed = value <= limit
        return allowed, ttl if ttl > 0 else window_seconds
    except Exception:
        if not settings.allow_inmemory_rate_limit_fallback:
            raise
        return await _rate_limit_hit_memory(key, limit, window_seconds)


async def _rate_limit_hit_memory(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    now = datetime.now(UTC).timestamp()
    ttl = window_seconds if window_seconds > 0 else _DEFAULT_TTL
    async with _inmemory_lock:
        current_value, expires_at = _inmemory_counters.get(key, (0, 0))
        if now >= expires_at:
            current_value = 0
            expires_at = now + ttl
        current_value += 1
        _inmemory_counters[key] = (current_value, expires_at)
        remaining_ttl = int(max(expires_at - now, 0))
        return current_value <= limit, remaining_ttl


def window_range(window_unit: str, window_size: int) -> tuple[datetime, datetime]:
    start = datetime.now(UTC)
    if window_unit == "day":
        end = start + timedelta(days=window_size)
    elif window_unit == "week":
        end = start + timedelta(weeks=window_size)
    elif window_unit == "month":
        end = start + timedelta(days=30 * window_size)
    else:
        end = start + timedelta(days=window_size)
    return start, end
