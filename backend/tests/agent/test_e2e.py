"""Ponta a ponta: agente real (Playwright) + API real (ASGI) + resolvedor real.

pergunta sensível → pendência → resposta → revisão → aprovação → envio → registro imutável.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from playwright.async_api import async_playwright
from sqlalchemy import select

from tests import factories
from tracker.agent.api import HttpAgentApi
from tracker.agent.human import Pace
from tracker.agent.runner import run_once
from tracker.core import settings_store
from tracker.core.config import get_settings
from tracker.core.storage import get_storage
from tracker.integrations.claude.client import FakeAIClient
from tracker.modules.agent_gateway.models import AgentJob
from tracker.modules.applications.models import (
    Application,
    ApplicationAnswer,
    DailyQuota,
    PendingQuestion,
)
from tracker.modules.profile.models import AnswerBankEntry
from tracker.modules.profile.service import seed_defaults
from tracker.modules.resumes.models import ResumeRender, ResumeVariant

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "linkedin"


@pytest.fixture
async def setup(session):
    m = await factories.seed_master(session)
    await seed_defaults(session, m)
    await settings_store.put(session, "limits", {"window": {"days": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"}})
    job = await factories.job(session, canonical_url=(FIX / "easy_apply.html").as_uri(), apply_kind="easy_apply")
    from tracker.modules.profile.service import current_version
    from tracker.modules.resumes.content import baseline

    v = ResumeVariant(
        kind="wildcard",
        slug="de-en",
        name="Data Engineer",
        language="en",
        content=baseline(m, "data_engineer", "en").model_dump(),
        master_version=(await current_version(session)).version,
        status="approved",
        validation={"passed": True},
    )
    session.add(v)
    await session.flush()
    pdf = b"%PDF-1.4 fake"
    key = get_storage().put("resumes/x/Ana_Silva_Data_Engineer_EN.pdf", pdf)
    r = ResumeRender(
        variant_id=v.id,
        storage_key=key,
        tex_source_key=key,
        filename="Ana_Silva_Data_Engineer_EN.pdf",
        sha256=hashlib.sha256(pdf).hexdigest(),
    )
    session.add(r)
    await session.flush()
    app = Application(
        job_id=job.id,
        status="queued",
        resume_variant_id=v.id,
        resume_render_id=r.id,
        cover_letter="I build Python and Spark pipelines at Acme and want to do the same at Globex.",
    )
    session.add(app)
    await session.flush()
    session.add(
        AgentJob(
            kind="apply",
            payload={"application_id": str(app.id), "job_id": str(job.id)},
            application_id=app.id,
            priority=50,
        )
    )
    await session.commit()
    return app


async def test_agent_end_to_end(setup, session, ai: FakeAIClient, client: AsyncClient) -> None:
    app = setup
    from tracker.main import app as asgi

    api = HttpAgentApi("http://test", get_settings().agent_device_token, transport=ASGITransport(app=asgi))
    pace = Pace(scale=0)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()

        # 1ª passada: pergunta de patrocínio de visto é sensível → pendência
        out = await run_once(ctx, api, pace, {})
        assert out["result"].status == "paused"
        await session.refresh(app)
        assert app.status == "needs_input"
        pq = await session.scalar(select(PendingQuestion).where(PendingQuestion.status == "open"))
        assert "sponsorship" in pq.question_text and pq.options == ["Yes", "No"]

        # usuário responde no dashboard (vira banco de respostas)
        r = await client.post(f"/api/v1/pending-questions/{pq.id}/answer", json={"value": "No"})
        assert r.status_code == 200

        # 2ª passada: tudo resolvido → para na revisão (modo revisão padrão)
        out = await run_once(ctx, api, pace, {})
        assert out["result"].status == "review_pending"
        await session.refresh(app)
        assert app.status == "awaiting_review"
        queue = (await client.get("/api/v1/review-queue")).json()
        assert [a["id"] for a in queue] == [str(app.id)]

        # usuário aprova
        await client.post("/api/v1/review-queue/approve", json={"ids": [str(app.id)]})

        # 3ª passada: envia
        out = await run_once(ctx, api, pace, {})
        assert out["result"].status == "submitted"
        page = ctx.pages[0]
        sent = await page.evaluate("window.submitted")
        await browser.close()

    await session.refresh(app)
    assert app.status == "submitted" and app.applied_snapshot_id is not None
    assert sent["ln"] == "Teste Silva" and sent["em"] == "ana@example.com" and sent["cc"] == "Brazil (+55)"
    assert sent["ph"] == "+55 (11) 90000-0000" and sent["cv"] == "Ana_Silva_Data_Engineer_EN.pdf"
    assert sent["yp"] == "5"  # anos com Python calculados pelo mestre (nunca inventados)
    assert sent["lvl"] == "Advanced" and sent["sp"] == "No" and sent["follow"] is False
    assert sent["why"].startswith("I build Python")  # carta de apresentação da candidatura
    answers = (await session.scalars(select(ApplicationAnswer).where(ApplicationAnswer.application_id == app.id))).all()
    assert answers and all(a.locked for a in answers)
    by_q = {a.question_text: a.resolution for a in answers}
    assert by_q["Mobile phone number"] == "profile"
    assert by_q["How many years of experience do you have with Python?"] == "rule"
    assert by_q["Will you now or in the future require sponsorship for employment visa status?"] == "user"
    assert (await session.scalar(select(DailyQuota).where(DailyQuota.kind == "easy_apply"))).used == 1
    assert not [c for c in ai.calls if c.task == "apply.answer"]  # nada precisou de IA
    assert await session.scalar(select(AnswerBankEntry).where(AnswerBankEntry.canonical_question.like("%sponsorship%")))
    aj = await session.scalar(select(AgentJob))
    await session.refresh(aj)
    assert aj.status == "done" and any(a["name"] == "submitted.png" for a in aj.artifacts)


async def test_kill_switch_blocks_leasing(setup, session, client: AsyncClient) -> None:
    from tracker.main import app as asgi

    await client.post("/api/v1/agent-control/kill")
    api = HttpAgentApi("http://test", get_settings().agent_device_token, transport=ASGITransport(app=asgi))
    r = await api.next_job()
    assert "parado" in r["wait"]
    await client.post("/api/v1/agent-control/resume")
    r = await api.next_job()
    assert r["job"]["kind"] == "apply"
    hb = await api.heartbeat(r["job"]["id"])
    assert hb["kill"] is False
    await client.post("/api/v1/agent-control/kill")
    assert (await api.heartbeat(r["job"]["id"]))["kill"] is True


async def test_agent_requires_device_token(anon_client: AsyncClient) -> None:
    r = await anon_client.post("/api/v1/agent/jobs/next", json={}, headers={"Authorization": "Device errado"})
    assert r.status_code == 401
