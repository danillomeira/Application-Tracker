"""Utilitários para tarefas Celery executarem código async com sessões próprias."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tracker.core import events
from tracker.core.db import worker_sessionmaker
from tracker.modules.platform.models import TaskRun

SM = async_sessionmaker[AsyncSession]


def run[T](fn: Callable[[SM], Awaitable[T]]) -> T:
    async def main() -> T:
        sm = worker_sessionmaker()
        try:
            return await fn(sm)
        finally:
            engine = sm.kw.get("bind")
            if engine is not None:
                await engine.dispose()

    return asyncio.run(main())


async def create_task_run(
    session: AsyncSession,
    kind: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> TaskRun:
    tr = TaskRun(kind=kind, status="pending", entity_type=entity_type, entity_id=entity_id)
    session.add(tr)
    await session.flush()
    return tr


async def progress(
    sm: SM,
    task_run_id: str | uuid.UUID | None,
    pct: int,
    message: str,
    status: str = "running",
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    if task_run_id is None:
        return
    async with sm() as s:
        tr = await s.get(TaskRun, uuid.UUID(str(task_run_id)))
        if tr is None:
            return
        tr.progress, tr.message, tr.status = pct, message, status
        if result is not None:
            tr.result = result
        if error is not None:
            tr.error = error
        await s.commit()
        kind = tr.kind
    type_ = {"done": "task.done", "failed": "task.failed"}.get(status, "task.progress")
    await events.apublish(
        "tasks",
        type_,
        {
            "task_id": str(task_run_id),
            "kind": kind,
            "pct": pct,
            "message": message,
            "result": result,
            "error": error,
        },
    )


def tracked(kind: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Any]]:
    """Envolve uma função async (sm, task_run_id, **kw) em execução rastreada."""

    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Any]:
        def wrapper(task_run_id: str | None = None, **kwargs: Any) -> Any:
            async def body(sm: SM) -> Any:
                await progress(sm, task_run_id, 1, "iniciado")
                try:
                    result = await fn(sm, task_run_id, **kwargs)
                except Exception as exc:
                    await progress(sm, task_run_id, 100, "falhou", status="failed", error=str(exc)[:2000])
                    raise
                await progress(
                    sm,
                    task_run_id,
                    100,
                    "concluído",
                    status="done",
                    result=result if isinstance(result, dict) else None,
                )
                return result

            return run(body)

        wrapper.__name__ = fn.__name__
        wrapper.__qualname__ = kind
        return wrapper

    return deco
