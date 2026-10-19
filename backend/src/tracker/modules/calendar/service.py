"""Agenda: horários livres, eventos (sincronizados com o Google), rascunhos e blocos de estudo (RF-AGE)."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import events, settings_store
from tracker.core.config import get_settings
from tracker.integrations.google import oauth
from tracker.integrations.google.calendar import Calendar, event_body
from tracker.modules.calendar.models import CalendarEvent

log = logging.getLogger(__name__)


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().user_timezone)


def free_slots(
    busy: list[tuple[datetime, datetime]],
    start_day: date,
    days: int,
    window: dict[str, Any],
    duration_min: int,
    buffer_min: int,
    zone: ZoneInfo,
    count: int = 3,
    now: datetime | None = None,
    step_min: int = 30,
) -> list[tuple[datetime, datetime]]:
    """Primeiros `count` horários livres nas janelas (dias úteis, hh:mm–hh:mm), com folga."""
    now = now or datetime.now(zone)
    w_start, w_end = time.fromisoformat(window["start"]), time.fromisoformat(window["end"])
    allowed_days = set(window.get("days", [0, 1, 2, 3, 4]))
    buf = timedelta(minutes=buffer_min)
    dur = timedelta(minutes=duration_min)
    out: list[tuple[datetime, datetime]] = []
    per_day: dict[date, int] = {}
    for d in range(days):
        day = start_day + timedelta(days=d)
        if day.weekday() not in allowed_days:
            continue
        t = datetime.combine(day, w_start, zone)
        end_of_window = datetime.combine(day, w_end, zone)
        while t + dur <= end_of_window:
            s, e = t, t + dur
            if s >= now + timedelta(hours=2) and all(e + buf <= b0 or s - buf >= b1 for b0, b1 in busy):
                if per_day.get(day, 0) < 2:  # espalha as opções em dias diferentes
                    out.append((s, e))
                    per_day[day] = per_day.get(day, 0) + 1
                    if len(out) >= count:
                        return out
                    t = e + timedelta(hours=2)
                    continue
            t += timedelta(minutes=step_min)
    return out


async def google_calendar(session: AsyncSession) -> Calendar | None:
    if not await settings_store.flag(session, "calendar"):
        return None
    try:
        token = await oauth.get_access_token(session)
    except oauth.OAuthError:
        return None
    return Calendar(token)


async def busy_times(session: AsyncSession, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    busy: list[tuple[datetime, datetime]] = []
    cal = await google_calendar(session)
    if cal is not None:
        try:
            busy = await cal.freebusy(start, end, get_settings().user_timezone)
        except Exception as exc:
            log.warning("freebusy falhou: %s", exc)
    local = (
        await session.scalars(
            select(CalendarEvent).where(
                CalendarEvent.status != "cancelled", CalendarEvent.starts_at < end, CalendarEvent.ends_at > start
            )
        )
    ).all()
    busy += [(e.starts_at, e.ends_at) for e in local]
    return busy


async def availability(
    session: AsyncSession, duration_min: int = 60, days: int = 7, count: int = 3, start_day: date | None = None
) -> list[tuple[datetime, datetime]]:
    cfg = await settings_store.get(session, "calendar")
    zone = tz()
    start_day = start_day or (datetime.now(zone) + timedelta(days=1)).date()
    start = datetime.combine(start_day, time(0, 0), zone)
    busy = await busy_times(session, start, start + timedelta(days=days + 1))
    return free_slots(busy, start_day, days, cfg["windows"], duration_min, cfg["buffer_min"], zone, count)


async def conflicts(session: AsyncSession, start: datetime, end: datetime, exclude: uuid.UUID | None = None) -> list[str]:
    busy = await busy_times(session, start - timedelta(minutes=1), end + timedelta(minutes=1))
    rows = (
        await session.scalars(
            select(CalendarEvent).where(
                CalendarEvent.status != "cancelled", CalendarEvent.starts_at < end, CalendarEvent.ends_at > start
            )
        )
    ).all()
    names = [r.title for r in rows if r.id != exclude]
    return names or (["compromisso na agenda do Google"] if any(b0 < end and b1 > start for b0, b1 in busy) and not rows else [])


def _reminders(kind: str, cfg: dict[str, Any]) -> list[int]:
    if kind == "assessment_deadline":
        return [h * 60 for h in cfg.get("assessment_reminders_h", [48, 24])]
    if kind == "study_block":
        return [15]
    return [1440, 60]


async def push(session: AsyncSession, ev: CalendarEvent) -> None:
    cal = await google_calendar(session)
    cfg = await settings_store.get(session, "calendar")
    if cal is None:
        ev.meta = {**(ev.meta or {}), "local_only": True}
        return
    body = event_body(
        title=ev.title,
        start=ev.starts_at,
        end=ev.ends_at,
        tz=ev.timezone,
        description=ev.description or "",
        location=ev.location_or_link,
        application_id=str(ev.application_id) if ev.application_id else None,
        reminders_min=_reminders(ev.kind, cfg),
    )
    if ev.google_event_id:
        await cal.patch(ev.google_event_id, body)
    else:
        ev.google_event_id = await cal.insert(body)


async def create_event(
    session: AsyncSession,
    *,
    application_id: uuid.UUID | None,
    kind: str,
    title: str,
    start: datetime,
    end: datetime,
    description: str = "",
    link: str | None = None,
    attendees: list[Any] | None = None,
    source_email_id: uuid.UUID | None = None,
    draft: bool = False,
    meta: dict[str, Any] | None = None,
) -> CalendarEvent:
    ev = CalendarEvent(
        application_id=application_id,
        kind=kind,
        title=title,
        description=description,
        starts_at=start,
        ends_at=end,
        timezone=get_settings().user_timezone,
        location_or_link=link,
        attendees=attendees or [],
        source_email_id=source_email_id,
        status="draft" if draft else "confirmed",
        meta=meta or {},
    )
    clash = await conflicts(session, start, end)
    if clash:
        ev.meta = {**ev.meta, "conflicts": clash}
    session.add(ev)
    await session.flush()
    if not draft:
        try:
            await push(session, ev)
        except Exception as exc:
            ev.meta = {**ev.meta, "sync_error": str(exc)[:300]}
    await events.apublish("calendar", "calendar.updated", {"event_id": str(ev.id), "status": ev.status})
    return ev


async def confirm(
    session: AsyncSession, ev: CalendarEvent, start: datetime | None = None, end: datetime | None = None
) -> CalendarEvent:
    if start:
        ev.starts_at = start
        ev.ends_at = end or start + (ev.ends_at - ev.starts_at)
    ev.status = "confirmed"
    await push(session, ev)
    return ev


async def cancel(session: AsyncSession, ev: CalendarEvent) -> None:
    ev.status = "cancelled"
    cal = await google_calendar(session)
    if cal and ev.google_event_id:
        try:
            await cal.delete(ev.google_event_id)
        except Exception as exc:
            log.warning("falha ao remover evento: %s", exc)


async def ensure_study_block(session: AsyncSession, interview_event: CalendarEvent, dossier_url: str) -> CalendarEvent | None:
    """Bloco de estudo no dia anterior (RF-AGE-07)."""
    existing = await session.scalar(
        select(CalendarEvent).where(
            CalendarEvent.application_id == interview_event.application_id,
            CalendarEvent.kind == "study_block",
            CalendarEvent.status != "cancelled",
            CalendarEvent.meta["for_event"].astext == str(interview_event.id),
        )
    )
    if existing:
        return existing
    cfg = await settings_store.get(session, "calendar")
    zone = tz()
    day = (interview_event.starts_at.astimezone(zone) - timedelta(days=1)).date()
    if day < datetime.now(zone).date():
        day = datetime.now(zone).date()
    start = datetime.combine(day, time(0), zone)
    busy = await busy_times(session, start, start + timedelta(days=1))
    window = {**cfg["windows"], "days": [0, 1, 2, 3, 4, 5, 6]}
    slots = free_slots(busy, day, 1, window, int(cfg["study_block_min"]), 0, zone, 1, step_min=30)
    if not slots:
        return None
    s, e = slots[0]
    return await create_event(
        session,
        application_id=interview_event.application_id,
        kind="study_block",
        title=f"Estudo: {interview_event.title}",
        start=s,
        end=e,
        description=f"Revisar o dossiê: {dossier_url}",
        meta={"for_event": str(interview_event.id)},
    )
