"""Fábricas de dados de teste."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from tracker.integrations.embeddings import embed_one
from tracker.modules.companies.models import Company
from tracker.modules.jobs.models import Job
from tracker.modules.profile import service as profile_service
from tracker.modules.profile.schemas import MasterProfile

FIXTURES = Path(__file__).parent / "fixtures"


def master() -> MasterProfile:
    return profile_service.load_yaml(FIXTURES / "profile" / "master.yaml")


async def seed_master(session: AsyncSession) -> MasterProfile:
    m = master()
    await profile_service.save_master(session, m, "seed_yaml", "teste")
    await session.commit()
    return m


async def company(session: AsyncSession, name: str = "Globex", **kw: Any) -> Company:
    from sqlalchemy import select

    existing = await session.scalar(select(Company).where(Company.normalized_name == name.lower()))
    if existing is not None:
        return existing
    c = Company(name=name, normalized_name=name.lower(), **kw)
    session.add(c)
    await session.flush()
    return c


async def job(session: AsyncSession, comp: Company | None = None, **kw: Any) -> Job:
    comp = comp or await company(session)
    data: dict[str, Any] = {
        "title": "Senior Data Engineer",
        "normalized_title": "senior data engineer",
        "description_text": "We need Python, Spark and Kafka experience to build pipelines. Remote.",
        "requirements": {"must": ["Python", "Spark", "Kafka"], "nice": ["Airflow"]},
        "language": "en",
        "work_model": "remote",
        "apply_kind": "easy_apply",
        "posted_at": datetime.now(UTC),
        "applicants_count": 20,
    }
    data.update(kw)
    j = Job(company_id=comp.id, **data)
    j.embedding = embed_one(f"{j.title} {j.description_text}")
    session.add(j)
    await session.flush()
    return j
