"""Rotas de candidaturas, fila de revisão e perguntas pendentes (docs/06 §Candidaturas)."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, select

from tracker.api.deps import SessionDep, get_or_404
from tracker.core.security import CurrentUser
from tracker.core.tasks import dispatch
from tracker.modules.applications import service, state_machine
from tracker.modules.applications.models import (
    Application,
    ApplicationAnswer,
    ApplicationEvent,
    PendingQuestion,
)
from tracker.modules.applications.schemas import (
    AnswerOut,
    ApplicationDetail,
    ApplicationOut,
    ApplicationPatch,
    EventOut,
    ManualApplicationIn,
    NoteIn,
)
from tracker.modules.calendar.models import CalendarEvent
from tracker.modules.companies.models import Company
from tracker.modules.inbox.models import Draft, EmailMessage
from tracker.modules.interviews.models import Interview
from tracker.modules.jobs import service as job_service
from tracker.modules.jobs.models import Job
from tracker.modules.jobs.normalize import RawJob
from tracker.modules.people.models import Person, PersonApplication
from tracker.modules.resumes import service as resume_service
from tracker.modules.scoring.models import JobScore

router = APIRouter(prefix="/applications", tags=["applications"])


def _base_stmt():
    return (
        select(Application, Job, Company, JobScore)
        .join(Job, Job.id == Application.job_id)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(JobScore, and_(JobScore.job_id == Job.id, JobScore.is_current.is_(True)))
    )


def _out(app: Application, job: Job, company: Company, score: JobScore | None, cls: type[ApplicationOut] = ApplicationOut) -> Any:
    o = cls.model_validate(app)
    o.job_title, o.company_name, o.company_id = job.title, company.name, company.id
    o.quadrant = score.quadrant if score else None
    o.apply_kind, o.ats_kind = job.apply_kind, job.ats_kind
    return o


@router.get("", response_model=list[ApplicationOut])
async def list_applications(
    session: SessionDep,
    _user: CurrentUser,
    status: list[str] | None = None,
    q: str | None = None,
    include_closed: bool = True,
    limit: int = 300,
) -> list[ApplicationOut]:
    stmt = _base_stmt()
    if status:
        stmt = stmt.where(Application.status.in_(status))
    elif not include_closed:
        stmt = stmt.where(Application.status.in_(state_machine.ACTIVE))
    if q:
        stmt = stmt.where(Job.title.ilike(f"%{q}%") | Company.name.ilike(f"%{q}%"))
    rows = (await session.execute(stmt.order_by(Application.last_activity_at.desc()).limit(min(limit, 500)))).all()
    return [_out(*r) for r in rows]


@router.get("/statuses")
async def statuses(_user: CurrentUser) -> dict[str, Any]:
    return {
        "statuses": state_machine.STATUSES,
        "transitions": {k: sorted(v) for k, v in state_machine.TRANSITIONS.items()},
    }


@router.get("/{app_id}", response_model=ApplicationDetail)
async def get_application(app_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> ApplicationDetail:
    row = (await session.execute(_base_stmt().where(Application.id == app_id))).first()
    if row is None:
        raise HTTPException(404, "candidatura não encontrada")
    out: ApplicationDetail = _out(*row, cls=ApplicationDetail)
    out.timeline = [
        EventOut.model_validate(e)
        for e in (
            await session.scalars(
                select(ApplicationEvent).where(ApplicationEvent.application_id == app_id).order_by(ApplicationEvent.occurred_at)
            )
        ).all()
    ]
    out.answers = [
        AnswerOut.model_validate(a)
        for a in (
            await session.scalars(
                select(ApplicationAnswer)
                .where(ApplicationAnswer.application_id == app_id)
                .order_by(ApplicationAnswer.step_index, ApplicationAnswer.created_at)
            )
        ).all()
    ]
    out.emails = [
        {
            "id": str(e.id),
            "subject": e.subject,
            "from": e.from_addr,
            "received_at": e.received_at.isoformat(),
            "classification": e.classification,
            "snippet": e.snippet,
        }
        for e in (
            await session.scalars(
                select(EmailMessage).where(EmailMessage.application_id == app_id).order_by(EmailMessage.received_at)
            )
        ).all()
    ]
    out.events_calendar = [
        {
            "id": str(c.id),
            "kind": c.kind,
            "title": c.title,
            "starts_at": c.starts_at.isoformat(),
            "status": c.status,
            "link": c.location_or_link,
        }
        for c in (
            await session.scalars(
                select(CalendarEvent).where(CalendarEvent.application_id == app_id).order_by(CalendarEvent.starts_at)
            )
        ).all()
    ]
    out.interviews = [
        {
            "id": str(i.id),
            "round": i.round,
            "kind": i.kind,
            "starts_at": i.starts_at.isoformat() if i.starts_at else None,
        }
        for i in (
            await session.scalars(select(Interview).where(Interview.application_id == app_id).order_by(Interview.round))
        ).all()
    ]
    out.drafts = [
        {
            "id": str(d.id),
            "kind": d.kind,
            "subject": d.subject,
            "status": d.status,
            "created_at": d.created_at.isoformat(),
        }
        for d in (
            await session.scalars(select(Draft).where(Draft.application_id == app_id).order_by(Draft.created_at.desc()))
        ).all()
    ]
    out.pending_questions = [
        {"id": str(p.id), "question": p.question_text, "status": p.status}
        for p in (await session.scalars(select(PendingQuestion).where(PendingQuestion.application_id == app_id))).all()
    ]
    out.people = [
        {"id": str(p.id), "name": p.full_name, "role": p.role, "relation": pa.relation}
        for pa, p in (
            await session.execute(
                select(PersonApplication, Person)
                .join(Person, Person.id == PersonApplication.person_id)
                .where(PersonApplication.application_id == app_id)
            )
        ).all()
    ]
    return out


@router.patch("/{app_id}", response_model=ApplicationOut)
async def patch_application(app_id: uuid.UUID, body: ApplicationPatch, session: SessionDep, _user: CurrentUser) -> ApplicationOut:
    app = await get_or_404(session, Application, app_id)
    if body.status and body.status != app.status:
        try:
            await service.transition(session, app, body.status, actor="user", reason=body.reason)
        except state_machine.InvalidTransition as exc:
            raise HTTPException(422, str(exc)) from exc
    for field in ("notes", "next_action", "next_action_at", "resume_variant_id"):
        v = getattr(body, field)
        if v is not None:
            setattr(app, field, v)
    await session.commit()
    row = (await session.execute(_base_stmt().where(Application.id == app_id))).first()
    assert row is not None
    return _out(*row)


@router.post("/{app_id}/notes", response_model=EventOut, status_code=201)
async def add_note(app_id: uuid.UUID, body: NoteIn, session: SessionDep, _user: CurrentUser) -> ApplicationEvent:
    app = await get_or_404(session, Application, app_id)
    ev = await service.add_event(session, app, "note", {"text": body.text}, actor="user")
    await session.commit()
    return ev


@router.post("/{app_id}/prepare", status_code=202)
async def prepare(app_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> dict[str, str]:
    await get_or_404(session, Application, app_id)
    dispatch("applications.prepare", application_id=str(app_id))
    return {"status": "queued"}


@router.post("/{app_id}/submitted", response_model=ApplicationOut)
async def mark_submitted(app_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> ApplicationOut:
    """Botão "Já me candidatei" (RF-EXT-04)."""
    app = await get_or_404(session, Application, app_id)
    await service.register_submission(session, app, actor="user", channel=None)
    await session.commit()
    row = (await session.execute(_base_stmt().where(Application.id == app_id))).first()
    assert row is not None
    return _out(*row)


@router.post("/manual", response_model=ApplicationOut, status_code=201)
async def manual(body: ManualApplicationIn, session: SessionDep, _user: CurrentUser) -> ApplicationOut:
    """Registra candidatura feita manualmente (para vaga existente ou nova)."""
    if body.job_id:
        job = await get_or_404(session, Job, body.job_id)
    else:
        if not (body.company_name and body.title):
            raise HTTPException(422, "informe job_id ou company_name + title")
        ext = hashlib.sha256(f"{body.url}|{body.company_name}|{body.title}".encode()).hexdigest()[:24]
        job, _ = await job_service.upsert_job(
            session,
            RawJob(
                source="manual",
                external_id=ext,
                title=body.title,
                company_name=body.company_name,
                url=body.url,
                description_text=body.description or "",
                apply_url=body.url,
            ),
        )
        dispatch("ai.process_job", job_id=str(job.id))
    app = await service.get_for_job(session, job.id) or await service.create_for_job(
        session, job, channel=body.channel, mode="manual", actor="user"
    )
    app.mode = "manual"
    if body.resume_variant_id:
        app.resume_variant_id = body.resume_variant_id
        r = await resume_service.latest_render(session, body.resume_variant_id)
        app.resume_render_id = r.id if r else None
    if body.notes:
        app.notes = body.notes
    await service.register_submission(session, app, actor="user", channel=body.channel, submitted_at=body.submitted_at)
    await session.commit()
    row = (await session.execute(_base_stmt().where(Application.id == app.id))).first()
    assert row is not None
    return _out(*row)
