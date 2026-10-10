"""Redis-backed session memory + HITL pending state."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis = None
_redis_failed = False


async def get_redis():
    global _redis, _redis_failed
    if _redis_failed:
        return None
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as redis

        settings = get_settings()
        client = redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        _redis = client
        logger.info("redis_connected", extra={"url": settings.redis_url})
        return _redis
    except Exception as e:
        logger.warning("redis_unavailable fallback_to_memory: %s", e)
        _redis_failed = True
        return None


async def redis_set_json(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    client = await get_redis()
    if not client:
        return False
    settings = get_settings()
    ttl = ttl if ttl is not None else settings.redis_session_ttl_seconds
    await client.set(key, json.dumps(value, default=str), ex=ttl)
    return True


async def redis_get_json(key: str) -> Optional[Any]:
    client = await get_redis()
    if not client:
        return None
    raw = await client.get(key)
    if not raw:
        return None
    return json.loads(raw)


async def redis_delete(key: str) -> None:
    client = await get_redis()
    if client:
        await client.delete(key)
