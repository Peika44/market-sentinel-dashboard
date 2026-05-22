from __future__ import annotations

import json
import logging
from typing import Any

from redis import Redis

logger = logging.getLogger("market_sentinel_cache")


class RedisCache:
    def __init__(self, redis_url: str) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)

    def get_json(self, key: str) -> Any | None:
        value = self._client.get(key)
        if value is None:
            logger.info("cache MISS %s", key)
            return None
        logger.info("cache HIT %s", key)
        return json.loads(value)

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._client.setex(key, ttl_seconds, json.dumps(value))
        logger.info("cache SET %s ttl=%ss", key, ttl_seconds)

    def ping(self) -> bool:
        return bool(self._client.ping())
