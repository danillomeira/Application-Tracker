"""Tarefas de avaliação: pontuar uma vaga, reavaliar todas, calibrar pesos."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from tracker.core import events
from tracker.modules.applications import service as app_service
from tracker.modules.companies.models import Company
from tracker.modules.jobs.models import Job
from tracker.modules.notifications.service import notify
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, run, tracked


async def score_and_route(sm: SM, job_id: str) -> dict[str, Any]:
    """Pontua a vaga e cria/atualiza a candidatura em `discovered` (ou `blocked`)."""
    from tracker.modules.scoring.service import score_job

    async with sm() as s:
        job = await s.get(Job, uuid.UUID(job_id))
        if job is None:
            return {"skipped": True}
        score = await score_job(s, job)
        company = await s.get(Company, job.company_id)
        app = await app_service.get_for_job(s, job.id)
        if app is None and job.status == "open":
            app = await app_service.create_for_job(
                s, job, status="blocked" if score.quadrant == "blocked" else "discovered", queue_priority=score.priority
            )
        elif app is not None:
            app.queue_priority = score.priority
            if score.quadrant == "blocked" and app.status == "discovered":
                await app_service.transition(s, app, "blocked", reason="; ".join(score.knockout["reasons"]))
        is_new_top = score.quadrant == "top" and not (job.extra or {}).get("notified_top")
        if is_new_top or (company and company.is_watchlisted and not (job.extra or {}).get("notified_top")):
            job.extra = {**(job.extra or {}), "notified_top": True}
            await notify(
                s,
                "watchlist_job" if company and company.is_watchlisted else "top_job",
                {
                    "company": company.name if company else "",
                    "title": job.title,
                    "message": f"Chance {score.chance:.0f} · Atratividade {score.attractiveness:.0f} — {score.suggested_action}",
                    "job_id": str(job.id),
                },
            )
        await s.commit()
        result = {
            "quadrant": score.quadrant,
            "chance": score.chance,
            "attractiveness": score.attractiveness,
            "priority": score.priority,
        }
    await events.apublish("jobs", "job.scored", {"job_id": job_id, **result})
    return result


@celery_app.task(name="scoring.score_job")
def score_job_task(job_id: str) -> dict[str, Any]:
    return run(lambda sm: score_and_route(sm, job_id))


async def _rescore_all(sm: SM, task_run_id: str | None) -> dict[str, Any]:
    async with sm() as s:
        ids = [str(i) for i in (await s.scalars(select(Job.id).where(Job.status == "open"))).all()]
    for jid in ids:
        await score_and_route(sm, jid)
    return {"rescored": len(ids)}


celery_app.task(name="scoring.rescore_all")(tracked("scoring.rescore_all")(_rescore_all))


async def _calibrate(sm: SM, task_run_id: str | None) -> dict[str, Any]:
    from tracker.modules.scoring.calibration import calibrate

    async with sm() as s:
        result = await calibrate(s)
        await s.commit()
    return result


celery_app.task(name="scoring.calibrate")(tracked("scoring.calibrate")(_calibrate))
