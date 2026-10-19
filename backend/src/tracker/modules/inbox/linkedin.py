"""Mensagens do LinkedIn lidas pelo agente (somente leitura, RF-ACO-09)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import settings_store
from tracker.integrations.claude.client import AIError, get_ai, sessionmaker_from
from tracker.integrations.google.gmail import ParsedEmail
from tracker.modules.applications import service as app_service
from tracker.modules.calendar import service as cal
from tracker.modules.inbox import service as inbox
from tracker.modules.inbox.models import LinkedinMessage
from tracker.modules.notifications.service import notify


async def process_linkedin_messages(session: AsyncSession, messages: list[dict[str, Any]]) -> int:
    processed = 0
    ai = get_ai(sessionmaker_from(session))
    cfg = await settings_store.get(session, "inbox")
    for m in messages:
        if await session.scalar(select(LinkedinMessage.id).where(LinkedinMessage.message_id == str(m["message_id"]))):
            continue
        received = datetime.fromisoformat(m["received_at"]) if m.get("received_at") else datetime.now(UTC)
        row = LinkedinMessage(
            conversation_id=str(m.get("conversation_id", "")),
            message_id=str(m["message_id"]),
            from_name=m.get("from_name") or "",
            from_profile_url=m.get("from_profile_url"),
            text=m.get("text") or "",
            received_at=received,
        )
        session.add(row)
        await session.flush()
        fake = ParsedEmail(
            gmail_id=f"li-{row.message_id}",
            thread_id=f"li-{row.conversation_id}",
            from_addr=row.from_profile_url or "linkedin",
            from_name=row.from_name,
            to_addrs=[],
            subject="Mensagem no LinkedIn",
            snippet=row.text[:200],
            body_text=row.text,
            received_at=received,
        )
        candidates = await inbox.candidate_applications(session, fake)
        try:
            result = await inbox.classify(ai, fake, candidates)
        except AIError:
            continue
        row.classification, row.classification_confidence = result.label, result.confidence
        row.extracted = result.extracted.model_dump() | {"summary": result.summary}
        processed += 1
        match = {str(a.id): (a, j, c) for a, j, c in candidates}.get(result.application_match or "")
        if match and result.confidence >= cfg["min_confidence"]:
            app, job, comp = match
            row.application_id, row.link_status = app.id, "auto"
            await app_service.add_event(
                session,
                app,
                "message_in",
                {"linkedin_message_id": str(row.id), "label": result.label, "summary": result.summary},
            )
            person = await inbox.upsert_person(session, row.from_name, None, None, comp, app, "recruiter")
            person.linkedin_url = person.linkedin_url or row.from_profile_url
            row.person_id = person.id
            status = inbox.LABEL_TO_STATUS.get(result.label)
            if status and status != app.status:
                try:
                    await app_service.transition(session, app, status, reason=f"LinkedIn: {result.summary}")
                except Exception:  # noqa: S110
                    pass
            if result.label == "convite_entrevista" and result.extracted.datetimes:
                start = inbox._parse_dt(result.extracted.datetimes[0].start)
                if start:
                    await cal.create_event(
                        session,
                        application_id=app.id,
                        kind="interview",
                        title=f"Entrevista: {comp.name} ({job.title})",
                        start=start,
                        end=start + timedelta(minutes=result.extracted.duration_min or 60),
                        description=result.summary,
                        link=result.extracted.meeting_link,
                        draft=True,
                    )
            if result.label in inbox.NOTIFY:
                await notify(
                    session,
                    inbox.NOTIFY[result.label],
                    {"company": comp.name, "title": job.title, "message": f"LinkedIn: {result.summary}"},
                )
        elif result.label == "recrutador_prospeccao":
            await notify(session, "top_job", {"message": f"Recrutador no LinkedIn ({row.from_name}): {result.summary}"})
        else:
            row.link_status = "ambiguous" if result.label != "irrelevante" else "none"
    return processed
