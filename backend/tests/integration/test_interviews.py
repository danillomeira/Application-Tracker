from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from tests import factories
from tracker.integrations.claude.client import FakeAIClient
from tracker.modules.applications.models import Application
from tracker.modules.calendar.models import CalendarEvent
from tracker.modules.companies.models import CompanyProfile
from tracker.modules.interviews.models import InterviewDossier, InterviewQuestionLog
from tracker.modules.interviews.service import build_dossier

SRC = "https://globex.com/about"

COMPANY_PROFILE = {
    "summary": "Globex faz software de logística.",
    "history": [{"text": "Fundada em 2010", "source_urls": [SRC]}],
    "mission": "Mover o mundo",
    "values": [{"text": "Ownership", "source_urls": [SRC]}],
    "products": ["Routing"],
    "reputation": {"rating": 4.3, "rating_trend_12m": 0.2},
    "culture_positive": ["autonomia"],
    "culture_alerts": [],
    "headcount_growth_12m": 0.2,
    "layoffs_12m": False,
    "is_product_company": True,
    "sources": [{"url": SRC, "title": "Sobre"}],
}


def dossier(**over) -> dict:
    base = {
        "job_summary": {
            "responsibilities": ["pipelines"],
            "must": ["Python"],
            "nice": [],
            "what_team_values": ["dono"],
        },
        "match": [
            {"requirement": "Python", "experience_id": "acme", "what_to_say": "12 pipelines em Python"},
            {"requirement": "Go", "experience_id": "inventado", "what_to_say": "x"},
        ],
        "gaps": [{"requirement": "Go", "honest_approach": "estudando"}],
        "company": {
            "overview": "Logística",
            "history": [{"text": "Fundada em 2010", "source_urls": [SRC]}, {"text": "Sem fonte", "source_urls": []}],
            "products": ["Routing"],
            "news": [{"text": "Rumor", "source_urls": ["https://fake.example"]}],
        },
        "mission": "Mover o mundo",
        "values": [{"value": "Ownership", "how_to_connect": "Fui dono dos pipelines na Acme", "source_urls": [SRC]}],
        "likely_questions": [{"question": "Fale de um pipeline", "type": "technical", "answer_outline": "Acme..."}],
        "questions_to_ask": ["Como medem sucesso?"],
        "logistics": {"when": "terça 14h", "link": "https://meet"},
        "points_to_defend": ["4+ anos"],
        "sources": [{"url": SRC}],
    }
    base.update(over)
    return base


async def _app(session) -> Application:
    await factories.seed_master(session)
    job = await factories.job(session)
    app = Application(job_id=job.id, status="submitted", submitted_at=datetime.now(UTC))
    session.add(app)
    await session.commit()
    return app


async def test_build_dossier_validates_sources_and_facts(session, sessionmaker, ai: FakeAIClient) -> None:
    app = await _app(session)
    ai.on("company.profile", lambda req: COMPANY_PROFILE)
    ai.on("interview.dossier", lambda req: dossier())
    did = await build_dossier(sessionmaker, str(app.id))
    d = await session.get(InterviewDossier, uuid.UUID(did))
    assert d.status == "ready"
    assert [h["text"] for h in d.content["company"]["history"]] == ["Fundada em 2010"]
    assert d.content["company"]["news"] == []  # fonte não verificada
    assert [m["experience_id"] for m in d.content["match"]] == ["acme"]
    assert "## Valores → minha história" in d.cheatsheet_md and "Ownership" in d.cheatsheet_md
    assert await session.scalar(select(CompanyProfile))  # perfil da empresa cacheado
    dossier_req = next(c for c in ai.calls if c.task == "interview.dossier")
    assert "<profile>" in dossier_req.context and "<company_profile>" in dossier_req.user


async def test_create_interview_flow(client: AsyncClient, session, dispatched) -> None:
    app = await _app(session)
    start = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    r = await client.post(
        "/api/v1/interviews",
        json={
            "application_id": str(app.id),
            "kind": "technical",
            "starts_at": start.isoformat(),
            "duration_min": 45,
            "link": "https://meet/x",
        },
    )
    assert r.status_code == 201
    iid = r.json()["id"]
    assert r.json()["company_name"] == "Globex" and r.json()["link"] == "https://meet/x"
    kinds = {e.kind for e in (await session.scalars(select(CalendarEvent))).all()}
    assert kinds == {"interview", "study_block"}
    await session.refresh(app)
    assert app.status == "interviewing"
    assert dispatched[-1][0] == "ai.build_dossier" and dispatched[-1][1]["interview_id"] == iid
    r = await client.post(
        f"/api/v1/interviews/{iid}/post-notes",
        json={
            "questions": ["Explique particionamento no Spark"],
            "self_rating": 4,
            "highlights": "conversa sobre Kafka",
        },
    )
    assert r.json()["self_rating"] == 4
    assert (await session.scalar(select(InterviewQuestionLog))).question.startswith("Explique")
    assert dispatched[-1][0] == "ai.thank_you"
    r = await client.get(f"/api/v1/interviews/{iid}/cheatsheet")
    assert r.status_code == 404  # dossiê ainda não gerado


async def test_mock_interview(client: AsyncClient, session, ai: FakeAIClient) -> None:
    app = await _app(session)
    turns = iter(
        [
            {"feedback": None, "next_question": "Conte sobre um pipeline que você construiu."},
            {
                "feedback": {
                    "star_structure": 3,
                    "clarity": 4,
                    "evidence": 2,
                    "overall": 3,
                    "strengths": ["clareza"],
                    "improvements": ["traga números"],
                    "better_answer_outline": "Na Acme, 12 pipelines...",
                },
                "next_question": None,
                "done": True,
                "final_summary": "Use métricas.",
            },
        ]
    )
    ai.on("interview.mock", lambda req: next(turns))
    r = await client.post("/api/v1/mock-sessions", json={"application_id": str(app.id), "interview_kind": "technical"})
    mid = r.json()["id"]
    assert r.json()["transcript"][0]["role"] == "interviewer"
    r = await client.post(f"/api/v1/mock-sessions/{mid}/turn", json={"answer": "Fiz pipelines na Acme."})
    assert r.json()["status"] == "finished" and r.json()["turn"]["feedback"]["overall"] == 3
    r = await client.post(f"/api/v1/mock-sessions/{mid}/turn", json={"answer": "mais"})
    assert r.status_code == 409


async def test_assessment_creates_deadline_and_status(client: AsyncClient, session) -> None:
    app = await _app(session)
    deadline = (datetime.now(UTC) + timedelta(days=4)).isoformat()
    r = await client.post(
        "/api/v1/assessments",
        json={"application_id": str(app.id), "deadline_at": deadline, "instructions": "Construa uma API"},
    )
    assert r.status_code == 201
    ev = await session.scalar(select(CalendarEvent).where(CalendarEvent.kind == "assessment_deadline"))
    assert ev is not None
    await session.refresh(app)
    assert app.status == "assessment"
