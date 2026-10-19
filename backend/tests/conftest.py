"""Fixtures globais: banco de teste real (Postgres do compose), cliente HTTP, IA fake."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

os.environ["TRACKER_NO_DOTENV"] = "1"
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://tracker:tracker@localhost:5433/tracker_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["AI_FAKE"] = "true"
os.environ["EMBEDDINGS_BACKEND"] = "hash"
os.environ["LATEX_CMD"] = os.environ.get("LATEX_CMD", "tectonic")
os.environ["AUTH_DEV_LOGIN"] = "true"
os.environ["AUTH_ALLOWED_EMAIL"] = "me@example.com"
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tracker.core import db as core_db
from tracker.core.config import get_settings
from tracker.core.security import SESSION_COOKIE, sign_session
from tracker.core.storage import LocalStorage, set_storage
from tracker.core.tasks import set_dispatcher
from tracker.integrations.claude.client import FakeAIClient, set_ai

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    os.environ["ALEMBIC_DATABASE_URL"] = get_settings().sync_database_url
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[Any]:
    eng = create_async_engine(get_settings().database_url, poolclass=NullPool)
    core_db._engine = eng
    core_db._sessionmaker = async_sessionmaker(eng, expire_on_commit=False)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
async def _clean_db(engine: Any) -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        tables = (
            (
                await conn.execute(
                    text("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'")
                )
            )
            .scalars()
            .all()
        )
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def sessionmaker(engine: Any) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as s:
        yield s


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> LocalStorage:
    st = LocalStorage(tmp_path / "storage")
    set_storage(st)
    return st


@pytest.fixture(autouse=True)
def dispatched() -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    set_dispatcher(lambda name, kwargs: calls.append((name, kwargs)))
    return calls


@pytest.fixture(autouse=True)
def ai(sessionmaker: async_sessionmaker[AsyncSession]) -> FakeAIClient:
    fake = FakeAIClient(sessionmaker)
    set_ai(fake)
    return fake


@pytest.fixture
async def client(engine: Any) -> AsyncIterator[AsyncClient]:
    from tracker.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"x-tracker-csrf": "1"},
    ) as c:
        c.cookies.set(SESSION_COOKIE, sign_session("me@example.com"))
        yield c


@pytest.fixture
async def anon_client(engine: Any) -> AsyncIterator[AsyncClient]:
    from tracker.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
