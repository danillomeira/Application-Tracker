"""Dependências comuns das rotas."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core.db import get_session, get_sessionmaker
from tracker.integrations.claude.client import AIClient, get_ai

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def ai_dep() -> AIClient:
    return get_ai(get_sessionmaker())


AIDep = Annotated[AIClient, Depends(ai_dep)]


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class TaskAccepted(BaseModel):
    task_id: uuid.UUID


def _encode_cursor(ts: datetime, id_: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([ts.isoformat(), str(id_)]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, id_ = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(ts), uuid.UUID(id_)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cursor inválido") from exc


async def paginate(
    session: AsyncSession,
    stmt: Select[Any],
    model: Any,
    cursor: str | None,
    limit: int,
    order_col: Any = None,
) -> tuple[list[Any], str | None]:
    """Paginação por cursor em (coluna de ordenação desc, id desc)."""
    limit = max(1, min(limit, 200))
    col = order_col if order_col is not None else model.created_at
    if cursor:
        ts, id_ = _decode_cursor(cursor)
        stmt = stmt.where(or_(col < ts, and_(col == ts, model.id < id_)))
    rows = list((await session.scalars(stmt.order_by(col.desc(), model.id.desc()).limit(limit + 1))).all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(getattr(last, col.key), last.id)
    return rows, next_cursor


async def get_or_404[M](session: AsyncSession, model: type[M], id_: uuid.UUID) -> M:
    obj = await session.get(model, id_)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} não encontrado")
    return obj


__all__ = ["select"]
