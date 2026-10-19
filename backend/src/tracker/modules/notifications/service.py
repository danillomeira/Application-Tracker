"""Notificações: registro no dashboard + Telegram, com horas de silêncio (RF-NOT)."""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import events, settings_store
from tracker.core.config import get_settings
from tracker.integrations import telegram
from tracker.modules.platform.models import Notification

log = logging.getLogger(__name__)

# Sempre notificam, mesmo em silêncio.
URGENT = {"agent_safety_stop", "interview_invite"}

TITLES = {
    "interview_invite": "📅 Convite de entrevista",
    "availability_request": "🗓️ Pedido de disponibilidade",
    "assessment": "🧪 Teste técnico",
    "offer": "🎉 Proposta recebida",
    "pending_question": "❓ Pergunta pendente na candidatura",
    "agent_safety_stop": "🛑 Agente parado por segurança",
    "integration_error": "⚠️ Falha de integração",
    "top_job": "⭐ Vaga de prioridade máxima",
    "watchlist_job": "👀 Vaga em empresa da watchlist",
    "dossier_ready": "📚 Dossiê pronto",
    "review_ready": "✅ Candidatura pronta para revisão",
    "followup": "📨 Sugestão de follow-up",
    "email_review": "📬 E-mail para revisar",
    "ai_budget": "💸 Orçamento de IA",
    "digest": "☀️ Resumo do dia",
    "weekly": "📊 Relatório semanal",
}


def in_quiet_hours(cfg: dict[str, Any], now: datetime | None = None) -> bool:
    tz = ZoneInfo(get_settings().user_timezone)
    now = (now or datetime.now(tz)).astimezone(tz)
    q = cfg.get("quiet_hours") or {}
    if not q:
        return False
    start = time.fromisoformat(q["start"])
    end = time.fromisoformat(q["end"])
    t = now.time()
    return (t >= start or t < end) if start > end else (start <= t < end)


def render_text(kind: str, payload: dict[str, Any]) -> str:
    title = TITLES.get(kind, kind)
    lines = [f"*{title}*"]
    for key in ("company", "title", "when", "question", "message", "reason"):
        if payload.get(key):
            lines.append(f"{payload[key]}")
    if payload.get("url"):
        lines.append(payload["url"])
    return "\n".join(lines)


async def notify(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    buttons: list[list[dict[str, str]]] | None = None,
    telegram_too: bool = True,
) -> Notification:
    """Cria a notificação web e envia ao Telegram (respeitando silêncio, exceto urgentes)."""
    n = Notification(channel="web", kind=kind, payload=payload)
    session.add(n)
    await session.flush()
    await events.apublish("notifications", "notification", {"id": str(n.id), "kind": kind, **payload})
    if not telegram_too or not await settings_store.flag(session, "telegram"):
        return n
    cfg = await settings_store.get(session, "notifications")
    if kind not in URGENT and in_quiet_hours(cfg):
        n.payload = {**payload, "telegram_deferred": True}
        return n
    try:
        chat = get_settings().telegram_allowed_chat_id or (await settings_store.get(session, "telegram_chat"))["chat_id"]
        msg_id = await telegram.send_message(render_text(kind, payload), buttons, chat_id=chat)
        if msg_id:
            n.channel = "telegram"
            n.telegram_message_id = msg_id
            n.sent_at = datetime.now(ZoneInfo("UTC"))
    except Exception as exc:  # notificação nunca derruba o fluxo
        log.warning("falha ao enviar Telegram: %s", exc)
    return n
