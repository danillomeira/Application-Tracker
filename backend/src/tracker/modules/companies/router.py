"""Rotas de empresas (watchlist, monitoramento, perfil)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select

from tracker.api.deps import SessionDep, TaskAccepted, get_or_404
from tracker.core.security import CurrentUser
from tracker.core.tasks import dispatch, enqueue
from tracker.modules.applications.models import Application
from tracker.modules.companies import service
from tracker.modules.companies.models import Company
from tracker.modules.companies.schemas import CompanyDetail, CompanyIn, CompanyOut, CompanyUpdate
from tracker.modules.jobs.models import Job
from tracker.modules.scoring.service import company_profile, responsiveness

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyOut])
async def list_companies(
    session: SessionDep,
    _user: CurrentUser,
    watchlisted: bool | None = None,
    monitored: bool | None = None,
    q: str | None = None,
) -> list[Company]:
    stmt = select(Company).order_by(Company.name)
    if watchlisted is not None:
        stmt = stmt.where(Company.is_watchlisted.is_(watchlisted))
    if monitored is not None:
        stmt = stmt.where(Company.is_monitored.is_(monitored))
    if q:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))
    return list((await session.scalars(stmt.limit(500))).all())


@router.post("", response_model=CompanyOut, status_code=201)
async def create_company(body: CompanyIn, session: SessionDep, _user: CurrentUser) -> Company:
    domain = None
    if body.website:
        domain = body.website.split("//")[-1].split("/")[0].removeprefix("www.")
    c = await service.get_or_create(session, body.name, domain=domain)
    for k, v in body.model_dump(exclude={"name"}).items():
        if v is not None:
            setattr(c, k, v)
    await session.commit()
    if c.is_monitored and c.ats_board_token:
        dispatch("ingest.poll_company", company_id=str(c.id))
    return c


@router.get("/logo")
async def logo_by_name(name: str, session: SessionDep, _user: CurrentUser) -> Response:
    """Logo pelo nome da empresa (para telas que só têm o nome). 404 = sem logo; o dashboard mostra as iniciais."""
    from tracker.modules.companies.logos import logo_by_name as find

    data = await find(session, name[:200])
    if data is None:
        raise HTTPException(404, "sem logo")
    kind = "image/png" if data[:4] == b"\x89PNG" else "image/x-icon"
    return Response(data, media_type=kind, headers={"Cache-Control": "private, max-age=604800"})


@router.get("/{company_id}", response_model=CompanyDetail)
async def get_company(company_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> CompanyDetail:
    c = await get_or_404(session, Company, company_id)
    out = CompanyDetail.model_validate(c)
    prof, row = await company_profile(session, c.id)
    if row is not None:
        out.profile = row.content
        out.profile_collected_at = row.collected_at
    _, info = await responsiveness(session, c.id, prof)
    out.responsiveness = info
    out.open_jobs = (
        await session.scalar(select(func.count()).select_from(Job).where(Job.company_id == c.id, Job.status == "open")) or 0
    )
    out.applications = (
        await session.scalar(
            select(func.count()).select_from(Application).join(Job, Job.id == Application.job_id).where(Job.company_id == c.id)
        )
        or 0
    )
    return out


@router.put("/{company_id}", response_model=CompanyOut)
async def update_company(company_id: uuid.UUID, body: CompanyUpdate, session: SessionDep, _user: CurrentUser) -> Company:
    c = await get_or_404(session, Company, company_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    await session.commit()
    if c.is_monitored and c.ats_board_token:
        dispatch("ingest.poll_company", company_id=str(c.id))
    return c


@router.post("/{company_id}/poll", status_code=202)
async def poll(company_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> dict[str, str]:
    await get_or_404(session, Company, company_id)
    dispatch("ingest.poll_company", company_id=str(company_id))
    return {"status": "queued"}


@router.post("/{company_id}/refresh-profile", response_model=TaskAccepted, status_code=202)
async def refresh_profile(company_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    await get_or_404(session, Company, company_id)
    tr = await enqueue(
        session,
        "ai.company_profile",
        entity_type="company",
        entity_id=company_id,
        company_id=str(company_id),
        force=True,
    )
    return TaskAccepted(task_id=tr.id)


@router.post("/seed-defaults")
async def seed_default_companies(session: SessionDep, _user: CurrentUser, monitor: bool = True) -> dict[str, int]:
    """Importa as empresas com board público verificado (seeds/companies.yaml)."""
    created = await seed_companies(session, monitor)
    await session.commit()
    return created


async def seed_companies(session: SessionDep, monitor: bool = True) -> dict[str, int]:
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[1] / "jobs" / "seeds" / "companies.yaml"  # noqa: ASYNC240
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    added = updated = 0
    for item in data.get("companies", []):
        existed = await session.scalar(
            select(Company.id).where(Company.normalized_name == service.normalize_company(item["name"]))
        )
        c = await service.get_or_create(session, item["name"])
        if not c.ats_board_token:
            c.ats_kind, c.ats_board_token = item["ats_kind"], item["ats_board_token"]
        c.is_monitored = c.is_monitored or monitor
        c.hq_location = c.hq_location or ("Brasil" if item.get("region") == "BR" else "Internacional")
        if item.get("domain") and not c.domains:
            c.domains = [item["domain"]]
        added += existed is None
        updated += existed is not None
    return {"added": added, "updated": updated}


@router.get("/{company_id}/logo")
async def logo(company_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    """Ícone do site da empresa (cache no storage). 404 quando não há: o dashboard mostra as iniciais."""
    from tracker.modules.companies.logos import company_logo

    company = await get_or_404(session, Company, company_id)
    data = await company_logo(session, company)
    if data is None:
        raise HTTPException(404, "sem logo")
    kind = "image/png" if data[:4] == b"\x89PNG" else "image/x-icon"
    return Response(data, media_type=kind, headers={"Cache-Control": "private, max-age=604800"})
