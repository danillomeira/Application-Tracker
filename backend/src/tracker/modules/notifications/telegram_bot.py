"""Bot do Telegram: vínculo, comandos e ações (RF-NOT-01..03)."""

from __future__ import annotations

import asyncio
import hmac
import logging
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.api.deps import SessionDep
from tracker.core import settings_store
from tracker.core.config import get_settings
from tracker.core.security import CurrentUser
from tracker.integrations import telegram
from tracker.modules.agent_gateway import control
from tracker.modules.agent_gateway.models import AgentJob
from tracker.modules.applications.models import Application, DailyQuota, PendingQuestion
from tracker.modules.calendar.models import CalendarEvent
from tracker.modules.platform.models import Notification

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


def _pending_buttons(pq: PendingQuestion) -> list[list[dict[str, str]]] | None:
    if not pq.options or len(pq.options) > 6:
        return None
    return [[{"text": str(o)[:40], "callback_data": f"pq:{pq.id}:{i}"}] for i, o in enumerate(pq.options)]


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
    pending = await session.scalar(select(func.count()).select_from(PendingQuestion).where(PendingQuestion.status == "open")) or 0
    reviews = (
        await session.scalar(select(func.count()).select_from(Application).where(Application.status == "awaiting_review")) or 0
    )
    quota = await session.scalar(select(DailyQuota).where(DailyQuota.day == date.today(), DailyQuota.kind == "easy_apply"))
    lines = ["*Hoje*"]
    lines += [
        f"📅 {e.starts_at.astimezone(__import__('zoneinfo').ZoneInfo(get_settings().user_timezone)):%d/%m %H:%M} — {e.title}"
        for e in interviews
    ] or ["Sem entrevistas nas próximas 48 h"]
    lines.append(f"❓ {pending} perguntas pendentes · ✅ {reviews} candidaturas para revisar")
    lines.append(f"📨 Easy Apply hoje: {quota.used if quota else 0}")
    return "\n".join(lines)


async def handle_update(session: AsyncSession, update: dict[str, Any]) -> str | None:
    """Processa um update; retorna o texto de resposta (ou None)."""
    from tracker.modules.applications.router import PendingAnswerIn, answer_pending

    chat_cfg = await settings_store.get(session, "telegram_chat")
    if cb := update.get("callback_query"):
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        if chat_id != await linked_chat(session):
            return None
        data = cb.get("data", "")
        reply = "ok"
        if data.startswith("pq:"):
            _, pq_id, idx = data.split(":")
            pq = await session.get(PendingQuestion, uuid.UUID(pq_id))
            if pq and pq.status == "open":
                value = pq.options[int(idx)]
                await answer_pending(session, pq, PendingAnswerIn(value=value), actor="user")
                reply = f"Resposta salva: {value}"
            else:
                reply = "Pergunta já respondida"
        elif data.startswith("ap:"):
            from tracker.modules.applications.router import BulkIds, approve_reviews

            await approve_reviews(BulkIds(ids=[uuid.UUID(data[3:])]), session, "telegram")  # type: ignore[arg-type]
            reply = "Candidatura aprovada"
        elif data == "kill":
            await control.kill(session, "user", "Telegram")
            reply = "Agente parado"
        await session.commit()
        if cb.get("id"):
            try:
                await telegram.answer_callback(cb["id"], reply)
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
    reply_to = (msg.get("reply_to_message") or {}).get("message_id")
    if reply_to:
        n = await session.scalar(select(Notification).where(Notification.telegram_message_id == reply_to))
        pq_id = (n.payload or {}).get("pending_question_id") if n else None
        if pq_id:
            pq = await session.get(PendingQuestion, uuid.UUID(pq_id))
            if pq and pq.status == "open":
                await answer_pending(session, pq, PendingAnswerIn(value=text), actor="user")
                await session.commit()
                return "Resposta salva no banco de respostas."
    cmd = text.split()[0].lower() if text else ""
    if cmd == "/stop":
        n = await control.kill(session, "user", "Telegram /stop")
        await session.commit()
        return f"🛑 Agente parado ({n} tarefa(s) interrompida(s)). Use /retomar para liberar."
    if cmd == "/retomar":
        await control.resume(session, "user")
        await session.commit()
        return "▶️ Agente liberado."
    if cmd in ("/hoje", "/status"):
        txt = await summary_today(session)
        if cmd == "/status":
            blocked = await control.is_blocked(session)
            running = await session.scalar(select(AgentJob).where(AgentJob.status.in_(["leased", "running"])).limit(1))
            txt += f"\n🤖 Agente: {blocked or ('trabalhando' if running else 'ocioso')}"
        return txt
    if cmd == "/fila":
        jobs = (
            await session.scalars(
                select(AgentJob).where(AgentJob.status == "pending").order_by(AgentJob.priority.desc()).limit(5)
            )
        ).all()
        return "\n".join(f"{i + 1}. {j.kind} ({j.payload.get('job_id', '')[:8]})" for i, j in enumerate(jobs)) or "Fila vazia"
    if cmd == "/pendentes":
        pqs = (await session.scalars(select(PendingQuestion).where(PendingQuestion.status == "open").limit(5))).all()
        for pq in pqs:
            mid = await telegram.send_message(f"❓ {pq.question_text}", _pending_buttons(pq), chat_id=chat_id)
            session.add(
                Notification(
                    channel="telegram",
                    kind="pending_question",
                    telegram_message_id=mid,
                    payload={"pending_question_id": str(pq.id)},
                    sent_at=datetime.now(UTC),
                )
            )
        await session.commit()
        return None if pqs else "Nenhuma pergunta pendente 🎉"
    return "Comandos: /hoje /status /fila /pendentes /stop /retomar"


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
