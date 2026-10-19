"""Referência salarial e roteiro de negociação (RF-OFE-03/04)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from tracker.integrations.claude.client import WEB_SEARCH_TOOL, AIRequest, get_ai, load_prompt
from tracker.modules.companies.schemas import SourceRef
from tracker.modules.offers.models import Offer
from tracker.modules.profile import service as profile_service
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, tracked


class MarketRange(BaseModel):
    low: float | None = None
    median: float | None = None
    high: float | None = None
    currency: str = "BRL"
    period: str = "month"
    regime: str | None = None
    notes: str | None = None


class NegotiationPlan(BaseModel):
    market: MarketRange
    position: str = Field(description="como a proposta se compara ao mercado e às outras propostas")
    target: float | None = None
    walk_away: float | None = None
    anchors: list[str] = Field(description="argumentos com base em fatos do perfil e do mercado")
    script: list[str] = Field(description="frases sugeridas para a conversa, em ordem")
    non_salary_levers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    sources: list[SourceRef]


async def _negotiation(sm: SM, task_run_id: str | None, offer_id: str) -> dict[str, Any]:
    async with sm() as s:
        offer = await s.get(Offer, uuid.UUID(offer_id))
        assert offer is not None
        others = (await s.scalars(select(Offer).where(Offer.id != offer.id, Offer.status != "declined"))).all()
        _, master = await profile_service.current_master(s)
        prefs = await profile_service.get_preferences(s)
    user = (
        f"<offer>{offer.company_name}: {offer.regime} {offer.currency} {offer.base_salary}/{offer.period}; "
        f"benefícios {offer.benefits}; bônus {offer.bonus}; anual líquido estimado {offer.annualized.get('annual_net')}</offer>\n"
        f"<other_offers>{[(o.company_name, o.regime, o.base_salary, o.annualized.get('annual_net')) for o in others]}</other_offers>\n"
        f"Pretensão do candidato: {prefs.salary_expectation} · mínimo: {prefs.min_salary}\n"
        f"Cargo/senioridade: {next(iter(master.headlines.values()), '')}. Local: {master.contact.location}."
    )
    res = await get_ai(sm).structured(
        AIRequest(
            task="offer.negotiation",
            system=load_prompt("offer.negotiation"),
            context="<profile>\n" + master.model_dump_json(exclude_none=True) + "\n</profile>",
            user=user,
            effort="high",
            tools=[{**WEB_SEARCH_TOOL, "max_uses": 6}],
            entity_type="offer",
            entity_id=uuid.UUID(offer_id),
        ),
        NegotiationPlan,
    )
    async with sm() as s:
        offer = await s.get(Offer, uuid.UUID(offer_id))
        assert offer is not None
        offer.negotiation = {**res.output.model_dump(mode="json"), "search_sources": res.sources}
        offer.status = "negotiating" if offer.status == "received" else offer.status
        await s.commit()
    return {"ok": True}


celery_app.task(name="ai.offer_negotiation")(tracked("ai.offer_negotiation")(_negotiation))
