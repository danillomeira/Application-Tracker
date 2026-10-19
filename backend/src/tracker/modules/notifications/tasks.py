"""Resumo diário (RF-NOT-04) e notificações adiadas pelas horas de silêncio."""

from __future__ import annotations

from typing import Any

from tracker.modules.notifications.service import notify
from tracker.modules.notifications.telegram_bot import summary_today
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, run


async def daily_digest(sm: SM) -> dict[str, Any]:
    async with sm() as s:
        text = await summary_today(s)
        await notify(s, "digest", {"message": text.replace("*Hoje*\n", "")})
        await s.commit()
    return {"sent": True}


@celery_app.task(name="notifications.daily_digest")
def daily_digest_task() -> dict[str, Any]:
    return run(daily_digest)
