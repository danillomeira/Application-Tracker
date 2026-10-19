from __future__ import annotations

import shutil
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from tests import factories
from tests.factories import FIXTURES
from tracker.integrations.claude.client import FakeAIClient
from tracker.modules.profile.models import AnswerBankEntry, BlocklistEntry, ProfileImport
from tracker.modules.profile.tasks import _extract
from tracker.modules.resumes.content import baseline
from tracker.modules.resumes.models import ResumeRender, ResumeVariant
from tracker.modules.resumes.tasks import _tailor

needs_tex = pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic não instalado")


async def test_master_requires_onboarding(client: AsyncClient) -> None:
    r = await client.get("/api/v1/profile/master")
    assert r.status_code == 409


async def test_master_versions_and_diff(client: AsyncClient, session) -> None:
    m = await factories.seed_master(session)
    r = await client.get("/api/v1/profile/master")
    assert r.status_code == 200
    assert r.json()["version"] == 1
    data = m.model_dump(mode="json")
    data["contact"]["phone"] = "+55 (11) 91111-1111"
    r = await client.put("/api/v1/profile/master", json={"data": data, "change_note": "telefone"})
    assert r.json()["version"] == 2
    r = await client.get("/api/v1/profile/master/diff", params={"from_": 1, "to": 2})
    assert r.json() == [{"path": "contact.phone", "before": "+55 (11) 90000-0000", "after": "+55 (11) 91111-1111"}]
    versions = (await client.get("/api/v1/profile/master/versions")).json()
    assert [v["is_current"] for v in versions] == [True, False]


async def test_skill_years_endpoint(client: AsyncClient, session) -> None:
    await factories.seed_master(session)
    r = await client.get("/api/v1/profile/skills/years", params={"skill": "postgres"})
    assert r.json()["canonical"] == "PostgreSQL"


async def test_yaml_import_flow(client: AsyncClient, session, sessionmaker, dispatched) -> None:
    yaml_bytes = (FIXTURES / "profile" / "master.yaml").read_bytes()
    r = await client.post("/api/v1/profile/import", files={"file": ("master.yaml", yaml_bytes, "application/x-yaml")})
    assert r.status_code == 202
    import_id = r.json()["id"]
    assert dispatched[-1][0] == "ai.profile_extract"
    await _extract(sessionmaker, None, import_id=import_id)
    imp = (await client.get(f"/api/v1/profile/import/{import_id}")).json()
    assert imp["status"] == "extracted"
    r = await client.post(f"/api/v1/profile/import/{import_id}/confirm", json={"data": imp["extracted"]["profile"]})
    assert r.status_code == 200
    # bloqueios padrão e respostas derivadas foram criados
    assert (await session.scalars(select(BlocklistEntry))).all()
    assert (await session.scalars(select(AnswerBankEntry))).all()
    row = await session.get(ProfileImport, uuid.UUID(import_id))
    assert row.status == "applied"


