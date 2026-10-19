"""Tarefas de entrevistas: dossiê."""

from __future__ import annotations

from typing import Any

from tracker.modules.interviews.service import build_dossier
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, tracked


async def _dossier(sm: SM, task_run_id: str | None, application_id: str, interview_id: str | None = None) -> dict[str, Any]:
    return {"dossier_id": await build_dossier(sm, application_id, interview_id, task_run_id)}


celery_app.task(name="ai.build_dossier")(tracked("ai.build_dossier")(_dossier))
