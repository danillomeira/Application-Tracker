"""Tarefas de agenda: blocos de estudo para entrevistas próximas (RF-AGE-07)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from tracker.core.config import get_settings
from tracker.modules.calendar import service
from tracker.modules.calendar.models import CalendarEvent
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, run


async def ensure_study_blocks(sm: SM) -> int:
    now = datetime.now(UTC)
    created = 0
    async with sm() as s:
        rows = (
            await s.scalars(
                select(CalendarEvent).where(
                    CalendarEvent.kind == "interview",
                    CalendarEvent.status == "confirmed",
                    CalendarEvent.starts_at > now,
                    CalendarEvent.starts_at < now + timedelta(days=3),
                )
            )
        ).all()
        for ev in rows:
            iid = (ev.meta or {}).get("interview_id", "")
            block = await service.ensure_study_block(s, ev, f"{get_settings().app_base_url}/entrevistas/{iid}")
            created += int(block is not None)
        await s.commit()
    return created


@celery_app.task(name="calendar.study_blocks")
def study_blocks_task() -> int:
    return run(ensure_study_blocks)