async def test_pdf_import_uses_ai(client: AsyncClient, sessionmaker, ai: FakeAIClient) -> None:
    ai.on(
        "profile.extract",
        lambda req: {
            "contact": {"full_name": "Ana", "email": "ana@example.com"},
            "skills": [{"category": "languages", "items": ["Python"]}],
            "experience": [
                {
                    "id": "x",
                    "title": "Dev",
                    "organization": "X",
                    "start": "2022-01",
                    "end": None,
                    "bullets_en": ["Did **things**."],
                    "skills": ["Python"],
                }
            ],
            "projects": [],
            "education": [],
            "certifications": [],
            "languages": [],
            "low_confidence": ["experience[0].start"],
        },
    )
    r = await client.post("/api/v1/profile/import", files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")})
    await _extract(sessionmaker, None, import_id=r.json()["id"])
    imp = (await client.get(f"/api/v1/profile/import/{r.json()['id']}")).json()
    assert imp["extracted"]["low_confidence"] == ["experience[0].start"]
    assert ai.calls[0].task == "profile.extract"
    assert ai.calls[0].user[0]["type"] == "document"


async def test_import_rejects_bad_type(client: AsyncClient) -> None:
    r = await client.post("/api/v1/profile/import", files={"file": ("x.exe", b"MZ\x90\x00", "application/octet-stream")})
    assert r.status_code == 415


async def test_answer_bank_sensitive_and_search(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/answer-bank", json={"canonical_question": "What is your expected salary?", "answer": {"value": "x"}}
    )
    assert r.json()["sensitive"] is True
    await client.post(
        "/api/v1/answer-bank",
        json={
            "canonical_question": "How many years of experience do you have with Python?",
            "field_kind": "number",
            "answer": {"value": 5},
        },
    )
    hits = (await client.get("/api/v1/answer-bank", params={"q": "years of experience with Python"})).json()
    assert hits[0]["canonical_question"].startswith("How many years")


async def test_preferences_risk_acceptance_audited(client: AsyncClient) -> None:
    r = await client.put("/api/v1/profile/preferences", json={"linkedin_risk_accepted": True})
    assert r.json()["linkedin_risk_accepted"] is True
    audit = (await client.get("/api/v1/audit")).json()["items"]
    assert any(a["action"] == "linkedin.risk_accepted" for a in audit)


@needs_tex
async def test_baseline_variant_render_and_download(client: AsyncClient, session) -> None:
    await factories.seed_master(session)
    r = await client.post("/api/v1/resumes/variants/baseline", json={"profile": "data_engineer", "language": "en"})
    assert r.status_code == 201
    vid = r.json()["id"]
    assert r.json()["validation"]["passed"] is True
    # render direto pelo serviço (a tarefa usa o mesmo caminho)
    from tracker.modules.profile.service import current_master
    from tracker.modules.resumes.service import render_variant

    v = await session.get(ResumeVariant, uuid.UUID(vid))
    _, m = await current_master(session)
    rr = await render_variant(session, v, m, ["Python", "Kafka"])
    await session.commit()
    assert rr.ats_report["ok"] is True
    pdf = await client.get(f"/api/v1/resumes/renders/{rr.id}/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert "Ana_Silva_Data_Engineer_EN.pdf" in pdf.headers["content-disposition"]
    r = await client.post(f"/api/v1/resumes/variants/{vid}/approve")
    assert r.json()["status"] == "approved"


async def test_approve_blocked_when_invalid(client: AsyncClient, session) -> None:
    m = await factories.seed_master(session)
    c = baseline(m, "data_engineer", "en")
    c.skill_rows[0].items.append("Kubernetes")
    r = await client.post("/api/v1/resumes/variants/baseline", json={"profile": "data_engineer"})
    vid = r.json()["id"]
    r = await client.put(f"/api/v1/resumes/variants/{vid}", json={"content": c.model_dump()})
    assert r.json()["validation"]["passed"] is False
    r = await client.post(f"/api/v1/resumes/variants/{vid}/approve")
    assert r.status_code == 422


def _draft(bullets_suffix: str = "") -> dict:
    return {
        "headline": "Data Engineer | Python, Spark, Kafka",
        "summary": "Data Engineer with **4+ years** building pipelines that process **2 TB per day**.",
        "skill_rows": [
            {"category": "Languages", "items": ["Python"]},
            {"category": "Data", "items": ["Spark", "Kafka"]},
        ],
        "experiences": [
            {
                "experience_id": "acme",
                "title": "Data Engineer",
                "bullets": ["Built **12 ETL pipelines** in Python and Spark with Kafka." + bullets_suffix],
            },
            {
                "experience_id": "beta",
                "title": "Junior Developer",
                "bullets": ["Developed FastAPI services used by **300 customers**."],
            },
        ],
        "project_ids": ["pipeline-lab"],
        "used_facts": ["acme"],
        "changes": ["foco em pipelines"],
    }


@needs_tex
async def test_tailor_retries_on_violation(session, sessionmaker, ai: FakeAIClient) -> None:
    await factories.seed_master(session)
    job = await factories.job(session)
    await session.commit()
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return _draft(" Deployed on Kubernetes.") if calls["n"] == 1 else _draft()

    ai.on("resume.tailor", handler)
    result = await _tailor(sessionmaker, None, job_id=str(job.id))
    assert calls["n"] == 2
    assert "kubernetes" in ai.calls[1].user.lower()  # a segunda tentativa recebeu a violação
    assert result["passed"] is True and result["render_id"]
    v = await session.get(ResumeVariant, uuid.UUID(result["variant_id"]))
    assert v.kind == "tailored" and v.status == "draft" and v.job_id == job.id
    rr = await session.get(ResumeRender, uuid.UUID(result["render_id"]))
    assert rr.ats_report["keyword_coverage"] == 1.0
