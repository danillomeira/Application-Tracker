"""Candidaturas: criação, transições validadas, linha do tempo e eventos (RF-ACO-11)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import audit, events
from tracker.modules.applications import state_machine
from tracker.modules.applications.models import Application, ApplicationEvent
from tracker.modules.jobs.models import Job


async def add_event(
    session: AsyncSession,
    app: Application,
    kind: str,
    payload: dict[str, Any] | None = None,
    actor: str = "system",
    reason: str | None = None,
    occurred_at: datetime | None = None,
) -> ApplicationEvent:
    ev = ApplicationEvent(
        application_id=app.id,
        kind=kind,
        payload=payload or {},
        actor=actor,
        reason=reason,
        occurred_at=occurred_at or datetime.now(UTC),
    )
    session.add(ev)
    app.last_activity_at = datetime.now(UTC)
    await session.flush()
    return ev


async def get_for_job(session: AsyncSession, job_id: uuid.UUID) -> Application | None:
    return await session.scalar(select(Application).where(Application.job_id == job_id))


async def create_for_job(
    session: AsyncSession,
    job: Job,
    *,
    status: str = "discovered",
    channel: str | None = None,
    mode: str = "review",
    actor: str = "system",
    queue_priority: float = 0.0,
) -> Application:
    existing = await get_for_job(session, job.id)
    if existing is not None:
        return existing
    app = Application(
        job_id=job.id,
        status=status,
        channel=channel
        or ("easy_apply" if job.apply_kind == "easy_apply" else "email" if job.apply_kind == "email" else "external"),
        mode=mode,
        queue_priority=queue_priority,
    )
    session.add(app)
    await session.flush()
    await add_event(session, app, "status_change", {"from": None, "to": status}, actor=actor)
    return app


async def transition(
    session: AsyncSession,
    app: Application,
    new_status: str,
    *,
    actor: str = "system",
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
    force: bool = False,
) -> Application:
    old = app.status
    if old == new_status and new_status != "interviewing":
        return app
    if not force:
        state_machine.check(old, new_status)
    app.status = new_status
    if new_status == "submitted" and app.submitted_at is None:
        app.submitted_at = datetime.now(UTC)
    if new_status in ("rejected", "withdrawn", "declined") and reason:
        app.outcome_reason = reason
    await add_event(session, app, "status_change", {"from": old, "to": new_status, **(payload or {})}, actor=actor, reason=reason)
    await audit.record(
        session,
        actor=actor,
        action="application.transition",
        entity_type="application",
        entity_id=app.id,
        before={"status": old},
        after={"status": new_status},
        reason=reason,
    )
    await events.apublish("applications", "application.updated", {"application_id": str(app.id), "from": old, "to": new_status})
    return app


async def register_submission(
    session: AsyncSession, app: Application, actor: str, channel: str | None, submitted_at: datetime | None = None
) -> None:
    from tracker.modules.jobs import service as job_service
    from tracker.modules.scoring.models import JobScore

    job = await session.get(Job, app.job_id)
    assert job is not None
    snap = await job_service.snapshot(session, job, "applied")
    score = await session.scalar(select(JobScore).where(JobScore.job_id == job.id, JobScore.is_current.is_(True)))
    app.applied_snapshot_id = snap.id
    app.priority_at_submit = (
        {"chance": score.chance, "attractiveness": score.attractiveness, "quadrant": score.quadrant} if score else None
    )
    if channel:
        app.channel = channel
    if app.status != "submitted":
        await transition(session, app, "submitted", actor=actor, force=True, payload={"manual": actor == "user"})
    app.submitted_at = submitted_at or app.submitted_at or datetime.now(UTC)
    app.next_action = None


async def quota_used(session: AsyncSession, kind: str) -> int:
    from datetime import date

    from tracker.modules.applications.models import DailyQuota

    q = await session.scalar(select(DailyQuota).where(DailyQuota.day == date.today(), DailyQuota.kind == kind))
    return q.used if q else 0


async def quota_increment(session: AsyncSession, kind: str, limit: int) -> int:
    from datetime import date

    from tracker.modules.applications.models import DailyQuota

    q = await session.scalar(select(DailyQuota).where(DailyQuota.day == date.today(), DailyQuota.kind == kind).with_for_update())
    if q is None:
        q = DailyQuota(day=date.today(), kind=kind, used=0, limit=limit)
        session.add(q)
    q.used += 1
    q.limit = limit
    await session.flush()
    return q.used
