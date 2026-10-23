"""Despacho de tarefas assíncronas a partir da API (202 + task_id). Substituível em testes."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from tracker.modules.platform.models import TaskRun

Dispatcher = Callable[[str, dict[str, Any]], None]


def _celery_dispatch(name: str, kwargs: dict[str, Any]) -> None:
    from tracker.workers.celery_app import celery_app

    celery_app.send_task(name, kwargs=kwargs)


_dispatcher: Dispatcher = _celery_dispatch


def set_dispatcher(fn: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = fn or _celery_dispatch


def dispatch(name: str, **kwargs: Any) -> None:
    _dispatcher(name, kwargs)


_PENDING = "tracker_pending_dispatch"


def dispatch_after_commit(session: AsyncSession, name: str, **kwargs: Any) -> None:
    """Envia a tarefa só depois do commit (o worker precisa enxergar as linhas). Rollback = não envia."""
    session.sync_session.info.setdefault(_PENDING, []).append((name, kwargs))


@event.listens_for(Session, "after_commit")
def _flush_pending(s: Session) -> None:
    for name, kwargs in s.info.pop(_PENDING, []):
        _dispatcher(name, kwargs)


@event.listens_for(Session, "after_rollback")
def _drop_pending(s: Session) -> None:
    s.info.pop(_PENDING, None)


async def enqueue(
    session: AsyncSession,
    name: str,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    **kwargs: Any,
) -> TaskRun:
    """Cria o TaskRun, confirma a transação e envia a tarefa."""
    tr = TaskRun(kind=name, status="pending", entity_type=entity_type, entity_id=entity_id)
    session.add(tr)
    await session.commit()
    dispatch(name, task_run_id=str(tr.id), **kwargs)
    return tr
