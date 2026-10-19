"""Tarefas de candidaturas: preparação, sem retorno, follow-ups, expiração de pendências."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from tracker.core import settings_store
from tracker.core.tasks import dispatch
from tracker.modules.applications import service
from tracker.modules.applications.models import Application, PendingQuestion
from tracker.modules.jobs.models import Job
from tracker.modules.profile import service as profile_service
from tracker.modules.resumes import service as resume_service
from tracker.modules.resumes.models import ResumeVariant
from tracker.modules.scoring.service import current_score
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, run

log = logging.getLogger(__name__)


async def prepare(sm: SM, application_id: str) -> dict[str, Any]:
    """Escolhe/gera o CV, garante o PDF e encaminha (agente Easy Apply ou pacote externo)."""
    from tracker.modules.resumes.tasks import _tailor, generate_cover_letter

    async with sm() as s:
        app = await s.get(Application, uuid.UUID(application_id))
        assert app is not None
        job = await s.get(Job, app.job_id)
        assert job is not None
        score = await current_score(s, job.id)
        selection = await resume_service.select_for_job(s, job)
        job_id, quadrant = str(job.id), score.quadrant if score else "volume"
        variant_id = str(app.resume_variant_id) if app.resume_variant_id else None
        needs_tailored = selection["needs_tailored"]
        best = str(selection["best_variant_id"]) if selection["best_variant_id"] else None
        cover_needed = not app.cover_letter and quadrant in ("top", "bet")

    if variant_id is None:
        if needs_tailored and (quadrant in ("top", "bet") or best is None):
            result = await _tailor(sm, None, job_id=job_id, base_variant_id=best)
            variant_id = result["variant_id"]
        else:
            variant_id = best
    if variant_id is None:
        async with sm() as s:
            app = await s.get(Application, uuid.UUID(application_id))
            assert app is not None
            app.next_action = "crie ou aprove um currículo coringa"
            await s.commit()
        return {"status": "needs_resume"}

    async with sm() as s:
        app = await s.get(Application, uuid.UUID(application_id))
        assert app is not None
        variant = await s.get(ResumeVariant, uuid.UUID(variant_id))
        assert variant is not None
        app.resume_variant_id = variant.id
        if variant.status != "approved":
            app.next_action = "aprovar o CV específico antes de enviar"
            await service.add_event(s, app, "resume_selected", {"variant_id": variant_id, "status": variant.status})
            await s.commit()
            return {"status": "awaiting_resume_approval", "variant_id": variant_id}
        render = await resume_service.latest_render(s, variant.id)
        if render is None:
            _, master = await profile_service.current_master(s)
            job = await s.get(Job, app.job_id)
            render = await resume_service.render_variant(
                s, variant, master, list(((job.requirements if job else {}) or {}).get("must", []))
            )
        app.resume_render_id = render.id
        await service.add_event(s, app, "resume_selected", {"variant_id": variant_id, "render_id": str(render.id)})
        await s.commit()

    if cover_needed:
        try:
            letter = await generate_cover_letter(sm, job_id, variant_id)
            async with sm() as s:
                app = await s.get(Application, uuid.UUID(application_id))
                assert app is not None
                app.cover_letter = letter.text
                await s.commit()
        except Exception as exc:  # carta é opcional
            log.warning("carta não gerada: %s", exc)

    async with sm() as s:
        app = await s.get(Application, uuid.UUID(application_id))
        assert app is not None
        # sem robô: você se candidata no site da vaga; a extensão do navegador preenche o formulário
        app.next_action = "candidate-se no site da vaga (o assistente do navegador preenche) e marque 'Já me candidatei'"
        await s.commit()
    return {"status": "routed", "variant_id": variant_id}


@celery_app.task(name="applications.prepare")
def prepare_task(application_id: str) -> dict[str, Any]:
    return run(lambda sm: prepare(sm, application_id))


async def mark_ghosted(sm: SM, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    async with sm() as s:
        cfg = await settings_store.get(s, "tracking")
        cutoff = now - timedelta(days=int(cfg["ghost_after_days"]))
        rows = (
            await s.scalars(
                select(Application).where(
                    Application.status.in_(["submitted", "under_review"]), Application.last_activity_at < cutoff
                )
            )
        ).all()
        for app in rows:
            await service.transition(s, app, "ghosted", reason=f"sem resposta há {cfg['ghost_after_days']} dias")
        await s.commit()
        return len(rows)


@celery_app.task(name="applications.mark_ghosted")
def mark_ghosted_task() -> int:
    return run(lambda sm: mark_ghosted(sm))


async def expire_pending(sm: SM, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    async with sm() as s:
        rows = (
            await s.scalars(select(PendingQuestion).where(PendingQuestion.status == "open", PendingQuestion.expires_at < now))
        ).all()
        for pq in rows:
            pq.status = "expired"
            app = await s.get(Application, pq.application_id)
            if app and app.status == "needs_input":
                await service.transition(s, app, "skipped", reason="pergunta pendente expirou")
        await s.commit()
        return len(rows)


@celery_app.task(name="applications.expire_pending")
def expire_pending_task() -> int:
    return run(lambda sm: expire_pending(sm))


@celery_app.task(name="applications.suggest_followups")
def suggest_followups_task() -> int:
    from tracker.modules.inbox.followups import suggest_followups

    return run(lambda sm: suggest_followups(sm))


__all__ = ["dispatch"]
