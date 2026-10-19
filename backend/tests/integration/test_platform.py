from __future__ import annotations

from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select

from tracker.integrations.claude.client import AIRequest, BudgetExceeded, FakeAIClient
from tracker.modules.platform.models import AiCall, AuditLog, TaskRun


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["db"] is True


async def test_requires_auth(anon_client: AsyncClient) -> None:
    r = await anon_client.get("/api/v1/settings/flags")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "401"


async def test_csrf_header_required_for_mutations(client: AsyncClient) -> None:
    r = await client.put("/api/v1/settings/flags", json={"gmail": False}, headers={"x-tracker-csrf": ""})
    assert r.status_code == 403


async def test_dev_login_sets_cookie(anon_client: AsyncClient) -> None:
    r = await anon_client.post("/api/v1/auth/dev-login")
    assert r.status_code == 303
    assert "tracker_session" in r.headers["set-cookie"]
    me = await anon_client.get("/api/v1/auth/me")
    assert me.json()["email"] == "me@example.com"


async def test_settings_merge_and_audit(client: AsyncClient, session) -> None:
    r = await client.get("/api/v1/settings/limits")
    assert r.json()["easy_apply_per_day"] == 20
    r = await client.put("/api/v1/settings/limits", json={"easy_apply_per_day": 12})
    assert r.status_code == 200
    body = r.json()
    assert body["easy_apply_per_day"] == 12
    assert body["linkedin_searches_per_day"] == 10  # padrão preservado
    logs = (await session.scalars(select(AuditLog))).all()
    assert any(log.action == "settings.update" for log in logs)


async def test_settings_rejects_auto_email(client: AsyncClient) -> None:
    r = await client.put("/api/v1/settings/automation_policy", json={"email": {"send": "auto"}})
    assert r.status_code == 422


async def test_dev_ping_enqueues_task(client: AsyncClient, dispatched, session) -> None:
    r = await client.post("/api/v1/dev/ping")
    assert r.status_code == 202
    task_id = r.json()["task_id"]
    assert dispatched == [("platform.ping", {"task_run_id": task_id, "steps": 5})]
    tr = await session.get(TaskRun, __import__("uuid").UUID(task_id))
    assert tr is not None and tr.status == "pending"


class Echo(BaseModel):
    text: str


async def test_fake_ai_records_call(ai: FakeAIClient, session) -> None:
    ai.on("test.echo", lambda req: {"text": str(req.user)})
    res = await ai.structured(AIRequest(task="test.echo", system="s", user="olá"), Echo)
    assert res.output.text == "olá"
    calls = (await session.scalars(select(AiCall))).all()
    assert len(calls) == 1 and calls[0].task == "test.echo"


async def test_budget_blocks_non_essential(ai: FakeAIClient, session, monkeypatch) -> None:
    from tracker.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ai_monthly_budget_usd", 1.0)
    session.add(AiCall(task="x", model="m", cost_usd=2.0))
    await session.commit()
    import pytest

    with pytest.raises(BudgetExceeded):
        await ai._check_budget("resume.tailor")
    await ai._check_budget("email.classify")  # essencial continua


async def test_ai_usage_endpoint(client: AsyncClient, session) -> None:
    session.add(AiCall(task="job.extract", model="m", cost_usd=0.5, input_tokens=10))
    await session.commit()
    r = await client.get("/api/v1/ai/usage")
    assert r.status_code == 200
    assert r.json()["by_task"][0]["task"] == "job.extract"
