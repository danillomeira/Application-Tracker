"""Eventos em tempo real: Redis pub/sub → WebSocket do dashboard (docs/06 §WS)."""

from __future__ import annotations

import json
from typing import Any

import redis
import redis.asyncio as aioredis

from tracker.core.config import get_settings

CHANNEL = "tracker:events"


def _encode(channel: str, type_: str, data: dict[str, Any]) -> str:
    return json.dumps({"channel": channel, "type": type_, "data": data}, default=str)


def publish(channel: str, type_: str, data: dict[str, Any]) -> None:
    """Versão síncrona (tarefas Celery)."""
    client = redis.Redis.from_url(get_settings().redis_url)
    try:
        client.publish(CHANNEL, _encode(channel, type_, data))
    finally:
        client.close()


async def apublish(channel: str, type_: str, data: dict[str, Any]) -> None:
    client = aioredis.Redis.from_url(get_settings().redis_url)
    try:
        await client.publish(CHANNEL, _encode(channel, type_, data))
    finally:
        await client.aclose()
