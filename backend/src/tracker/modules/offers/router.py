"""Ofertas: registro, comparação CLT x PJ, referência salarial e negociação (RF-OFE)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from tracker.api.deps import SessionDep, TaskAccepted, get_or_404
from tracker.core.security import CurrentUser
from tracker.core.tasks import enqueue
from tracker.modules.applications import service as app_service
from tracker.modules.applications.models import Application
from tracker.modules.offers import compare
from tracker.modules.offers.models import Offer

router = APIRouter(prefix="/offers", tags=["offers"])


class OfferIn(BaseModel):
    application_id: uuid.UUID | None = None
    company_name: str
    regime: Literal["CLT", "PJ"]
    base_salary: float
    currency: str = "BRL"
    period: Literal["month", "year"] = "month"
    bonus: dict[str, Any] = Field(default_factory=dict)  # {"annual": 10000, "plr": 5000}
    benefits: dict[str, Any] = Field(default_factory=dict)  # {"vr_va": 1200, "saude": 600, ...} mensais
    equity: dict[str, Any] = Field(default_factory=dict)
    work_model: str | None = None
    start_date: date | None = None
    respond_by: datetime | None = None
    premises: dict[str, Any] = Field(default_factory=dict)


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    application_id: uuid.UUID | None
    company_name: str
    regime: str
    base_salary: float
    currency: str
    period: str
    bonus: dict[str, Any]
    benefits: dict[str, Any]
    equity: dict[str, Any]
    work_model: str | None
    start_date: date | None
    respond_by: datetime | None
    annualized: dict[str, Any]
    negotiation: dict[str, Any] | None
    status: str


# Chaves especiais em `bonus` (não somadas como bônus em dinheiro).
SPECIAL_BONUS = {"plr_salaries", "pension_employee_rate", "pension_match_rate", "pension_match_cap"}
SPECIAL_BENEFITS = {"employee_costs_monthly"}  # custos pagos pelo funcionário (ex.: coparticipação do plano)


def _annualize(o: OfferIn | Offer, premises: dict[str, Any] | None = None) -> dict[str, Any]:
    ben = o.benefits or {}
    bon = o.bonus or {}
    benefits = sum(float(v) for k, v in ben.items() if isinstance(v, int | float) and k not in SPECIAL_BENEFITS)
    bonus = sum(float(v) for k, v in bon.items() if isinstance(v, int | float) and k not in SPECIAL_BONUS)
    return compare.annualize(
        o.regime,
        o.base_salary,
        o.period,
        benefits,
        bonus,
        premises,
        plr_salaries=float(bon.get("plr_salaries") or 0),
        pension_employee_rate=float(bon.get("pension_employee_rate") or 0),
        pension_match_rate=float(bon.get("pension_match_rate") or 0),
        pension_match_cap=float(bon.get("pension_match_cap") or 0),
        employee_costs_monthly=float(ben.get("employee_costs_monthly") or 0),
    )


async def _current(session: SessionDep, premises: dict[str, Any] | None = None) -> dict[str, Any] | None:
    from tracker.core import settings_store

    cfg = await settings_store.get(session, "current_compensation")
    if not cfg.get("monthly_gross"):
        return None
    return {"config": cfg, "annualized": compare.current_package(cfg, premises)}


@router.get("/current")
async def current(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    """Remuneração atual (linha de base). Editar via PUT /settings/current_compensation."""
    from tracker.core import settings_store

    data = await _current(session)
    return data or {"config": await settings_store.get(session, "current_compensation"), "annualized": None}


@router.get("", response_model=list[OfferOut])
async def list_offers(session: SessionDep, _user: CurrentUser) -> list[Offer]:
    return list((await session.scalars(select(Offer).order_by(Offer.created_at.desc()))).all())


@router.post("", response_model=OfferOut, status_code=201)
async def create_offer(body: OfferIn, session: SessionDep, _user: CurrentUser) -> Offer:
    o = Offer(**body.model_dump(exclude={"premises"}), annualized=_annualize(body, body.premises))
    session.add(o)
    if body.application_id:
        app = await get_or_404(session, Application, body.application_id)
        if app.status != "offer":
            try:
                await app_service.transition(session, app, "offer", actor="user", reason="proposta registrada")
            except Exception:  # noqa: S110
                pass
    await session.commit()
    return o


@router.put("/{offer_id}", response_model=OfferOut)
async def update_offer(offer_id: uuid.UUID, body: OfferIn, session: SessionDep, _user: CurrentUser) -> Offer:
    o = await get_or_404(session, Offer, offer_id)
    for k, v in body.model_dump(exclude={"premises"}).items():
        setattr(o, k, v)
    o.annualized = _annualize(body, body.premises)
    await session.commit()
    return o


class StatusIn(BaseModel):
    status: Literal["received", "negotiating", "accepted", "declined"]


@router.post("/{offer_id}/status", response_model=OfferOut)
async def set_status(offer_id: uuid.UUID, body: StatusIn, session: SessionDep, _user: CurrentUser) -> Offer:
    o = await get_or_404(session, Offer, offer_id)
    o.status = body.status
    if o.application_id and body.status in ("accepted", "declined"):
        app = await session.get(Application, o.application_id)
        if app and app.status == "offer":
            await app_service.transition(session, app, body.status, actor="user")
    await session.commit()
    return o


class CompareIn(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list)
    premises: dict[str, Any] = Field(default_factory=dict)


@router.post("/compare")
async def compare_offers(body: CompareIn, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    stmt = select(Offer)
    if body.ids:
        stmt = stmt.where(Offer.id.in_(body.ids))
    offers = (await session.scalars(stmt)).all()
    rows = []
    for o in offers:
        a = _annualize(o, body.premises)
        rows.append(
            {
                "id": str(o.id),
                "company": o.company_name,
                "regime": o.regime,
                "annual_net": a["annual_net"],
                "monthly_equivalent": a["monthly_equivalent"],
                "work_model": o.work_model,
                "respond_by": o.respond_by.isoformat() if o.respond_by else None,
                "detail": a,
            }
        )
    rows.sort(key=lambda r: -r["annual_net"])
    baseline = await _current(session, body.premises)
    if baseline:
        base = baseline["annualized"]["annual_net"]
        for r in rows:
            r["vs_current_annual"] = round(r["annual_net"] - base, 2)
            r["vs_current_pct"] = round((r["annual_net"] / base - 1) * 100, 1) if base else None
    return {"offers": rows, "current": baseline, "premises": {**compare.DEFAULT_PREMISES, **body.premises}}


class SimulateIn(BaseModel):
    regime: Literal["CLT", "PJ"]
    monthly: float
    benefits_monthly: float = 0.0
    bonus_annual: float = 0.0
    premises: dict[str, Any] = Field(default_factory=dict)


@router.post("/simulate")
async def simulate(body: SimulateIn, _user: CurrentUser) -> dict[str, Any]:
    return compare.annualize(body.regime, body.monthly, "month", body.benefits_monthly, body.bonus_annual, body.premises)


@router.post("/{offer_id}/negotiation", response_model=TaskAccepted, status_code=202)
async def negotiation(offer_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    await get_or_404(session, Offer, offer_id)
    tr = await enqueue(session, "ai.offer_negotiation", entity_type="offer", entity_id=offer_id, offer_id=str(offer_id))
    return TaskAccepted(task_id=tr.id)
