"""Follow-ups (RF-ACO-08), agradecimento pós-entrevista (RF-ENT-05) e nota para recrutador (RF-REL-02)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from tracker.core import settings_store
from tracker.integrations.claude.client import AIError
from tracker.modules.applications.models import Application
from tracker.modules.companies.models import Company
from tracker.modules.inbox.drafts import ai_text, save_draft
from tracker.modules.inbox.models import Draft, EmailMessage
from tracker.modules.interviews.models import Interview
from tracker.modules.jobs.models import Job
from tracker.modules.notifications.service import notify
from tracker.modules.people.models import Person, PersonApplication
from tracker.modules.profile import service as profile_service
from tracker.workers.runtime import SM


async def _context(s: Any, app: Application) -> tuple[Job, Company, str, str]:
    job = await s.get(Job, app.job_id)
    assert job is not None
    company = await s.get(Company, job.company_id)
    assert company is not None
    _, master = await profile_service.current_master(s)
    lang = job.language if job.language in ("pt", "en") else "pt"
    return job, company, master.contact.full_name, lang


async def _recruiter_email(s: Any, app: Application) -> str | None:
    p = await s.scalar(
        select(Person)
        .join(PersonApplication, PersonApplication.person_id == Person.id)
        .where(PersonApplication.application_id == app.id, Person.email.is_not(None))
        .limit(1)
    )
    if p:
        return p.email
    e = await s.scalar(
        select(EmailMessage).where(EmailMessage.application_id == app.id).order_by(EmailMessage.received_at.desc()).limit(1)
    )
    return e.from_addr if e else None


async def suggest_followups(sm: SM, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    created = 0
    async with sm() as s:
        cfg = await settings_store.get(s, "tracking")
        cutoff = now - timedelta(days=int(cfg["followup_after_days"]))
        apps = (
            await s.scalars(
                select(Application).where(
                    Application.status.in_(["submitted", "under_review"]),
                    Application.last_activity_at < cutoff,
                    Application.submitted_at.is_not(None),
                )
            )
        ).all()
        for app in apps:
            if await s.scalar(select(Draft.id).where(Draft.application_id == app.id, Draft.kind == "followup")):
                continue
            job, company, name, lang = await _context(s, app)
            days = (now - (app.submitted_at or app.created_at)).days
            user = (
                f"Idioma: {'português' if lang == 'pt' else 'inglês'}. Candidato: {name}.\n"
                f"Empresa: {company.name}. Vaga: {job.title}. Candidatura enviada há {days} dias, sem resposta."
            )
            try:
                text = await ai_text(s, "draft.followup", user, app.id)
            except AIError:
                continue
            await save_draft(s, kind="followup", app=app, to=await _recruiter_email(s, app), subject=text.subject, body=text.body)
            app.next_action = "enviar follow-up (rascunho pronto)"
            app.next_action_at = now
            await notify(
                s,
                "followup",
                {
                    "company": company.name,
                    "title": job.title,
                    "message": f"Sem resposta há {days} dias. Rascunho de follow-up pronto.",
                },
            )
            created += 1
        await s.commit()
    return created


async def thank_you_draft(sm: SM, interview_id: str) -> str | None:
    async with sm() as s:
        iv = await s.get(Interview, uuid.UUID(interview_id))
        if iv is None:
            return None
        app = await s.get(Application, iv.application_id)
        assert app is not None
        job, company, name, lang = await _context(s, app)
        names = ", ".join(i.get("name", "") for i in iv.interviewers if i.get("name")) or "time"
        notes = (iv.post_notes or {}).get("highlights", "")
        user = (
            f"Idioma: {'português' if lang == 'pt' else 'inglês'}. Candidato: {name}.\n"
            f"Empresa: {company.name}. Vaga: {job.title}. Etapa: {iv.kind}. Entrevistadores: {names}.\n"
            f"Pontos marcantes da conversa (do candidato): {notes}"
        )
        text = await ai_text(s, "draft.thank_you", user, app.id)
        d = await save_draft(
            s, kind="thank_you", app=app, to=await _recruiter_email(s, app), subject=text.subject, body=text.body
        )
        iv.thank_you_draft_id = d.id
        await s.commit()
        return str(d.id)


async def recruiter_note(sm: SM, application_id: str, person_id: str | None = None) -> str:
    """Convite de conexão/mensagem curta ao recrutador ou gestor (≤ 300 caracteres)."""
    async with sm() as s:
        app = await s.get(Application, uuid.UUID(application_id))
        assert app is not None
        job, company, name, lang = await _context(s, app)
        person = await s.get(Person, uuid.UUID(person_id)) if person_id else None
        who = person.full_name if person else (job.recruiter or {}).get("name", "recrutador(a)")
        user = (
            f"Idioma: {'português' if lang == 'pt' else 'inglês'}. Candidato: {name}.\n"
            f"Destinatário: {who} ({person.role if person and person.role else 'recrutamento'}) na {company.name}.\n"
            f"Vaga: {job.title}. Requisitos: {', '.join((job.requirements or {}).get('must', [])[:6])}."
        )
        text = await ai_text(s, "draft.linkedin_note", user, app.id)
        d = await save_draft(
            s, kind="linkedin_note", app=app, to=who, subject=None, body=text.body[:300], meta={"person_id": person_id}
        )
        await s.commit()
        return str(d.id)
