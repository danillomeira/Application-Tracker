"""Bot do Telegram: vínculo, comandos e ações (RF-NOT-01..03)."""

from __future__ import annotations

import asyncio
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.api.deps import SessionDep
from tracker.core import settings_store
from tracker.core.config import get_settings
from tracker.core.security import CurrentUser
from tracker.integrations import telegram
from tracker.modules.calendar.models import CalendarEvent

log = logging.getLogger(__name__)
router = APIRouter(tags=["telegram"])


async def linked_chat(session: AsyncSession) -> int | None:
    return get_settings().telegram_allowed_chat_id or (await settings_store.get(session, "telegram_chat"))["chat_id"]


@router.post("/integrations/telegram/link")
async def create_link_code(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    code = secrets.token_hex(4)
    cfg = await settings_store.get(session, "telegram_chat")
    await settings_store.put(
        session,
        "telegram_chat",
        {**cfg, "link_code": code, "link_expires": (datetime.now(UTC) + timedelta(minutes=15)).isoformat()},
    )
    await session.commit()
    return {
        "code": code,
        "instructions": f"Envie /start {code} para o seu bot no Telegram (válido por 15 min).",
        "configured": bool(get_settings().telegram_bot_token),
    }


@router.get("/integrations/telegram/status")
async def telegram_status(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    return {"bot_configured": bool(get_settings().telegram_bot_token), "chat_linked": bool(await linked_chat(session))}


@router.post("/integrations/telegram/test")
async def telegram_test(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    chat = await linked_chat(session)
    if not chat:
        raise HTTPException(409, "Telegram não vinculado")
    mid = await telegram.send_message("✅ Teste do Application Tracker", chat_id=chat)
    return {"message_id": mid}


async def summary_today(session: AsyncSession) -> str:
    now = datetime.now(UTC)
    interviews = (
        await session.scalars(
            select(CalendarEvent)
            .where(
                CalendarEvent.kind == "interview",
                CalendarEvent.status == "confirmed",
                CalendarEvent.starts_at >= now,
                CalendarEvent.starts_at <= now + timedelta(days=2),
            )
            .order_by(CalendarEvent.starts_at)
        )
    ).all()
    from tracker.modules.analytics.dashboard import today as today_view

    data = await today_view(session, "telegram")
    labels = {
        "ambiguous_emails": "e-mail(s) para associar",
        "resumes_to_approve": "CV(s) para aprovar",
        "calendar_drafts": "evento(s) para confirmar",
        "drafts": "rascunho(s) de e-mail",
    }
    pend = [f"{n} {labels[k]}" for k, n in data["pending"].items() if n and k in labels]
    lines = ["*Hoje*"]
    lines += [
        f"📅 {e.starts_at.astimezone(__import__('zoneinfo').ZoneInfo(get_settings().user_timezone)):%d/%m %H:%M} — {e.title}"
        for e in interviews
    ] or ["Sem entrevistas nas próximas 48 h"]
    lines.append("✅ Nada pendente" if not pend else "⏳ " + " · ".join(pend))
    lines.append(f"📨 Candidaturas na semana: {data['stats']['applied_7d']} · respostas: {data['stats']['responses_7d']}")
    return "\n".join(lines)


async def handle_update(session: AsyncSession, update: dict[str, Any]) -> str | None:
    """Processa um update; retorna o texto de resposta (ou None)."""
    chat_cfg = await settings_store.get(session, "telegram_chat")
    if cb := update.get("callback_query"):  # botões antigos: só confirma
        if cb.get("id"):
            try:
                await telegram.answer_callback(cb["id"], "ok")
            except Exception:  # noqa: S110
                pass
        return None
    msg = update.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if text.startswith("/start"):
        code = text.split(maxsplit=1)[1] if " " in text else ""
        exp = chat_cfg.get("link_expires")
        if (
            code
            and chat_cfg.get("link_code")
            and hmac.compare_digest(code, chat_cfg["link_code"])
            and exp
            and datetime.fromisoformat(exp) > datetime.now(UTC)
        ):
            await settings_store.put(session, "telegram_chat", {"chat_id": chat_id, "link_code": None, "link_expires": None})
            await session.commit()
            return "✅ Telegram vinculado ao Application Tracker."
        return None  # código inválido: silêncio (não revela o bot)
    if chat_id != await linked_chat(session):
        return None
    cmd = text.split()[0].lower() if text else ""
    if cmd in ("/hoje", "/status", "/pendentes"):
        return await summary_today(session)
    return "Comandos: /hoje (resumo do dia) · /pendentes (o que precisa de você)"


@router.post("/webhooks/telegram/{secret}")
async def telegram_webhook(
    secret: str,
    request: Request,
    session: SessionDep,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    expected = get_settings().telegram_webhook_secret
    if not hmac.compare_digest(secret, expected) or not hmac.compare_digest(x_telegram_bot_api_secret_token or "", expected):
        raise HTTPException(404)
    update = await request.json()
    reply = await handle_update(session, update)
    chat_id = (update.get("message") or {}).get("chat", {}).get("id")
    if reply and chat_id:
        await telegram.send_message(reply, chat_id=chat_id)
    return {"ok": True}


async def poll_updates(stop: asyncio.Event) -> None:
    """Modo local: busca updates por long polling (getUpdates) em vez de webhook; mesmo tratamento do webhook."""
    from tracker.core.db import get_sessionmaker

    await telegram.call("deleteWebhook", {"drop_pending_updates": False})
    offset: int | None = None
    while not stop.is_set():
        try:
            payload: dict[str, Any] = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                payload["offset"] = offset
            updates = await telegram.call("getUpdates", payload, http_timeout=35)
            for update in updates:
                offset = update["update_id"] + 1
                async with get_sessionmaker()() as session:
                    reply = await handle_update(session, update)
                chat_id = (update.get("message") or {}).get("chat", {}).get("id")
                if reply and chat_id:
                    await telegram.send_message(reply, chat_id=chat_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("telegram polling falhou; nova tentativa em 5 s")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass
