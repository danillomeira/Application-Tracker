"""Protocolo do agente local (docs/06 §Protocolo do agente; ADR-014: HTTP + heartbeat).

O agente só executa: toda decisão (cota, janela, política, pendências, revisão) é da API.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from tracker.api.deps import SessionDep, get_or_404
from tracker.core import audit, events, settings_store
from tracker.core.config import get_settings
from tracker.core.security import CurrentUser, agent_auth
from tracker.core.storage import get_storage
from tracker.core.tasks import dispatch
from tracker.modules.agent_gateway import control
from tracker.modules.agent_gateway.models import AgentJob
from tracker.modules.agent_gateway.service import finish, heartbeat, lease_next
from tracker.modules.applications import service as app_service
from tracker.modules.applications.models import Application, ApplicationAnswer, PendingQuestion
from tracker.modules.applications.resolver import FormField, resolve_fields
from tracker.modules.companies.models import Company
from tracker.modules.jobs.models import Job, JobSource
from tracker.modules.notifications.service import notify
from tracker.modules.resumes.models import ResumeRender, ResumeVariant
from tracker.modules.scoring.models import JobScore

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(agent_auth)])
user_router = APIRouter(prefix="/agent-control", tags=["agent"])

LINKEDIN_KINDS = {"apply", "search", "read_messages"}
QUADRANT_ORDER = {"top": 3, "bet": 2, "volume": 1, "discard": 0}


def in_window(window: dict[str, Any], now: datetime | None = None) -> bool:
    zone = ZoneInfo(get_settings().user_timezone)
    now = (now or datetime.now(zone)).astimezone(zone)
    if now.weekday() not in set(window.get("days", [0, 1, 2, 3, 4])):
        return False
    return time.fromisoformat(window["start"]) <= now.time() < time.fromisoformat(window["end"])


class Hello(BaseModel):
    version: str
    sites: list[str] = Field(default_factory=list)
    machine: str | None = None


@router.post("/hello")
async def hello(body: Hello, session: SessionDep) -> dict[str, Any]:
    await audit.record(session, actor="agent", action="agent.hello", after=body.model_dump())
    await session.commit()
    limits = await settings_store.get(session, "limits")
    policy = await settings_store.get(session, "automation_policy")
    return {
        "limits": limits,
        "dry_run": bool(policy["easy_apply"].get("dry_run")),
        "blocked": await control.is_blocked(session),
    }


class NextIn(BaseModel):
    kinds: list[str] | None = None


async def _job_url(session: SessionDep, job: Job) -> str | None:
    src = await session.scalar(select(JobSource).where(JobSource.job_id == job.id, JobSource.source == "linkedin"))
    return (src.url if src else None) or job.canonical_url or job.apply_url


@router.post("/jobs/next")
async def next_job(body: NextIn, session: SessionDep) -> dict[str, Any]:
    blocked = await control.is_blocked(session)
    kinds = set(body.kinds or ["apply", "search", "read_messages", "fill_external"])
    limits = await settings_store.get(session, "limits")
    if blocked:
        kinds -= LINKEDIN_KINDS | {"fill_external"}
    if not in_window(limits["window"]):
        kinds -= LINKEDIN_KINDS
    if "apply" in kinds and await app_service.quota_used(session, "easy_apply") >= int(limits["easy_apply_per_day"]):
        kinds.discard("apply")
    if "search" in kinds and await app_service.quota_used(session, "linkedin_search") >= int(limits["linkedin_searches_per_day"]):
        kinds.discard("search")
    if not kinds:
        return {"wait": blocked or "fora da janela ou cota atingida", "retry_in": 300}
    job = await lease_next(session, sorted(kinds))
    if job is None:
        await session.commit()
        return {"wait": "fila vazia", "retry_in": 60}
    payload: dict[str, Any] = dict(job.payload)
    if job.kind in ("apply", "fill_external") and job.application_id:
        app = await session.get(Application, job.application_id)
        assert app is not None
        j = await session.get(Job, app.job_id)
        assert j is not None
        comp = await session.get(Company, j.company_id)
        payload.update(
            {
                "url": await _job_url(session, j),
                "apply_url": j.apply_url,
                "title": j.title,
                "company": comp.name if comp else "",
                "has_resume": app.resume_render_id is not None,
                "cover_letter": app.cover_letter,
            }
        )
        if app.status in ("queued", "needs_input", "awaiting_review"):
            target = "in_progress" if app.status == "queued" else app.status
            if target != app.status:
                await app_service.transition(session, app, target, actor="agent")
    await session.commit()
    await events.apublish("agent", "agent.status", {"agent_job_id": str(job.id), "kind": job.kind, "status": "leased"})
    return {"job": {"id": str(job.id), "kind": job.kind, "payload": payload, "state": job.state, "attempts": job.attempts}}


@router.post("/jobs/{job_id}/heartbeat")
async def hb(job_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    await heartbeat(session, job_id)
    job = await session.get(AgentJob, job_id)
    killed = (await settings_store.get(session, "agent_control"))["killed"]
    await session.commit()
    return {"kill": bool(killed) or (job is not None and job.status in ("cancelled", "pending"))}


class StepIn(BaseModel):
    index: int
    title: str
    log: str | None = None
    screenshot_key: str | None = None


@router.post("/jobs/{job_id}/step")
async def step(job_id: uuid.UUID, body: StepIn, session: SessionDep) -> dict[str, str]:
    job = await get_or_404(session, AgentJob, job_id)
    if job.application_id:
        app = await session.get(Application, job.application_id)
        if app:
            await app_service.add_event(session, app, "agent_step", body.model_dump(), actor="agent")
    await session.commit()
    await events.apublish("agent", "agent.step", {"agent_job_id": str(job_id), **body.model_dump()})
    return {"ok": "1"}


@router.post("/jobs/{job_id}/artifact")
async def artifact(job_id: uuid.UUID, session: SessionDep, file: UploadFile = File(...), name: str = Form(...)) -> dict[str, str]:
    job = await get_or_404(session, AgentJob, job_id)
    data = await file.read(15 * 1024 * 1024)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")[:80] or "artifact"
    key = get_storage().put(f"agent-artifacts/{day}/{job_id}/{safe}", data, file.content_type or "application/octet-stream")
    job.artifacts = [*job.artifacts, {"key": key, "name": safe, "at": datetime.now(UTC).isoformat()}]
    await session.commit()
    return {"key": key}


class CheckpointIn(BaseModel):
    state: dict[str, Any]


@router.post("/jobs/{job_id}/checkpoint")
async def checkpoint(job_id: uuid.UUID, body: CheckpointIn, session: SessionDep) -> dict[str, str]:
    job = await get_or_404(session, AgentJob, job_id)
    job.state = {**(job.state or {}), **body.state}
    await session.commit()
    return {"ok": "1"}


class ResolveIn(BaseModel):
    step_index: int
    fields: list[FormField]


@router.post("/jobs/{job_id}/resolve")
async def resolve(job_id: uuid.UUID, body: ResolveIn, session: SessionDep) -> dict[str, Any]:
    job = await get_or_404(session, AgentJob, job_id)
    if not job.application_id:
        raise HTTPException(422, "job sem candidatura")
    if job.application_id is None:
        raise HTTPException(422, "job sem candidatura")
    app = await get_or_404(session, Application, job.application_id)
    res = await resolve_fields(session, app, body.fields, body.step_index, (job.state or {}).get("user_answers"))
    if res.gaps:
        await app_service.add_event(session, app, "skill_gap", {"skills": res.gaps}, actor="agent")
    if res.pending:
        await finish(session, job, "paused")
        if app.status != "needs_input":
            await app_service.transition(
                session, app, "needs_input", actor="agent", reason=f"{len(res.pending)} pergunta(s) sem resposta"
            )
        j = await session.get(Job, app.job_id)
        comp = await session.get(Company, j.company_id) if j else None
        for f in res.pending:
            pq = await session.scalar(
                select(PendingQuestion).where(
                    PendingQuestion.application_id == app.id,
                    PendingQuestion.question_text == f.label,
                    PendingQuestion.status == "open",
                )
            )
            buttons = (
                [[{"text": o[:40], "callback_data": f"pq:{pq.id}:{i}"}] for i, o in enumerate(f.options)]
                if pq and f.options and len(f.options) <= 6
                else None
            )
            n = await notify(
                session,
                "pending_question",
                {
                    "company": comp.name if comp else "",
                    "title": j.title if j else "",
                    "question": f.label,
                    "message": f"Sugestão: {f.current_value}" if f.current_value else None,
                    "pending_question_id": str(pq.id) if pq else None,
                },
                buttons=buttons,
            )
            n.payload = {**n.payload, "pending_question_id": str(pq.id) if pq else None}
        await session.commit()
        await events.apublish("applications", "pending_question.created", {"application_id": str(app.id)})
        return {"pause": True, "pending": [f.label for f in res.pending]}
    await session.commit()
    return {"values": {r.key: r.value for r in res.values}, "resolutions": {r.key: r.resolution for r in res.values}}


@router.get("/applications/{app_id}/resume")
async def resume_pdf(app_id: uuid.UUID, session: SessionDep) -> Response:
    app = await get_or_404(session, Application, app_id)
    if not app.resume_render_id:
        raise HTTPException(404, "candidatura sem PDF")
    r = await get_or_404(session, ResumeRender, app.resume_render_id)
    return Response(
        get_storage().get(r.storage_key),
        media_type="application/pdf",
        headers={"content-disposition": f'attachment; filename="{r.filename}"', "x-filename": r.filename},
    )


class ReviewIn(BaseModel):
    summary: str | None = None
    screenshot_key: str | None = None


async def auto_allowed(session: SessionDep, app: Application, policy: dict[str, Any]) -> tuple[bool, str]:
    ea = policy["easy_apply"]
    if ea.get("mode") != "auto" or not await settings_store.flag(session, "auto_apply"):
        return False, "modo revisão"
    auto = ea["auto"]
    score = await session.scalar(select(JobScore).where(JobScore.job_id == app.job_id, JobScore.is_current.is_(True)))
    if score is None:
        return False, "vaga sem avaliação"
    allowed = {"top"} if auto["min_quadrant"] == "top" else {"top", "volume"}
    if score.quadrant not in allowed:
        return False, f"quadrante {score.quadrant}"
    if score.chance < float(auto["min_chance"]):
        return False, f"chance {score.chance:.0f} abaixo de {auto['min_chance']}"
    answers = (await session.scalars(select(ApplicationAnswer).where(ApplicationAnswer.application_id == app.id))).all()
    low = [a for a in answers if a.confidence < float(auto["min_answer_confidence"])]
    if low:
        return False, f"{len(low)} resposta(s) com confiança baixa"
    if app.resume_variant_id:
        v = await session.get(ResumeVariant, app.resume_variant_id)
        if v and v.kind == "tailored" and not auto["allow_tailored_resume"]:
            return False, "CV específico exige revisão"
    if await app_service.quota_used(session, "auto_apply") >= int(auto["max_per_day"]):
        return False, "cota diária do modo automático atingida"
    return True, "política automática satisfeita"


@router.post("/jobs/{job_id}/review")
async def review(job_id: uuid.UUID, body: ReviewIn, session: SessionDep) -> dict[str, Any]:
    job = await get_or_404(session, AgentJob, job_id)
    if job.application_id is None:
        raise HTTPException(422, "job sem candidatura")
    app = await get_or_404(session, Application, job.application_id)
    policy = await settings_store.get(session, "automation_policy")
    if (job.payload or {}).get("dry_run") or policy["easy_apply"].get("dry_run"):
        await app_service.add_event(session, app, "dry_run_complete", body.model_dump(), actor="agent")
        await finish(session, job, "done")
        await app_service.transition(session, app, "queued", actor="agent", reason="simulação concluída (dry run)")
        await session.commit()
        return {"approved": False, "dry_run": True}
    if (job.state or {}).get("review_approved"):
        await session.commit()
        return {"approved": True, "by": "user"}
    ok, why = await auto_allowed(session, app, policy)
    if ok:
        await app_service.add_event(session, app, "auto_approved", {"reason": why}, actor="system")
        await session.commit()
        return {"approved": True, "by": "policy"}
    await finish(session, job, "paused")
    job.state = {
        **(job.state or {}),
        "review_pending": True,
        "review_summary": body.summary,
        "review_screenshot": body.screenshot_key,
    }
    if app.status != "awaiting_review":
        await app_service.transition(session, app, "awaiting_review", actor="agent", reason=why)
    j = await session.get(Job, app.job_id)
    comp = await session.get(Company, j.company_id) if j else None
    await notify(
        session,
        "review_ready",
        {
            "company": comp.name if comp else "",
            "title": j.title if j else "",
            "message": why,
            "application_id": str(app.id),
        },
        buttons=[[{"text": "✅ Aprovar envio", "callback_data": f"ap:{app.id}"}]],
    )
    await session.commit()
    return {"approved": False, "reason": why}


class SubmittedIn(BaseModel):
    evidence: str | None = None
    screenshot_key: str | None = None
    already_applied: bool = False


@router.post("/jobs/{job_id}/submitted")
async def submitted(job_id: uuid.UUID, body: SubmittedIn, session: SessionDep) -> dict[str, Any]:
    job = await get_or_404(session, AgentJob, job_id)
    if job.application_id is None:
        raise HTTPException(422, "job sem candidatura")
    app = await get_or_404(session, Application, job.application_id)
    already = app.submitted_at is not None
    await app_service.register_submission(session, app, actor="agent", channel=None)
    app.evidence = {**(app.evidence or {}), **body.model_dump(), "at": datetime.now(UTC).isoformat()}
    for a in (await session.scalars(select(ApplicationAnswer).where(ApplicationAnswer.application_id == app.id))).all():
        a.locked = True
    if not already and not body.already_applied and job.kind == "apply":
        limits = await settings_store.get(session, "limits")
        await app_service.quota_increment(session, "easy_apply", int(limits["easy_apply_per_day"]))
        if (job.state or {}).get("review_approved") is not True:
            policy = await settings_store.get(session, "automation_policy")
            await app_service.quota_increment(session, "auto_apply", int(policy["easy_apply"]["auto"]["max_per_day"]))
    await finish(session, job, "done")
    await session.commit()
    return {"ok": True}


class SafetyIn(BaseModel):
    kind: str = Field(pattern="^(captcha|checkpoint|login|warning|unknown_layout|rate_limit|error_page)$")
    message: str
    url: str | None = None
    artifacts: list[str] = Field(default_factory=list)


@router.post("/jobs/{job_id}/safety-stop")
async def safety_stop(job_id: uuid.UUID, body: SafetyIn, session: SessionDep) -> dict[str, Any]:
    """Para tudo, salva estado e avisa (RF-CAN-10). Nunca contorna a proteção."""
    job = await get_or_404(session, AgentJob, job_id)
    job.status = "pending"
    job.lease_until = None
    job.error = f"{body.kind}: {body.message}"
    hours = {"warning": 72, "rate_limit": 6, "error_page": 1}.get(body.kind, 0)
    await control.safety_pause(session, "linkedin", hours, f"{body.kind}: {body.message}")
    if body.kind in ("captcha", "checkpoint", "login"):
        await control.kill(session, "agent", f"{body.kind}: ação humana necessária")
    if job.application_id:
        app = await session.get(Application, job.application_id)
        if app and app.status == "in_progress":
            await app_service.transition(session, app, "queued", actor="agent", reason=f"parada de segurança ({body.kind})")
    await notify(session, "agent_safety_stop", {"reason": body.kind, "message": body.message, "url": body.url})
    await audit.record(session, actor="agent", action="agent.safety_stop", after=body.model_dump())
    await session.commit()
    await events.apublish("agent", "agent.stopped", body.model_dump())
    return {"stop": True}


class FailIn(BaseModel):
    error: str
    closed: bool = False


@router.post("/jobs/{job_id}/fail")
async def fail(job_id: uuid.UUID, body: FailIn, session: SessionDep) -> dict[str, Any]:
    job = await get_or_404(session, AgentJob, job_id)
    app = await session.get(Application, job.application_id) if job.application_id else None
    if body.closed and app:
        j = await session.get(Job, app.job_id)
        if j:
            j.status = "closed"
        await finish(session, job, "done", "vaga encerrada")
        if app.status in ("in_progress", "queued", "needs_input", "awaiting_review"):
            await app_service.transition(session, app, "skipped", actor="agent", reason="vaga não aceita mais candidaturas")
    elif job.attempts >= 3:
        await finish(session, job, "failed", body.error[:1000])
        if app and app.status == "in_progress":
            await app_service.transition(session, app, "queued", actor="agent", reason="falha no agente")
            app.next_action = "falha no robô: candidatar manualmente"
    else:
        job.status = "pending"
        job.error = body.error[:1000]
        job.lease_until = None
    await session.commit()
    return {"ok": True}


class SearchResultsIn(BaseModel):
    jobs: list[dict[str, Any]]
    done: bool = True


@router.post("/jobs/{job_id}/search-results")
async def search_results(job_id: uuid.UUID, body: SearchResultsIn, session: SessionDep) -> dict[str, Any]:
    from tracker.modules.jobs import service as job_service
    from tracker.modules.jobs.normalize import RawJob

    job = await get_or_404(session, AgentJob, job_id)
    created = 0
    ss_id = (job.payload or {}).get("saved_search_id")
    for raw in body.jobs:
        rj = RawJob(
            source="linkedin",
            external_id=str(raw["external_id"]),
            title=raw["title"],
            company_name=raw["company"],
            url=raw.get("url"),
            location=raw.get("location"),
            description_text=raw.get("description") or "",
            applicants_count=raw.get("applicants"),
            posted_at=datetime.fromisoformat(raw["posted_at"]) if raw.get("posted_at") else None,
            apply_kind="easy_apply" if raw.get("easy_apply") else None,
            recruiter=raw.get("recruiter"),
        )
        j, is_new = await job_service.upsert_job(session, rj, uuid.UUID(ss_id) if ss_id else None)
        if is_new:
            created += 1
            dispatch("ai.process_job", job_id=str(j.id))
    if body.done:
        limits = await settings_store.get(session, "limits")
        await app_service.quota_increment(session, "linkedin_search", int(limits["linkedin_searches_per_day"]))
        await finish(session, job, "done")
    await session.commit()
    return {"created": created}


class MessagesIn(BaseModel):
    messages: list[dict[str, Any]]


@router.post("/jobs/{job_id}/messages")
async def messages(job_id: uuid.UUID, body: MessagesIn, session: SessionDep) -> dict[str, Any]:
    from tracker.modules.inbox.linkedin import process_linkedin_messages

    job = await get_or_404(session, AgentJob, job_id)
    n = await process_linkedin_messages(session, body.messages)
    await finish(session, job, "done")
    await session.commit()
    return {"processed": n}


@router.post("/jobs/{job_id}/done")
async def done(job_id: uuid.UUID, session: SessionDep) -> dict[str, bool]:
    job = await get_or_404(session, AgentJob, job_id)
    await finish(session, job, "done")
    await session.commit()
    return {"ok": True}


@router.post("/login-ok")
async def login_ok(session: SessionDep, site: str = "linkedin") -> dict[str, bool]:
    from tracker.modules.platform.models import BrowserSessionMeta

    meta = await session.scalar(select(BrowserSessionMeta).where(BrowserSessionMeta.site == site))
    if meta is None:
        meta = BrowserSessionMeta(site=site)
        session.add(meta)
    meta.last_login_ok_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True}


# ---------- Controle pelo usuário ----------
@user_router.get("/status")
async def status(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    from tracker.modules.platform.models import BrowserSessionMeta

    running = (await session.scalars(select(AgentJob).where(AgentJob.status.in_(["leased", "running"])))).all()
    pending = (
        await session.scalars(
            select(AgentJob).where(AgentJob.status.in_(["pending", "paused"])).order_by(AgentJob.priority.desc()).limit(50)
        )
    ).all()
    recent = (
        await session.scalars(
            select(AgentJob)
            .where(AgentJob.status.in_(["done", "failed", "cancelled"]))
            .order_by(AgentJob.finished_at.desc().nulls_last())
            .limit(20)
        )
    ).all()
    meta = await session.scalar(select(BrowserSessionMeta).where(BrowserSessionMeta.site == "linkedin"))
    limits = await settings_store.get(session, "limits")

    def j(x: AgentJob) -> dict[str, Any]:
        return {
            "id": str(x.id),
            "kind": x.kind,
            "status": x.status,
            "priority": x.priority,
            "application_id": str(x.application_id) if x.application_id else None,
            "attempts": x.attempts,
            "error": x.error,
            "artifacts": x.artifacts[-5:],
            "updated_at": x.updated_at.isoformat(),
        }

    return {
        "blocked": await control.is_blocked(session),
        "in_window": in_window(limits["window"]),
        "quota": {"used": await app_service.quota_used(session, "easy_apply"), "limit": limits["easy_apply_per_day"]},
        "running": [j(x) for x in running],
        "queue": [j(x) for x in pending],
        "recent": [j(x) for x in recent],
        "last_login_ok_at": meta.last_login_ok_at.isoformat() if meta and meta.last_login_ok_at else None,
        "last_safety_stop_at": meta.last_safety_stop_at.isoformat() if meta and meta.last_safety_stop_at else None,
        "safety_note": meta.notes if meta else None,
    }


@user_router.post("/kill")
async def kill(session: SessionDep, _user: CurrentUser) -> dict[str, int]:
    n = await control.kill(session, "user", "dashboard")
    await session.commit()
    return {"interrupted": n}


@user_router.post("/resume")
async def resume(session: SessionDep, _user: CurrentUser) -> dict[str, str]:
    await control.resume(session, "user")
    await session.commit()
    return {"status": "resumed"}


@user_router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> dict[str, str]:
    job = await get_or_404(session, AgentJob, job_id)
    await finish(session, job, "cancelled")
    await session.commit()
    return {"status": "cancelled"}


@user_router.get("/artifacts")
async def get_artifact(key: str, _user: CurrentUser) -> Response:
    if not key.startswith("agent-artifacts/"):
        raise HTTPException(404)
    data = get_storage().get(key)
    media = "image/png" if key.endswith(".png") else "text/html" if key.endswith(".html") else "application/zip"
    return Response(data, media_type=media, headers={"content-security-policy": "sandbox"})


def _hash(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()[:12]
