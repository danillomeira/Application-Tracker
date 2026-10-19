"""Métricas e aprendizado (RF-ANA-01..08)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import settings_store
from tracker.modules.applications.models import Application, ApplicationEvent
from tracker.modules.applications.state_machine import POSITIVE, RESPONDED, SENT
from tracker.modules.inbox.models import Draft
from tracker.modules.jobs.models import Job, JobSource
from tracker.modules.resumes.models import ResumeVariant
from tracker.modules.scoring.models import JobScore


def _rate(num: int, den: int) -> float:
    return round(num / den, 3) if den else 0.0


async def funnel(session: AsyncSession, since: datetime, until: datetime | None = None) -> dict[str, Any]:
    until = until or datetime.now(UTC)
    found = await session.scalar(select(func.count()).select_from(Job).where(Job.first_seen_at.between(since, until))) or 0
    scored = (
        await session.scalar(
            select(func.count(func.distinct(JobScore.job_id)))
            .join(Job, Job.id == JobScore.job_id)
            .where(Job.first_seen_at.between(since, until))
        )
        or 0
    )
    apps = (
        await session.execute(select(Application.id, Application.status).where(Application.submitted_at.between(since, until)))
    ).all()
    ids = [a[0] for a in apps]
    reached: dict[str, set[Any]] = {"interviewing": set(), "assessment": set(), "offer": set()}
    if ids:
        evs = (
            await session.execute(
                select(ApplicationEvent.application_id, ApplicationEvent.payload).where(
                    ApplicationEvent.application_id.in_(ids), ApplicationEvent.kind == "status_change"
                )
            )
        ).all()
        for aid, payload in evs:
            to = (payload or {}).get("to")
            if to in reached:
                reached[to].add(aid)
    responded = {a[0] for a in apps if a[1] in RESPONDED} | reached["interviewing"] | reached["assessment"] | reached["offer"]
    submitted = len(apps)
    return {
        "found": found,
        "evaluated": scored,
        "submitted": submitted,
        "responded": len(responded),
        "interviewing": len(reached["interviewing"]),
        "assessment": len(reached["assessment"]),
        "offer": len(reached["offer"]),
        "response_rate": _rate(len(responded), submitted),
        "interview_rate": _rate(len(reached["interviewing"]), submitted),
    }


async def performance(session: AsyncSession, since: datetime) -> dict[str, list[dict[str, Any]]]:
    rows = (
        await session.execute(
            select(Application, Job, JobScore, ResumeVariant)
            .join(Job, Job.id == Application.job_id)
            .outerjoin(JobScore, and_(JobScore.job_id == Job.id, JobScore.is_current.is_(True)))
            .outerjoin(ResumeVariant, ResumeVariant.id == Application.resume_variant_id)
            .where(Application.status.in_(SENT), Application.submitted_at >= since)
        )
    ).all()
    sources = {s.job_id: s.source for s in (await session.scalars(select(JobSource))).all()}

    def group(key_fn: Any) -> list[dict[str, Any]]:
        acc: dict[str, list[int]] = {}
        for app, job, score, variant in rows:
            k = key_fn(app, job, score, variant)
            a = acc.setdefault(k, [0, 0, 0])
            a[0] += 1
            a[1] += app.status in RESPONDED
            a[2] += app.status in POSITIVE
        return sorted(
            (
                {
                    "key": k,
                    "sent": v[0],
                    "responses": v[1],
                    "positive": v[2],
                    "response_rate": _rate(v[1], v[0]),
                    "positive_rate": _rate(v[2], v[0]),
                }
                for k, v in acc.items()
            ),
            key=lambda r: -r["sent"],
        )

    weekdays = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    return {
        "by_resume": group(lambda a, j, s, v: f"{v.name} ({v.kind}, {v.language})" if v else "sem CV registrado"),
        "by_quadrant": group(lambda a, j, s, v: s.quadrant if s else "sem nota"),
        "by_source": group(lambda a, j, s, v: sources.get(j.id, "manual")),
        "by_channel": group(lambda a, j, s, v: a.channel),
        "by_weekday": group(lambda a, j, s, v: weekdays[a.submitted_at.weekday()] if a.submitted_at else "?"),
        "by_hour": group(lambda a, j, s, v: f"{a.submitted_at.hour:02d}h" if a.submitted_at else "?"),
    }


async def skill_gaps(session: AsyncSession, days: int = 60) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(JobScore.explanation, Job.first_seen_at)
            .join(Job, Job.id == JobScore.job_id)
            .where(
                JobScore.is_current.is_(True),
                JobScore.quadrant.in_(["top", "bet", "volume"]),
                Job.first_seen_at >= now - timedelta(days=days),
            )
        )
    ).all()
    recent: Counter[str] = Counter()
    older: Counter[str] = Counter()
    for expl, seen in rows:
        for skill in (expl or {}).get("missing_must", []):
            k = skill.strip()
            (recent if seen >= now - timedelta(days=days / 2) else older)[k] += 1
    total = len(rows) or 1
    out = []
    for skill, n in (recent + older).most_common(25):
        trend = "subindo" if recent[skill] > older[skill] else "caindo" if recent[skill] < older[skill] else "estável"
        out.append({"skill": skill, "jobs": n, "share": round(n / total, 3), "trend": trend})
    return out


async def rejections(session: AsyncSession, since: datetime) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(Application, Job, JobScore)
            .join(Job, Job.id == Application.job_id)
            .outerjoin(JobScore, and_(JobScore.job_id == Job.id, JobScore.is_current.is_(True)))
            .where(Application.status == "rejected", Application.last_activity_at >= since)
        )
    ).all()
    stage: Counter[str] = Counter()
    seniority: Counter[str] = Counter()
    quadrant: Counter[str] = Counter()
    reasons: list[str] = []
    for app, job, score in rows:
        evs = (
            await session.scalars(
                select(ApplicationEvent.payload).where(
                    ApplicationEvent.application_id == app.id, ApplicationEvent.kind == "status_change"
                )
            )
        ).all()
        tos = {(e or {}).get("to") for e in evs}
        stage["após entrevista" if "interviewing" in tos else "após teste" if "assessment" in tos else "triagem"] += 1
        seniority[job.seniority or "?"] += 1
        quadrant[score.quadrant if score else "?"] += 1
        if app.outcome_reason:
            reasons.append(app.outcome_reason)
    return {
        "total": len(rows),
        "by_stage": dict(stage),
        "by_seniority": dict(seniority),
        "by_quadrant": dict(quadrant),
        "reasons": reasons[:20],
    }


async def goals(session: AsyncSession) -> dict[str, Any]:
    cfg = await settings_store.get(session, "goals")
    week_start = datetime.now(UTC) - timedelta(days=7)
    applied = (
        await session.scalar(select(func.count()).select_from(Application).where(Application.submitted_at >= week_start)) or 0
    )
    followups = (
        await session.scalar(
            select(func.count())
            .select_from(Draft)
            .where(Draft.kind == "followup", Draft.status == "sent_by_user", Draft.updated_at >= week_start)
        )
        or 0
    )
    target = int(cfg["applications_per_week"])
    alerts = []
    if applied > 2 * target:
        alerts.append("Ritmo muito acima da meta: cuidado com desgaste e com a qualidade das candidaturas.")
    if applied < target / 2 and datetime.now(UTC).weekday() >= 3:
        alerts.append("Abaixo da metade da meta semanal de candidaturas.")
    return {
        "applications": {"done": applied, "target": target},
        "followups": {"done": followups, "target": int(cfg["followups_per_week"])},
        "study_hours": {"target": int(cfg["study_hours_per_week"])},
        "alerts": alerts,
    }


async def wildcard_suggestions(session: AsyncSession, threshold: float | None = None) -> list[dict[str, Any]]:
    """Clusters de vagas boas com baixa aderência aos coringas (RF-CV-10)."""
    cfg = await settings_store.get(session, "resume")
    th = threshold or float(cfg["match_threshold"])
    rows = (
        await session.execute(
            select(Job.normalized_title, JobScore.variant_scores)
            .join(JobScore, JobScore.job_id == Job.id)
            .where(JobScore.is_current.is_(True), JobScore.quadrant.in_(["top", "bet"]), Job.status == "open")
        )
    ).all()
    clusters: Counter[str] = Counter()
    for title, vs in rows:
        best = (vs or {}).get("_best_score")
        if best is None or best < th:
            key = " ".join(
                w for w in title.split() if w not in {"senior", "sr", "junior", "jr", "pleno", "mid", "i", "ii", "iii"}
            )
            key = re.sub(r"\s+", " ", key).strip()
            if key:
                clusters[key] += 1
    return [
        {"cluster": k, "jobs": n, "suggestion": f"Criar coringa para '{k}' ({n} vagas boas sem CV adequado)"}
        for k, n in clusters.most_common(5)
        if n >= 3
    ]


async def weekly_metrics(session: AsyncSession) -> dict[str, Any]:
    now = datetime.now(UTC)
    week = await funnel(session, now - timedelta(days=7), now)
    prev = await funnel(session, now - timedelta(days=14), now - timedelta(days=7))
    return {
        "week": week,
        "previous_week": prev,
        "skill_gaps": (await skill_gaps(session, 30))[:5],
        "goals": await goals(session),
        "wildcards": await wildcard_suggestions(session),
    }
