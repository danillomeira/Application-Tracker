"""Telegram Bot API (docs/07 §6). Só envia para o chat vinculado."""

from __future__ import annotations

from typing import Any

import httpx

from tracker.core.config import get_settings

API = "https://api.telegram.org/bot{token}/{method}"

_transport: httpx.AsyncBaseTransport | None = None
sent: list[dict[str, Any]] = []  # registro em memória (testes/depuração)


def set_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t


def configured() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_allowed_chat_id)


async def call(method: str, payload: dict[str, Any], http_timeout: float = 15) -> Any:
    s = get_settings()
    if not s.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")
    async with httpx.AsyncClient(timeout=http_timeout, transport=_transport) as c:
        r = await c.post(API.format(token=s.telegram_bot_token, method=method), json=payload)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data["result"]


async def send_message(text: str, buttons: list[list[dict[str, str]]] | None = None, chat_id: int | None = None) -> int | None:
    s = get_settings()
    target = chat_id or s.telegram_allowed_chat_id
    if not s.telegram_bot_token or not target:
        return None
    payload: dict[str, Any] = {
        "chat_id": target,
        "text": text[:4000],
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    sent.append(payload)
    result = await call("sendMessage", payload)
    return int(result.get("message_id", 0))


async def answer_callback(callback_id: str, text: str) -> None:
    await call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})


async def set_webhook(url: str) -> None:
    await call(
        "setWebhook",
        {
            "url": url,
            "secret_token": get_settings().telegram_webhook_secret,
            "allowed_updates": ["message", "callback_query"],
        },
    )
