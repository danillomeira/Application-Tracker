"""Rotas de pesos da avaliação (RF-AVA-05, RF-AVA-08)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update

from tracker.api.deps import SessionDep, TaskAccepted
from tracker.core import audit
from tracker.core.security import CurrentUser
from tracker.core.tasks import enqueue
from tracker.modules.scoring import service
from tracker.modules.scoring.models import ScoringWeights

router = APIRouter(prefix="/scoring", tags=["scoring"])


class WeightsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: int
    chance_weights: dict[str, float]
    attractiveness_weights: dict[str, float]
    thresholds: dict[str, Any]
    source: str
    is_current: bool
    metrics: dict[str, Any]


class WeightsIn(BaseModel):
    chance_weights: dict[str, float]
    attractiveness_weights: dict[str, float]
    thresholds: dict[str, Any] = {}


@router.get("/weights", response_model=WeightsOut)
async def get_weights(session: SessionDep, _user: CurrentUser) -> ScoringWeights:
    w = await service.current_weights(session)
    await session.commit()
    return w


@router.get("/weights/history", response_model=list[WeightsOut])
async def history(session: SessionDep, _user: CurrentUser) -> list[ScoringWeights]:
    return list((await session.scalars(select(ScoringWeights).order_by(ScoringWeights.version.desc()))).all())


@router.put("/weights", response_model=WeightsOut)
async def put_weights(body: WeightsIn, session: SessionDep, _user: CurrentUser) -> ScoringWeights:
    from tracker.modules.scoring.features import ATTRACTIVENESS_WEIGHTS, CHANCE_WEIGHTS

    if set(body.chance_weights) - set(CHANCE_WEIGHTS) or set(body.attractiveness_weights) - set(ATTRACTIVENESS_WEIGHTS):
        raise HTTPException(422, "critério desconhecido")
    row = await service.save_weights(session, body.chance_weights, body.attractiveness_weights, body.thresholds, "user")
    await audit.record(session, actor="user", action="scoring.weights", after={"version": row.version})
    await session.commit()
    await enqueue(session, "scoring.rescore_all")
    return row


@router.post("/weights/{version}/activate", response_model=WeightsOut)
async def activate(version: int, session: SessionDep, _user: CurrentUser) -> ScoringWeights:
    row = await session.scalar(select(ScoringWeights).where(ScoringWeights.version == version))
    if row is None:
        raise HTTPException(404, "versão não encontrada")
    await session.execute(update(ScoringWeights).values(is_current=False))
    row.is_current = True
    await audit.record(session, actor="user", action="scoring.activate", after={"version": version})
    await session.commit()
    await enqueue(session, "scoring.rescore_all")
    return row


@router.post("/calibrate", response_model=TaskAccepted, status_code=202)
async def calibrate(session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    tr = await enqueue(session, "scoring.calibrate")
    return TaskAccepted(task_id=tr.id)
