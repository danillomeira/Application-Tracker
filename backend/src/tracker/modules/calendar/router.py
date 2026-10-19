"""Rotas de agenda (RF-AGE, RF-DSH-08)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from tracker.api.deps import SessionDep, get_or_404
from tracker.core.security import CurrentUser
from tracker.modules.calendar import service
from tracker.modules.calendar.models import CalendarEvent

router = APIRouter(prefix="/calendar", tags=["calendar"])


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    application_id: uuid.UUID | None
    kind: str
    google_event_id: str | None
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    timezone: str
    location_or_link: str | None
    attendees: list
    status: str
    meta: dict


class EventIn(BaseModel):
    application_id: uuid.UUID | None = None
    kind: str = "interview"
    title: str
    starts_at: datetime
    ends_at: datetime
    description: str = ""
    link: str | None = None


class ConfirmIn(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None


@router.get("/events", response_model=list[EventOut])
async def list_events(
    session: SessionDep,
    _user: CurrentUser,
    from_: datetime | None = None,
    to: datetime | None = None,
    status: str | None = None,
) -> list[CalendarEvent]:
    start = from_ or datetime.now(UTC) - timedelta(days=7)
    end = to or start + timedelta(days=60)
    stmt = select(CalendarEvent).where(CalendarEvent.starts_at >= start, CalendarEvent.starts_at <= end)
    if status:
        stmt = stmt.where(CalendarEvent.status == status)
    return list((await session.scalars(stmt.order_by(CalendarEvent.starts_at))).all())


@router.post("/events", response_model=EventOut, status_code=201)
async def create_event(body: EventIn, session: SessionDep, _user: CurrentUser) -> CalendarEvent:
    ev = await service.create_event(
        session,
        application_id=body.application_id,
        kind=body.kind,
        title=body.title,
        start=body.starts_at,
        end=body.ends_at,
        description=body.description,
        link=body.link,
    )
    await session.commit()
    return ev


@router.post("/events/{event_id}/confirm", response_model=EventOut)
async def confirm(event_id: uuid.UUID, body: ConfirmIn, session: SessionDep, _user: CurrentUser) -> CalendarEvent:
    ev = await get_or_404(session, CalendarEvent, event_id)
    await service.confirm(session, ev, body.starts_at, body.ends_at)
    if ev.kind == "interview":
        from tracker.core.config import get_settings

        iid = (ev.meta or {}).get("interview_id")
        await service.ensure_study_block(session, ev, f"{get_settings().app_base_url}/entrevistas/{iid or ''}")
    await session.commit()
    return ev


@router.post("/events/{event_id}/cancel", response_model=EventOut)
async def cancel(event_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> CalendarEvent:
    ev = await get_or_404(session, CalendarEvent, event_id)
    await service.cancel(session, ev)
    await session.commit()
    return ev


@router.get("/availability")
async def availability(
    session: SessionDep, _user: CurrentUser, duration: int = 60, days: int = 7, count: int = 3
) -> list[dict[str, str]]:
    slots = await service.availability(session, duration_min=duration, days=days, count=count)
    return [{"start": s.isoformat(), "end": e.isoformat()} for s, e in slots]
