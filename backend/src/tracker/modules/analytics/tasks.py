"""Relatório semanal, plano de estudo e otimização do perfil do LinkedIn (RF-ANA-04/06/07)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from tracker.integrations.claude.client import AIError, AIRequest, get_ai, load_prompt
from tracker.modules.analytics import service
from tracker.modules.notifications.service import notify
from tracker.modules.platform.models import Setting
from tracker.modules.profile import service as profile_service
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, run, tracked


class WeeklyReport(BaseModel):
    headline: str
    highlights: list[str]
    recommendations: list[str] = Field(description="exatamente 3, acionáveis")


class StudyItem(BaseModel):
    skill: str
    why: str
    resources: list[str]
    effort_hours: int


class StudyPlan(BaseModel):
    items: list[StudyItem]


class ProfileSuggestion(BaseModel):
    section: str
    current: str | None = None
    suggested: str
    why: str


class ProfileSuggestions(BaseModel):
    suggestions: list[ProfileSuggestion]


async def _save(sm: SM, key: str, value: dict[str, Any]) -> None:
    from sqlalchemy import select

    async with sm() as s:
        row = await s.scalar(select(Setting).where(Setting.key == key))
        if row is None:
            s.add(Setting(key=key, value=value))
        else:
            row.value = value
        await s.commit()


def fallback_report(m: dict[str, Any]) -> WeeklyReport:
    w, p = m["week"], m["previous_week"]
    recs = []
    if w["submitted"] < m["goals"]["applications"]["target"]:
        recs.append("Aumente o ritmo: priorize as vagas do quadrante 'top' e use os coringas.")
    if w["response_rate"] < 0.1 and w["submitted"] >= 5:
        recs.append("Taxa de resposta baixa: aposte em CV específico e contato com recrutador nas vagas 'bet'.")
    if m["skill_gaps"]:
        recs.append(f"Estude {m['skill_gaps'][0]['skill']}: é o requisito que mais falta nas vagas que você mira.")
    while len(recs) < 3:
        recs.append("Mantenha os follow-ups em dia nas candidaturas sem resposta.")
    return WeeklyReport(
        headline=f"{w['submitted']} candidaturas, {w['responded']} respostas, {w['interviewing']} entrevistas",
        highlights=[
            f"Semana anterior: {p['submitted']} candidaturas e {p['responded']} respostas.",
            f"Taxa de resposta: {round(w['response_rate'] * 100)}%.",
        ],
        recommendations=recs[:3],
    )


async def weekly_report(sm: SM) -> dict[str, Any]:
    async with sm() as s:
        m = await service.weekly_metrics(s)
    try:
        res = await get_ai(sm).structured(
            AIRequest(
                task="insights.weekly",
                system=load_prompt("insights.weekly"),
                user=f"<metrics>{json.dumps(m, ensure_ascii=False, default=str)}</metrics>",
                effort="medium",
                max_tokens=3000,
            ),
            WeeklyReport,
        )
        report = res.output
    except AIError:
        report = fallback_report(m)
    data = {"generated_at": datetime.now(UTC).isoformat(), "metrics": m, **report.model_dump()}
    await _save(sm, "weekly_report", data)
    async with sm() as s:
        text = report.headline + "\n" + "\n".join(f"• {r}" for r in report.recommendations)
        await notify(s, "weekly", {"message": text})
        await s.commit()
    return data


@celery_app.task(name="ai.weekly_report")
def weekly_report_task() -> dict[str, Any]:
    return run(weekly_report)


async def _study_plan(sm: SM, task_run_id: str | None) -> dict[str, Any]:
    async with sm() as s:
        gaps = await service.skill_gaps(s)
        _, master = await profile_service.current_master(s)
    res = await get_ai(sm).structured(
        AIRequest(
            task="insights.skill_gaps",
            system=load_prompt("insights.skill_gaps"),
            context="<profile>\n" + master.model_dump_json(exclude_none=True) + "\n</profile>",
            user=f"<gaps>{json.dumps(gaps[:10], ensure_ascii=False)}</gaps>",
            effort="medium",
        ),
        StudyPlan,
    )
    data = {"generated_at": datetime.now(UTC).isoformat(), "gaps": gaps, **res.output.model_dump()}
    await _save(sm, "study_plan", data)
    return {"items": len(res.output.items)}


celery_app.task(name="ai.study_plan")(tracked("ai.study_plan")(_study_plan))


async def _linkedin_optimize(sm: SM, task_run_id: str | None, current_profile: str = "") -> dict[str, Any]:
    from sqlalchemy import select

    from tracker.modules.jobs.models import Job
    from tracker.modules.scoring.models import JobScore

    async with sm() as s:
        _, master = await profile_service.current_master(s)
        jobs = (
            await s.execute(
                select(Job.title, Job.requirements)
                .join(JobScore, JobScore.job_id == Job.id)
                .where(JobScore.is_current.is_(True), JobScore.quadrant.in_(["top", "bet"]))
                .limit(30)
            )
        ).all()
    targets = [{"title": t, "must": (r or {}).get("must", [])} for t, r in jobs]
    res = await get_ai(sm).structured(
        AIRequest(
            task="profile.linkedin_optimize",
            system=load_prompt("profile.linkedin_optimize"),
            context="<profile>\n" + master.model_dump_json(exclude_none=True) + "\n</profile>",
            user=f"<current_linkedin>{current_profile[:12000]}</current_linkedin>\n<target_jobs>{json.dumps(targets, ensure_ascii=False)}</target_jobs>",
            effort="high",
        ),
        ProfileSuggestions,
    )
    data = {"generated_at": datetime.now(UTC).isoformat(), **res.output.model_dump()}
    await _save(sm, "linkedin_suggestions", data)
    return {"suggestions": len(res.output.suggestions)}


celery_app.task(name="ai.linkedin_optimize")(tracked("ai.linkedin_optimize")(_linkedin_optimize))
