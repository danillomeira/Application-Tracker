"""Rotas de entrevistas, dossiê, simulação, pós-entrevista e testes técnicos (RF-ENT)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from tracker.api.deps import SessionDep, TaskAccepted, get_or_404
from tracker.core.config import get_settings
from tracker.core.security import CurrentUser
from tracker.core.tasks import enqueue
from tracker.integrations.claude.client import sessionmaker_from
from tracker.modules.applications import service as app_service
from tracker.modules.applications.models import Application
from tracker.modules.calendar import service as cal
from tracker.modules.calendar.models import CalendarEvent
from tracker.modules.companies.models import Company
from tracker.modules.interviews import service
from tracker.modules.interviews.models import (
    Assessment,
    Interview,
    InterviewDossier,
    InterviewQuestionLog,
    MockSession,
)
from tracker.modules.interviews.schemas import (
    AssessmentIn,
    AssessmentOut,
    InterviewIn,
    InterviewOut,
    MockAnswerIn,
    MockStartIn,
    PostNotesIn,
)
from tracker.modules.jobs.models import Job

router = APIRouter(prefix="/interviews", tags=["interviews"])
mock_router = APIRouter(prefix="/mock-sessions", tags=["interviews"])
assessments_router = APIRouter(prefix="/assessments", tags=["interviews"])


async def _enrich(session: SessionDep, iv: Interview) -> InterviewOut:
    out = InterviewOut.model_validate(iv)
    app = await session.get(Application, iv.application_id)
    job = await session.get(Job, app.job_id) if app else None
    comp = await session.get(Company, job.company_id) if job else None
    out.company_name, out.job_title = (comp.name if comp else None), (job.title if job else None)
    d = await session.scalar(
        select(InterviewDossier)
        .where(InterviewDossier.application_id == iv.application_id)
        .order_by(InterviewDossier.generated_at.desc())
        .limit(1)
    )
    out.dossier_status = d.status if d else None
    ev = await session.get(CalendarEvent, iv.scheduled_event_id) if iv.scheduled_event_id else None
    out.link = ev.location_or_link if ev else None
    return out


@router.get("", response_model=list[InterviewOut])
async def list_interviews(session: SessionDep, _user: CurrentUser, upcoming: bool | None = None) -> list[InterviewOut]:
    stmt = select(Interview).order_by(Interview.starts_at.desc().nulls_last())
    now = datetime.now(UTC)
    if upcoming is True:
        stmt = select(Interview).where(Interview.starts_at >= now - timedelta(hours=2)).order_by(Interview.starts_at)
    elif upcoming is False:
        stmt = stmt.where(Interview.starts_at < now)
    return [await _enrich(session, iv) for iv in (await session.scalars(stmt.limit(200))).all()]


@router.post("", response_model=InterviewOut, status_code=201)
async def create_interview(body: InterviewIn, session: SessionDep, _user: CurrentUser) -> InterviewOut:
    app = await get_or_404(session, Application, body.application_id)
    job = await session.get(Job, app.job_id)
    assert job is not None
    comp = await session.get(Company, job.company_id)
    assert comp is not None
    rounds = len((await session.scalars(select(Interview).where(Interview.application_id == app.id))).all())
    iv = Interview(
        application_id=app.id,
        round=rounds + 1,
        kind=body.kind,
        starts_at=body.starts_at,
        interviewers=body.interviewers,
    )
    session.add(iv)
    await session.flush()
    url = f"{get_settings().app_base_url}/entrevistas/{iv.id}"
    ev = await cal.create_event(
        session,
        application_id=app.id,
        kind="interview",
        title=f"Entrevista {body.kind}: {comp.name} ({job.title})",
        start=body.starts_at,
        end=body.starts_at + timedelta(minutes=body.duration_min),
        description=f"Dossiê: {url}",
        link=body.link,
        meta={"interview_id": str(iv.id)},
    )
    iv.scheduled_event_id = ev.id
    await cal.ensure_study_block(session, ev, url)
    if app.status in ("submitted", "under_review", "ghosted", "assessment"):
        await app_service.transition(session, app, "interviewing", actor="user", reason="entrevista registrada")
    await session.commit()
    await enqueue(
        session,
        "ai.build_dossier",
        entity_type="application",
        entity_id=app.id,
        application_id=str(app.id),
        interview_id=str(iv.id),
    )
    return await _enrich(session, iv)


@router.get("/{interview_id}")
async def get_interview(interview_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    iv = await get_or_404(session, Interview, interview_id)
    d = await session.scalar(
        select(InterviewDossier)
        .where(InterviewDossier.application_id == iv.application_id)
        .order_by(InterviewDossier.generated_at.desc())
        .limit(1)
    )
    out = (await _enrich(session, iv)).model_dump(mode="json")
    out["dossier"] = (
        {
            "id": str(d.id),
            "status": d.status,
            "content": d.content,
            "sources": d.sources,
            "generated_at": d.generated_at.isoformat(),
        }
        if d
        else None
    )
    out["mock_sessions"] = [
        {"id": str(m.id), "status": m.status, "kind": m.interview_kind, "created_at": m.created_at.isoformat()}
        for m in (await session.scalars(select(MockSession).where(MockSession.application_id == iv.application_id))).all()
    ]
    return out


@router.post("/{interview_id}/dossier", response_model=TaskAccepted, status_code=202)
async def regenerate_dossier(interview_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    iv = await get_or_404(session, Interview, interview_id)
    tr = await enqueue(
        session,
        "ai.build_dossier",
        entity_type="application",
        entity_id=iv.application_id,
        application_id=str(iv.application_id),
        interview_id=str(iv.id),
    )
    return TaskAccepted(task_id=tr.id)


@router.post("/applications/{application_id}/dossier", response_model=TaskAccepted, status_code=202)
async def dossier_on_demand(application_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    await get_or_404(session, Application, application_id)
    tr = await enqueue(
        session,
        "ai.build_dossier",
        entity_type="application",
        entity_id=application_id,
        application_id=str(application_id),
    )
    return TaskAccepted(task_id=tr.id)


@router.get("/{interview_id}/cheatsheet", response_class=PlainTextResponse)
async def get_cheatsheet(interview_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> str:
    iv = await get_or_404(session, Interview, interview_id)
    d = await session.scalar(
        select(InterviewDossier)
        .where(InterviewDossier.application_id == iv.application_id, InterviewDossier.status == "ready")
        .order_by(InterviewDossier.generated_at.desc())
        .limit(1)
    )
    if d is None or not d.cheatsheet_md:
        raise HTTPException(404, "dossiê ainda não está pronto")
    return d.cheatsheet_md


@router.post("/{interview_id}/post-notes", response_model=InterviewOut)
async def post_notes(interview_id: uuid.UUID, body: PostNotesIn, session: SessionDep, _user: CurrentUser) -> InterviewOut:
    iv = await get_or_404(session, Interview, interview_id)
    app = await session.get(Application, iv.application_id)
    assert app is not None
    job = await session.get(Job, app.job_id)
    assert job is not None
    iv.post_notes = body.model_dump(exclude={"generate_thank_you", "self_rating"})
    iv.self_rating = body.self_rating
    for q in body.questions:
        session.add(InterviewQuestionLog(company_id=job.company_id, interview_id=iv.id, interview_kind=iv.kind, question=q))
    await app_service.add_event(
        session, app, "interview_notes", {"interview_id": str(iv.id), "rating": body.self_rating}, actor="user"
    )
    if body.next_steps:
        app.next_action = body.next_steps
    await session.commit()
    if body.generate_thank_you:
        await enqueue(session, "ai.thank_you", interview_id=str(iv.id))
    return await _enrich(session, iv)


# ---------- Simulação ----------
@mock_router.post("")
async def start_mock(body: MockStartIn, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    await get_or_404(session, Application, body.application_id)
    ms = MockSession(application_id=body.application_id, interview_kind=body.interview_kind)
    session.add(ms)
    await session.flush()
    turn = await service.mock_turn(session, sessionmaker_from(session), ms, None)
    await session.commit()
    return {"id": str(ms.id), "turn": turn.model_dump(), "transcript": ms.transcript}


@mock_router.post("/{mock_id}/turn")
async def mock_answer(mock_id: uuid.UUID, body: MockAnswerIn, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    ms = await get_or_404(session, MockSession, mock_id)
    if ms.status != "active":
        raise HTTPException(409, "simulação encerrada")
    turn = await service.mock_turn(session, sessionmaker_from(session), ms, body.answer)
    await session.commit()
    return {"id": str(ms.id), "turn": turn.model_dump(), "transcript": ms.transcript, "status": ms.status}


@mock_router.get("/{mock_id}")
async def get_mock(mock_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    ms = await get_or_404(session, MockSession, mock_id)
    return {
        "id": str(ms.id),
        "status": ms.status,
        "kind": ms.interview_kind,
        "transcript": ms.transcript,
        "feedback": ms.feedback,
    }


@mock_router.post("/{mock_id}/finish")
async def finish_mock(mock_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> dict[str, str]:
    ms = await get_or_404(session, MockSession, mock_id)
    ms.status = "finished"
    await session.commit()
    return {"status": "finished"}


# ---------- Testes técnicos ----------
@assessments_router.get("", response_model=list[AssessmentOut])
async def list_assessments(session: SessionDep, _user: CurrentUser, application_id: uuid.UUID | None = None) -> list[Assessment]:
    stmt = select(Assessment).order_by(Assessment.deadline_at.asc().nulls_last())
    if application_id:
        stmt = stmt.where(Assessment.application_id == application_id)
    return list((await session.scalars(stmt)).all())


@assessments_router.post("", response_model=AssessmentOut, status_code=201)
async def create_assessment(body: AssessmentIn, session: SessionDep, _user: CurrentUser) -> Assessment:
    app = await get_or_404(session, Application, body.application_id)
    a = Assessment(**body.model_dump())
    session.add(a)
    if body.deadline_at:
        await cal.create_event(
            session,
            application_id=app.id,
            kind="assessment_deadline",
            title="Prazo do teste técnico",
            start=body.deadline_at - timedelta(minutes=30),
            end=body.deadline_at,
            description=body.instructions or "",
        )
    if app.status in ("submitted", "under_review", "interviewing", "ghosted"):
        await app_service.transition(session, app, "assessment", actor="user", reason="teste técnico")
    await session.commit()
    return a


@assessments_router.put("/{assessment_id}", response_model=AssessmentOut)
async def update_assessment(assessment_id: uuid.UUID, body: AssessmentIn, session: SessionDep, _user: CurrentUser) -> Assessment:
    a = await get_or_404(session, Assessment, assessment_id)
    for k, v in body.model_dump(exclude={"application_id"}).items():
        setattr(a, k, v)
    await session.commit()
    return a
