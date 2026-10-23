"""Rascunhos gerados (e-mail/LinkedIn). NUNCA enviados pelo sistema (ADR-009)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import events
from tracker.core.humanize import humanize
from tracker.integrations.claude.client import AIError, AIRequest, get_ai, load_prompt, sessionmaker_from
from tracker.integrations.google import oauth
from tracker.integrations.google.gmail import Gmail
from tracker.modules.applications import service as app_service
from tracker.modules.applications.models import Application
from tracker.modules.calendar import service as cal
from tracker.modules.companies.models import Company
from tracker.modules.inbox.models import Draft, EmailMessage
from tracker.modules.inbox.schemas import DraftText
from tracker.modules.jobs.models import Job
from tracker.modules.notifications.service import notify
from tracker.modules.profile import service as profile_service

log = logging.getLogger(__name__)

WEEKDAYS_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def format_slot(s: datetime, e: datetime, lang: str) -> str:
    s, e = s.astimezone(cal.tz()), e.astimezone(cal.tz())
    if lang == "pt":
        return f"{WEEKDAYS_PT[s.weekday()]}, {s:%d/%m}, das {s:%H:%M} às {e:%H:%M} (horário de Brasília)"
    return f"{WEEKDAYS_EN[s.weekday()]}, {s:%b %d}, {s:%H:%M}–{e:%H:%M} (UTC{s:%z}, Brasília)"


def fallback_availability(name: str, slots: list[str], lang: str) -> DraftText:
    if lang == "pt":
        body = (
            "Olá,\n\nObrigado pelo contato! Tenho disponibilidade nos seguintes horários:\n\n"
            + "\n".join(f"- {s}" for s in slots)
            + f"\n\nFico à disposição.\n\nAbraço,\n{name}"
        )
        return DraftText(subject="Disponibilidade para conversa", body=body)
    body = (
        "Hi,\n\nThank you for reaching out! I'm available at the following times:\n\n"
        + "\n".join(f"- {s}" for s in slots)
        + f"\n\nLooking forward to talking.\n\nBest,\n{name}"
    )
    return DraftText(subject="Availability", body=body)


async def ai_text(session: AsyncSession, task: str, user: str, entity_id: Any = None) -> DraftText:
    out = (
        await get_ai(sessionmaker_from(session)).structured(
            AIRequest(
                task=task,
                system=load_prompt(task),
                user=user,
                effort="medium",
                max_tokens=3000,
                entity_type="application",
                entity_id=entity_id,
            ),
            DraftText,
        )
    ).output
    # texto escrito pela IA em seu nome: sem cara de IA (templates do sistema não passam por aqui)
    return out.model_copy(update={"body": humanize_body(out.body)})


def humanize_body(body: str) -> str:
    """Limpa parágrafo a parágrafo (mantém saudação, quebras de linha e assinatura)."""
    return "\n".join(humanize(line) if len(line) > 40 else line for line in body.split("\n"))


async def save_draft(
    session: AsyncSession,
    *,
    kind: str,
    app: Application | None,
    to: str | None,
    subject: str | None,
    body: str,
    in_reply_to: EmailMessage | None = None,
    meta: dict[str, Any] | None = None,
) -> Draft:
    d = Draft(
        kind=kind,
        application_id=app.id if app else None,
        to=to,
        subject=subject,
        body=body,
        in_reply_to_email_id=in_reply_to.id if in_reply_to else None,
        meta=meta or {},
    )
    session.add(d)
    await session.flush()
    if app is not None:
        await app_service.add_event(session, app, "email_draft", {"draft_id": str(d.id), "kind": kind})
    await events.apublish("inbox", "draft.created", {"draft_id": str(d.id), "kind": kind})
    return d


async def availability_draft(
    session: AsyncSession, email: EmailMessage, app: Application, company: Company, job: Job, duration_min: int = 60
) -> Draft:
    """Pedido de disponibilidade → 3 horários livres → rascunho de resposta (RF-AGE-03)."""
    _, master = await profile_service.current_master(session)
    lang = job.language if job.language in ("pt", "en") else "pt"
    slots = await cal.availability(session, duration_min=duration_min, days=7, count=3)
    slot_text = [format_slot(s, e, lang) for s, e in slots]
    user = (
        f"Idioma: {'português' if lang == 'pt' else 'inglês'}. Candidato: {master.contact.full_name}.\n"
        f"Empresa: {company.name}. Vaga: {job.title}.\nHorários livres (use exatamente estes):\n"
        + "\n".join(f"- {s}" for s in slot_text)
        + f"\n\n<email>\nDe: {email.from_name or ''} <{email.from_addr}>\nAssunto: {email.subject}\n\n"
        f"{(email.body_text or email.snippet)[:5000]}\n</email>"
    )
    try:
        text = await ai_text(session, "draft.reply", user, app.id)
    except AIError:
        text = fallback_availability(master.contact.full_name, slot_text, lang)
    subject = email.subject if email.subject.lower().startswith("re:") else f"Re: {email.subject}"
    d = await save_draft(
        session,
        kind="availability",
        app=app,
        to=email.from_addr,
        subject=subject,
        body=text.body,
        in_reply_to=email,
        meta={"slots": [[s.isoformat(), e.isoformat()] for s, e in slots]},
    )
    await notify(
        session,
        "availability_request",
        {
            "company": company.name,
            "title": job.title,
            "message": "Rascunho de resposta com 3 horários criado. Revise e envie pelo Gmail.",
            "draft_id": str(d.id),
        },
    )
    return d


async def push_to_gmail(session: AsyncSession, d: Draft) -> str:
    """Cria o rascunho no Gmail (escopo gmail.compose). O envio é sempre do usuário."""
    token = await oauth.get_access_token(session)
    thread_id = in_reply = None
    if d.in_reply_to_email_id:
        src = await session.get(EmailMessage, d.in_reply_to_email_id)
        if src:
            thread_id = src.thread_id
            in_reply = (src.extracted or {}).get("message_id_header")
    gid = await Gmail(token).create_draft(d.to or "", d.subject or "", d.body, thread_id, in_reply)
    d.gmail_draft_id = gid
    d.status = "created_in_gmail"
    return gid
