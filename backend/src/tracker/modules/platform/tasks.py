"""Tarefas da plataforma: ping de demonstração, backup, retenção de artefatos."""

from __future__ import annotations

import asyncio
import gzip
import io
import logging
import os
import shlex
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from typing import Any

from tracker.core.config import get_settings
from tracker.core.crypto import encrypt
from tracker.core.storage import get_storage
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, progress, tracked

log = logging.getLogger(__name__)


async def _ping(sm: SM, task_run_id: str | None, steps: int = 5) -> dict[str, Any]:
    for i in range(1, steps + 1):
        await asyncio.sleep(0.5)
        await progress(sm, task_run_id, int(i / steps * 95), f"passo {i} de {steps}")
    return {"pong": True, "steps": steps}


celery_app.task(name="platform.ping")(tracked("platform.ping")(_ping))


def _plain_db_url() -> str:
    return get_settings().sync_database_url.replace("postgresql+psycopg://", "postgresql://")


def make_backup() -> dict[str, Any]:
    """pg_dump + arquivos (storage local), comprimidos e criptografados (RF-PLA-06)."""
    s = get_settings()
    storage = get_storage()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    cmd = s.backup_pg_dump_cmd
    args = shlex.split(cmd, posix=os.name != "nt") + ([] if "pg_dump -U" in cmd else [f"--dbname={_plain_db_url()}"])
    dump = subprocess.run(args, check=True, capture_output=True, timeout=600).stdout  # noqa: S603
    db_key = storage.put(f"backups/{stamp}/db.sql.gz.enc", encrypt(gzip.compress(dump)))
    keys = [db_key]
    if s.storage_backend == "local":
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for key in storage.list(""):
                if key.startswith("backups/"):
                    continue
                data = storage.get(key)
                info = tarfile.TarInfo(name=key)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        keys.append(storage.put(f"backups/{stamp}/files.tar.gz.enc", encrypt(buf.getvalue())))
    cutoff = datetime.now(UTC) - timedelta(days=s.backup_retention_days)
    removed = 0
    for key in storage.list("backups/"):
        try:
            when = datetime.strptime(key.split("/")[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except (IndexError, ValueError):
            continue
        if when < cutoff:
            storage.delete(key)
            removed += 1
    log.info("backup concluído", extra={"keys": keys, "removed": removed})
    return {"keys": keys, "removed": removed, "db_bytes": len(dump)}


@celery_app.task(name="platform.backup")
def backup() -> dict[str, Any]:
    return make_backup()


@celery_app.task(name="platform.artifact_retention")
def artifact_retention() -> int:
    """Screenshots/HTML do agente: retenção de 30 dias (docs/12 §4)."""
    storage = get_storage()
    cutoff = datetime.now(UTC) - timedelta(days=30)
    removed = 0
    for key in storage.list("agent-artifacts/"):
        parts = key.split("/")
        try:
            day = datetime.strptime(parts[1], "%Y-%m-%d").replace(tzinfo=UTC)
        except (IndexError, ValueError):
            continue
        if day < cutoff:
            storage.delete(key)
            removed += 1
    return removed
