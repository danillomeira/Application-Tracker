"""Perfil de empresa via pesquisa web do Claude, com cache (RF-AVA-06, ADR-010)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from tracker.core import settings_store
from tracker.core.tasks import dispatch
from tracker.integrations.claude.client import WEB_FETCH_TOOL, WEB_SEARCH_TOOL, AIRequest, get_ai, load_prompt
from tracker.modules.companies.models import Company, CompanyProfile
from tracker.modules.companies.schemas import CompanyProfileContent
from tracker.modules.jobs.models import Job
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, progress, tracked

CACHE_DAYS = 45


def drop_unsourced(content: CompanyProfileContent, found_urls: set[str]) -> CompanyProfileContent:
    """Remove afirmações sem fonte (docs/08 §5). Fontes válidas: as retornadas pela pesquisa ou listadas."""
    valid = found_urls | {s.url for s in content.sources}

    def ok(urls: list[str]) -> bool:
        return any(u in valid for u in urls) if valid else bool(urls)

    content.history = [c for c in content.history if c.source_urls and ok(c.source_urls)]
    content.values = [c for c in content.values if c.source_urls and ok(c.source_urls)]
    content.news = [c for c in content.news if c.source_urls and ok(c.source_urls)]
    return content


async def get_or_build_profile(
    sm: SM, company_id: str, force: bool = False, task_run_id: str | None = None
) -> CompanyProfile | None:
    async with sm() as s:
        c = await s.get(Company, uuid.UUID(company_id))
        assert c is not None
        if not await settings_store.flag(s, "company_research"):
            return None
        cached = await s.scalar(
            select(CompanyProfile)
            .where(CompanyProfile.company_id == c.id, CompanyProfile.expires_at > datetime.now(UTC))
            .order_by(CompanyProfile.collected_at.desc())
            .limit(1)
        )
        if cached and not force:
            return cached
        name, website, domains = c.name, c.website, list(c.domains or [])
    await progress(sm, task_run_id, 15, f"pesquisando {name}")
    user = (
        f"Empresa: {name}\nSite: {website or (domains[0] if domains else 'desconhecido')}\n"
        "Pesquise e preencha o perfil. Cite as fontes de cada afirmação."
    )
    res = await get_ai(sm).structured(
        AIRequest(
            task="company.profile",
            system=load_prompt("company.profile"),
            user=user,
            effort="high",
            tools=[WEB_SEARCH_TOOL, WEB_FETCH_TOOL],
            entity_type="company",
            entity_id=uuid.UUID(company_id),
        ),
        CompanyProfileContent,
    )
    content = drop_unsourced(res.output, {s["url"] for s in res.sources})
    async with sm() as s:
        c = await s.get(Company, uuid.UUID(company_id))
        assert c is not None
        row = CompanyProfile(
            company_id=c.id,
            content=content.model_dump(mode="json"),
            sources=[*[x.model_dump() for x in content.sources], *res.sources],
            expires_at=datetime.now(UTC) + timedelta(days=CACHE_DAYS),
            model=res.model,
        )
        s.add(row)
        c.sector = c.sector or content.sector
        c.size_range = c.size_range or content.size_range
        c.hq_location = c.hq_location or content.hq_location
        job_ids = (await s.scalars(select(Job.id).where(Job.company_id == c.id, Job.status == "open"))).all()
        await s.commit()
    for jid in job_ids:  # perfil novo muda a atratividade
        dispatch("scoring.score_job", job_id=str(jid))
    return row


async def _profile(sm: SM, task_run_id: str | None, company_id: str, force: bool = False) -> dict[str, Any]:
    row = await get_or_build_profile(sm, company_id, force, task_run_id)
    return {"profile_id": str(row.id) if row else None}


celery_app.task(name="ai.company_profile")(tracked("ai.company_profile")(_profile))
