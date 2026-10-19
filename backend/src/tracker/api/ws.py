"""WebSocket do dashboard: repassa eventos do Redis pub/sub (docs/06 §WS)."""

from __future__ import annotations

import asyncio
import contextlib
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tracker.core.config import get_settings
from tracker.core.events import CHANNEL
from tracker.core.security import ws_user

router = APIRouter()


@router.websocket("/ws")
async def dashboard_ws(websocket: WebSocket) -> None:
    if ws_user(websocket) is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    channels: set[str] | None = None  # None = todos
    client = aioredis.Redis.from_url(get_settings().redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(CHANNEL)

    async def pump() -> None:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            raw = msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]
            event = json.loads(raw)
            if channels is None or event.get("channel") in channels:
                await websocket.send_text(raw)

    task = asyncio.create_task(pump())
    try:
        while True:
            data = json.loads(await websocket.receive_text())
            if data.get("action") == "subscribe":
                channels = set(data.get("channels") or []) or None
            elif data.get("action") == "ping":
                await websocket.send_text(json.dumps({"channel": "system", "type": "pong", "data": {}}))
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.aclose()
        await client.aclose()
