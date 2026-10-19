"""Rotas da plataforma: saúde, configurações, tarefas, custo de IA, auditoria, notificações."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text

from tracker.api.deps import Page, SessionDep, TaskAccepted, get_or_404, paginate
from tracker.core import audit, settings_store
from tracker.core.config import get_settings
from tracker.core.security import CurrentUser
from tracker.core.tasks import enqueue
from tracker.integrations.claude.client import month_spend
from tracker.modules.platform.models import AiCall, AuditLog, IntegrationState, Notification, TaskRun

router = APIRouter(tags=["platform"])


class TaskRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    status: str
    progress: int
    message: str | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor: str
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    occurred_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    channel: str
    kind: str
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None


class IntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
    consecutive_errors: int


class AiUsageRow(BaseModel):
    task: str
    calls: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


class AiUsage(BaseModel):
    month_spend_usd: float
    budget_usd: float
    by_task: list[AiUsageRow]
    by_day: list[dict[str, Any]]


@router.get("/health")
async def health(session: SessionDep) -> dict[str, Any]:
    db_ok = redis_ok = False
    try:
        await session.execute(text("select 1"))
        db_ok = True
    except Exception:  # noqa: S110
        pass
    try:
        r = aioredis.Redis.from_url(get_settings().redis_url)
        redis_ok = bool(await r.ping())
        await r.aclose()
    except Exception:  # noqa: S110
        pass
    return {"status": "ok" if db_ok and redis_ok else "degraded", "db": db_ok, "redis": redis_ok}


@router.get("/settings/{key}")
async def get_setting(key: str, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    if key not in settings_store.DEFAULTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "configuração desconhecida")
    return await settings_store.get(session, key)


@router.put("/settings/{key}")
async def put_setting(key: str, value: dict[str, Any], session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    before = await settings_store.get(session, key) if key in settings_store.DEFAULTS else None
    try:
        merged = await settings_store.put(session, key, value)
    except settings_store.SettingError as exc:
        raise HTTPException(422, str(exc)) from exc
    await audit.record(
        session, actor="user", action="settings.update", entity_type="setting", before=before, after=merged, reason=key
    )
    await session.commit()
    return merged


@router.get("/tasks/{task_id}", response_model=TaskRunOut)
async def get_task(task_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> TaskRun:
    return await get_or_404(session, TaskRun, task_id)


@router.get("/tasks", response_model=list[TaskRunOut])
async def list_tasks(session: SessionDep, _user: CurrentUser, status_: str | None = None) -> list[TaskRun]:
    stmt = select(TaskRun).order_by(TaskRun.created_at.desc()).limit(50)
    if status_:
        stmt = stmt.where(TaskRun.status == status_)
    return list((await session.scalars(stmt)).all())


@router.post("/dev/ping", response_model=TaskAccepted, status_code=202)
async def dev_ping(session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    tr = await enqueue(session, "platform.ping", steps=5)
    return TaskAccepted(task_id=tr.id)


@router.get("/ai/usage", response_model=AiUsage)
async def ai_usage(session: SessionDep, _user: CurrentUser, days: int = 30) -> AiUsage:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await session.execute(
            select(
                AiCall.task,
                func.count(),
                func.sum(AiCall.cost_usd),
                func.sum(AiCall.input_tokens),
                func.sum(AiCall.output_tokens),
                func.sum(AiCall.cache_read_tokens),
            )
            .where(AiCall.created_at >= since)
            .group_by(AiCall.task)
            .order_by(func.sum(AiCall.cost_usd).desc())
        )
    ).all()
    day_col = func.date_trunc("day", AiCall.created_at)
    days_rows = (
        await session.execute(
            select(day_col, func.sum(AiCall.cost_usd), func.count())
            .where(AiCall.created_at >= since)
            .group_by(day_col)
            .order_by(day_col)
        )
    ).all()
    return AiUsage(
        month_spend_usd=round(await month_spend(session), 4),
        budget_usd=get_settings().ai_monthly_budget_usd,
        by_task=[
            AiUsageRow(
                task=r[0],
                calls=r[1],
                cost_usd=round(r[2] or 0, 4),
                input_tokens=r[3] or 0,
                output_tokens=r[4] or 0,
                cache_read_tokens=r[5] or 0,
            )
            for r in rows
        ],
        by_day=[
            {
                "day": d[0].date().isoformat() if isinstance(d[0], datetime) else str(d[0]),
                "cost_usd": round(d[1] or 0, 4),
                "calls": d[2],
            }
            for d in days_rows
        ],
    )


@router.get("/audit", response_model=Page[AuditOut])
async def list_audit(
    session: SessionDep,
    _user: CurrentUser,
    entity_type: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[AuditOut]:
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    items, nxt = await paginate(session, stmt, AuditLog, cursor, limit, AuditLog.occurred_at)
    return Page(items=[AuditOut.model_validate(i) for i in items], next_cursor=nxt)


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(session: SessionDep, _user: CurrentUser, unread: bool = False) -> list[Notification]:
    stmt = select(Notification).order_by(Notification.created_at.desc()).limit(100)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list((await session.scalars(stmt)).all())


@router.post("/notifications/read-all")
async def read_all(session: SessionDep, _user: CurrentUser) -> dict[str, int]:
    rows = (await session.scalars(select(Notification).where(Notification.read_at.is_(None)))).all()
    now = datetime.now(UTC)
    for n in rows:
        n.read_at = now
    await session.commit()
    return {"updated": len(rows)}


@router.get("/integrations/health", response_model=list[IntegrationOut])
async def integrations_health(session: SessionDep, _user: CurrentUser) -> list[IntegrationState]:
    return list((await session.scalars(select(IntegrationState).order_by(IntegrationState.name))).all())


@router.get("/system/today")
async def today() -> dict[str, str]:
    return {"date": date.today().isoformat()}
