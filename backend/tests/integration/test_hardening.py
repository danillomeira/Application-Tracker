"""Proteções da revisão: login de dev só local, Host confiável, cookie fora da extensão, registro idempotente."""

from __future__ import annotations

import hashlib

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from tests import factories
from tracker.core import settings_store
from tracker.core.security import SESSION_COOKIE, sign_session
from tracker.modules.applications import service as app_service
from tracker.modules.jobs.models import JobSnapshot


async def test_untrusted_host_is_rejected(engine) -> None:
    from tracker.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://evil.example") as c:
        assert (await c.get("/api/v1/health")).status_code == 400  # DNS rebinding
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost:8000") as c:
        assert (await c.get("/api/v1/health")).status_code == 200


async def test_dev_login_only_from_this_machine(engine, monkeypatch) -> None:
    from tracker.core.config import get_settings
    from tracker.main import app

    monkeypatch.setattr(get_settings(), "auth_dev_login", True)
    local = ASGITransport(app=app, client=("127.0.0.1", 5555))
    async with AsyncClient(transport=local, base_url="http://localhost") as c:
        r = await c.post("/api/v1/auth/dev-login")
        assert r.status_code == 303 and SESSION_COOKIE in r.cookies
    remote = ASGITransport(app=app, client=("192.168.0.50", 5555))
    async with AsyncClient(transport=remote, base_url="http://localhost") as c:
        assert (await c.post("/api/v1/auth/dev-login")).status_code == 403


async def test_assistant_cookie_not_usable_by_other_extensions(engine, session) -> None:
    from tracker.main import app

    await settings_store.put(session, "extension", {"token_sha256": hashlib.sha256(b"tok").hexdigest()})
    await session.commit()
    body = {"url": "https://example.com/x", "title": "x", "text": ""}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.cookies.set(SESSION_COOKIE, sign_session("me@example.com"))
        # outra extensão com o cookie do dashboard: recusado
        r = await c.post("/api/v1/assistant/page", json=body, headers={"origin": "chrome-extension://abc", "x-tracker-csrf": "1"})
        assert r.status_code == 401
        # escrita com cookie mas sem o header CSRF: recusado
        assert (await c.post("/api/v1/assistant/page", json=body)).status_code == 401
        # token certo: aceito
        r = await c.post("/api/v1/assistant/page", json=body, headers={"authorization": "Extension tok"})
        assert r.status_code == 200
        # token errado não cai para o cookie
        r = await c.post("/api/v1/assistant/page", json=body, headers={"authorization": "Extension nope", "x-tracker-csrf": "1"})
        assert r.status_code == 401


async def test_register_submission_is_idempotent(session) -> None:
    await factories.seed_master(session)
    job = await factories.job(session)
    app = await app_service.create_for_job(session, job, actor="user")
    await app_service.register_submission(session, app, actor="user", channel="assisted")
    first = app.submitted_at
    await app_service.register_submission(session, app, actor="user", channel="email")
    await session.commit()
    snaps = await session.scalar(select(func.count()).select_from(JobSnapshot).where(JobSnapshot.job_id == job.id))
    assert snaps == 1 and app.submitted_at == first and app.channel == "assisted"


async def test_skip_can_be_undone(client: AsyncClient, session) -> None:
    job = await factories.job(session)
    await session.commit()
    assert (await client.post(f"/api/v1/jobs/{job.id}/skip")).status_code == 200
    assert (await client.post(f"/api/v1/jobs/{job.id}/restore")).status_code == 200
    await session.refresh(job)
    assert job.triage == "new"


async def test_saved_search_put_validates_cron(client: AsyncClient) -> None:
    body = {"name": "x", "query": "data", "sources": ["boards"], "schedule_cron": "0 9 * * 1-5", "filters": {}}
    r = await client.post("/api/v1/saved-searches", json=body)
    assert r.status_code == 201
    r = await client.put(f"/api/v1/saved-searches/{r.json()['id']}", json={**body, "schedule_cron": "nunca"})
    assert r.status_code == 422


async def test_multiple_quadrants_filter(client: AsyncClient) -> None:
    r = await client.get("/api/v1/jobs?quadrant=top&quadrant=bet")
    assert r.status_code == 200


async def test_assistant_tailor_flow(anon_client: AsyncClient, session, dispatched) -> None:
    from tracker.modules.resumes.content import baseline
    from tracker.modules.resumes.models import ResumeVariant

    m = await factories.seed_master(session)
    await settings_store.put(session, "extension", {"token_sha256": hashlib.sha256(b"tok").hexdigest()})
    job = await factories.job(session, canonical_url="https://jobs.example.com/de-1")
    await session.commit()
    h = {"authorization": "Extension tok"}
    r = await anon_client.post("/api/v1/assistant/tailor", json={"job_id": str(job.id)}, headers=h)
    assert r.status_code == 202 and dispatched[-1][0] == "ai.resume_tailor"
    task = await anon_client.get(f"/api/v1/assistant/tasks/{r.json()['task_id']}", headers=h)
    assert task.json()["status"] == "pending"
    from tracker.modules.profile.service import current_version

    v = ResumeVariant(kind="tailored", slug="t1", name="t", language="en", status="draft", job_id=job.id,
                      content=baseline(m, "data_engineer", "en").model_dump(), master_version=(await current_version(session)).version,
                      validation={"passed": True})  # fmt: skip
    session.add(v)
    await session.commit()
    page = await anon_client.post("/api/v1/assistant/page", json={"url": job.canonical_url, "title": "", "text": ""}, headers=h)
    assert page.json()["tailored"]["status"] == "draft"
    ok = await anon_client.post(f"/api/v1/assistant/tailored/{v.id}/approve", headers=h)
    assert ok.status_code == 200 and ok.json()["tailored"]["status"] == "approved"


async def test_auto_tailor_when_form_opens(anon_client: AsyncClient, session, dispatched) -> None:
    """Formulário aberto numa vaga top sem CV sob medida: a geração começa sozinha, uma vez só."""
    from tracker.modules.scoring.models import JobScore

    await factories.seed_master(session)
    await settings_store.put(session, "extension", {"token_sha256": hashlib.sha256(b"tok").hexdigest()})
    job = await factories.job(session, canonical_url="https://jobs.example.com/top-1")
    session.add(JobScore(job_id=job.id, chance=80, attractiveness=80, priority=80, quadrant="top", is_current=True,
                         explanation={}, chance_breakdown={}, attractiveness_breakdown={}, weights_version=1, master_version=1))  # fmt: skip
    await session.commit()
    h = {"authorization": "Extension tok"}
    body = {"url": job.canonical_url, "title": "", "text": "", "has_form": True}
    first = (await anon_client.post("/api/v1/assistant/page", json=body, headers=h)).json()
    assert first["tailor_task"] and [n for n, _ in dispatched].count("ai.resume_tailor") == 1
    again = (await anon_client.post("/api/v1/assistant/page", json=body, headers=h)).json()
    assert again["tailor_task"] == first["tailor_task"]  # a mesma geração, sem duplicar
    assert [n for n, _ in dispatched].count("ai.resume_tailor") == 1
    browse = (await anon_client.post("/api/v1/assistant/page", json={**body, "has_form": False}, headers=h)).json()
    assert "tailor_task" not in browse  # só olhando a vaga: não gasta IA
