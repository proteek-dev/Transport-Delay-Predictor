from __future__ import annotations

from typing import Any

import orjson

from app.core.redis import get_redis


def _dumps(value: Any) -> str:
    return orjson.dumps(value).decode("utf-8")


def _loads(value: str | None) -> Any | None:
    if value is None:
        return None
    return orjson.loads(value)


async def get_json(key: str) -> Any | None:
    raw = await get_redis().get(key)
    return _loads(raw)


async def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    await get_redis().set(key, _dumps(value), ex=ttl_seconds)


async def delete(*keys: str) -> None:
    if keys:
        await get_redis().delete(*keys)
