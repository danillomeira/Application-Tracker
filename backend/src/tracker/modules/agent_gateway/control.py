"""Kill switch e pausa do agente (RF-CAN-10/11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import audit, events, settings_store
from tracker.modules.agent_gateway.models import AgentJob
from tracker.modules.platform.models import BrowserSessionMeta


async def kill(session: AsyncSession, actor: str, reason: str = "kill switch") -> int:
    ctl = await settings_store.get(session, "agent_control")
    await settings_store.put(
        session, "agent_control", {**ctl, "killed": True, "killed_at": datetime.now(UTC).isoformat(), "reason": reason}
    )
    jobs = (await session.scalars(select(AgentJob).where(AgentJob.status.in_(["leased", "running"])))).all()
    for j in jobs:
        j.status = "pending"  # retoma do checkpoint quando liberado
        j.lease_until = None
    await audit.record(session, actor=actor, action="agent.kill", reason=reason)
    await events.apublish("agent", "agent.kill", {"reason": reason})
    return len(jobs)


async def resume(session: AsyncSession, actor: str) -> None:
    ctl = await settings_store.get(session, "agent_control")
    await settings_store.put(session, "agent_control", {**ctl, "killed": False, "reason": None})
    meta = await session.scalar(select(BrowserSessionMeta).where(BrowserSessionMeta.site == "linkedin"))
    if meta is not None:
        meta.paused_until = None
    await audit.record(session, actor=actor, action="agent.resume")
    await events.apublish("agent", "agent.resumed", {})


async def is_blocked(session: AsyncSession, site: str = "linkedin") -> str | None:
    """Motivo pelo qual o agente não deve agir agora (ou None)."""
    ctl = await settings_store.get(session, "agent_control")
    if ctl.get("killed"):
        return f"agente parado ({ctl.get('reason') or 'kill switch'})"
    meta = await session.scalar(select(BrowserSessionMeta).where(BrowserSessionMeta.site == site))
    if meta and meta.paused_until and meta.paused_until > datetime.now(UTC):
        return f"pausado por segurança até {meta.paused_until.isoformat()}"
    return None


async def safety_pause(session: AsyncSession, site: str, hours: int, note: str) -> None:
    meta = await session.scalar(select(BrowserSessionMeta).where(BrowserSessionMeta.site == site))
    if meta is None:
        meta = BrowserSessionMeta(site=site)
        session.add(meta)
    now = datetime.now(UTC)
    meta.last_safety_stop_at = now
    if hours:
        meta.paused_until = now + timedelta(hours=hours)
    meta.notes = note
    await session.flush()
