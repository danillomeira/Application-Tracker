"""Tela "Hoje" (RF-DSH-01)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import and_, func, select

from tracker.api.deps import SessionDep
from tracker.core.security import CurrentUser
from tracker.modules.applications.models import Application, DailyQuota
from tracker.modules.calendar.models import CalendarEvent
from tracker.modules.companies.models import Company
from tracker.modules.inbox.models import Draft, EmailMessage
from tracker.modules.jobs.models import Job
from tracker.modules.platform.models import BrowserSessionMeta, IntegrationState
from tracker.modules.profile.models import MasterProfileVersion
from tracker.modules.resumes.models import ResumeVariant
from tracker.modules.scoring.models import JobScore

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/today")
async def today(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    now = datetime.now(UTC)
    week = now + timedelta(days=7)
    interviews = (
        await session.execute(
            select(CalendarEvent, Job, Company)
            .join(Application, Application.id == CalendarEvent.application_id)
            .join(Job, Job.id == Application.job_id)
            .join(Company, Company.id == Job.company_id)
            .where(
                CalendarEvent.kind == "interview",
                CalendarEvent.status != "cancelled",
                CalendarEvent.starts_at >= now - timedelta(hours=2),
                CalendarEvent.starts_at <= week,
            )
            .order_by(CalendarEvent.starts_at)
        )
    ).all()
    deadlines = (
        (
            await session.execute(
                select(CalendarEvent).where(
                    CalendarEvent.kind == "assessment_deadline",
                    CalendarEvent.status != "cancelled",
                    CalendarEvent.starts_at >= now,
                    CalendarEvent.starts_at <= week,
                )
            )
        )
        .scalars()
        .all()
    )

    async def count(stmt: Any) -> int:
        return int(await session.scalar(stmt) or 0)

    pending = {
        "ambiguous_emails": await count(
            select(func.count()).select_from(EmailMessage).where(EmailMessage.link_status == "ambiguous")
        ),
        "calendar_drafts": await count(select(func.count()).select_from(CalendarEvent).where(CalendarEvent.status == "draft")),
        "resumes_to_approve": await count(
            select(func.count())
            .select_from(ResumeVariant)
            .where(ResumeVariant.kind == "tailored", ResumeVariant.status == "draft")
        ),
        "drafts": await count(select(func.count()).select_from(Draft).where(Draft.status == "proposed")),
    }
    followups = (
        await session.execute(
            select(Application, Job, Company)
            .join(Job, Job.id == Application.job_id)
            .join(Company, Company.id == Job.company_id)
            .where(Application.next_action_at.is_not(None), Application.next_action_at <= now + timedelta(days=1))
            .order_by(Application.next_action_at)
            .limit(20)
        )
    ).all()
    top_jobs = (
        await session.execute(
            select(Job, Company, JobScore)
            .join(Company, Company.id == Job.company_id)
            .join(JobScore, and_(JobScore.job_id == Job.id, JobScore.is_current.is_(True)))
            .where(Job.status == "open", Job.triage == "new", JobScore.quadrant.in_(["top", "bet"]))
            .order_by(JobScore.priority.desc())
            .limit(8)
        )
    ).all()
    quota = await session.scalar(select(DailyQuota).where(DailyQuota.day == date.today(), DailyQuota.kind == "easy_apply"))
    agent_meta = await session.scalar(select(BrowserSessionMeta).where(BrowserSessionMeta.site == "linkedin"))
    week_ago = now - timedelta(days=7)
    stats = {
        "applied_7d": await count(select(func.count()).select_from(Application).where(Application.submitted_at >= week_ago)),
        "responses_7d": await count(
            select(func.count())
            .select_from(EmailMessage)
            .where(
                EmailMessage.received_at >= week_ago,
                EmailMessage.application_id.is_not(None),
                EmailMessage.classification.in_(
                    ["convite_entrevista", "pedido_disponibilidade", "teste_tecnico", "oferta", "rejeicao"]
                ),
            )
        ),
        "new_jobs_7d": await count(select(func.count()).select_from(Job).where(Job.first_seen_at >= week_ago)),
    }
    integrations = (await session.scalars(select(IntegrationState).where(IntegrationState.consecutive_errors > 0))).all()
    has_master = await session.scalar(select(MasterProfileVersion.id).limit(1)) is not None
    return {
        "onboarding_needed": not has_master,
        "interviews": [
            {
                "event_id": str(e.id),
                "application_id": str(e.application_id),
                "title": e.title,
                "company": c.name,
                "job_title": j.title,
                "starts_at": e.starts_at.isoformat(),
                "link": e.location_or_link,
                "status": e.status,
            }
            for e, j, c in interviews
        ],
        "deadlines": [
            {
                "event_id": str(d.id),
                "title": d.title,
                "starts_at": d.starts_at.isoformat(),
                "application_id": str(d.application_id) if d.application_id else None,
            }
            for d in deadlines
        ],
        "pending": pending,
        "followups": [
            {
                "application_id": str(a.id),
                "company": c.name,
                "job_title": j.title,
                "next_action": a.next_action,
                "next_action_at": a.next_action_at.isoformat() if a.next_action_at else None,
            }
            for a, j, c in followups
        ],
        "top_jobs": [
            {
                "job_id": str(j.id),
                "title": j.title,
                "company": c.name,
                "quadrant": s.quadrant,
                "chance": s.chance,
                "attractiveness": s.attractiveness,
                "action": s.suggested_action,
            }
            for j, c, s in top_jobs
        ],
        "quota": {"used": quota.used if quota else 0, "limit": quota.limit if quota else 20},
        "agent": {
            "paused_until": agent_meta.paused_until.isoformat() if agent_meta and agent_meta.paused_until else None,
            "last_safety_stop_at": agent_meta.last_safety_stop_at.isoformat()
            if agent_meta and agent_meta.last_safety_stop_at
            else None,
        },
        "stats": stats,
        "integration_errors": [{"name": i.name, "error": i.last_error} for i in integrations],
    }
