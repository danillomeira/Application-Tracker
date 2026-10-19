"""Fila de jobs do agente local (docs/06 §Protocolo do agente)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import events
from tracker.modules.agent_gateway.models import AgentJob

LEASE = timedelta(minutes=10)


async def enqueue_agent_job(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    *,
    priority: float = 0.0,
    application_id: uuid.UUID | None = None,
) -> AgentJob:
    if application_id is not None:
        existing = await session.scalar(
            select(AgentJob).where(
                AgentJob.application_id == application_id,
                AgentJob.kind == kind,
                AgentJob.status.in_(["pending", "leased", "running", "paused"]),
            )
        )
        if existing is not None:
            existing.priority = max(existing.priority, priority)
            return existing
    job = AgentJob(kind=kind, payload=payload, priority=priority, application_id=application_id)
    session.add(job)
    await session.flush()
    await events.apublish("agent", "agent.job_queued", {"agent_job_id": str(job.id), "kind": kind})
    return job


async def lease_next(session: AsyncSession, kinds: list[str] | None = None) -> AgentJob | None:
    now = datetime.now(UTC)
    stmt = (
        select(AgentJob)
        .where(
            or_(
                AgentJob.status == "pending",
                (AgentJob.status.in_(["leased", "running"])) & (AgentJob.lease_until < now),
            )
        )
        .order_by(AgentJob.priority.desc(), AgentJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if kinds:
        stmt = stmt.where(AgentJob.kind.in_(kinds))
    job = await session.scalar(stmt)
    if job is None:
        return None
    job.status = "leased"
    job.lease_until = now + LEASE
    job.attempts += 1
    await session.flush()
    return job


async def heartbeat(session: AsyncSession, job_id: uuid.UUID) -> None:
    job = await session.get(AgentJob, job_id)
    if job is not None and job.status in ("leased", "running"):
        job.lease_until = datetime.now(UTC) + LEASE
        job.status = "running"


async def finish(session: AsyncSession, job: AgentJob, status: str, error: str | None = None) -> None:
    job.status = status
    job.error = error
    job.finished_at = datetime.now(UTC)
    job.lease_until = None
    await session.flush()
    await events.apublish("agent", f"agent.job_{status}", {"agent_job_id": str(job.id), "kind": job.kind, "error": error})
