"""Robô contra fixtures HTML locais (nunca contra o LinkedIn real em testes)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright

from tracker.agent.human import Pace
from tracker.agent.sites.linkedin import easy_apply, search
from tracker.agent.sites.linkedin.easy_apply import StopJob

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "linkedin"


class FakeApi:
    def __init__(self, answers: dict[str, Any] | None = None, pause_on: str | None = None, approve: bool = True) -> None:
        self.answers = answers or {}
        self.pause_on = pause_on
        self.approve = approve
        self.calls: list[tuple[str, Any]] = []

    async def heartbeat(self, job_id):
        return {"kill": False}

    async def step(self, job_id, index, title, log=None, screenshot_key=None):
        self.calls.append(("step", title))

    async def artifact(self, job_id, name, data, content_type):
        self.calls.append(("artifact", name))
        return f"k/{name}"

    async def checkpoint(self, job_id, state):
        pass

    async def resolve(self, job_id, step_index, fields):
        self.calls.append(("resolve", [f["label"] for f in fields]))
        if self.pause_on and any(self.pause_on in f["label"] for f in fields):
            return {"pause": True, "pending": [self.pause_on]}
        values = {}
        for f in fields:
            if f["kind"] == "file":
                values[f["key"]] = "__resume__"
                continue
            for k, v in self.answers.items():
                if k.lower() in f["label"].lower():
                    values[f["key"]] = v
        return {"values": values}

    async def resume(self, application_id, dest: Path):
        p = dest / "Ana_Silva_Data_Engineer_EN.pdf"
        p.write_bytes(b"%PDF-1.4 test")
        return p

    async def review(self, job_id, summary, screenshot_key):
        self.calls.append(("review", summary))
        return {"approved": self.approve, "reason": "modo revisão"}

    async def submitted(self, job_id, evidence, screenshot_key, already_applied=False):
        self.calls.append(("submitted", already_applied))

    async def safety_stop(self, job_id, kind, message, url):
        self.calls.append(("safety", kind))

    async def fail(self, job_id, error, closed=False):
        self.calls.append(("fail", closed, error))

    async def search_results(self, job_id, jobs, done=True):
        self.calls.append(("search", jobs))
        return {"created": len(jobs)}


ANSWERS = {
    "Last name": "Teste Silva",
    "Email": "ana@example.com",
    "country code": "Brazil (+55)",
    "Mobile phone": "+55 11 90000-0000",
    "years of experience": "3",
    "English": "Advanced",
    "sponsorship": "No",
    "Why do you want": "I build pipelines in Python.",
}


def job(name: str = "easy_apply.html") -> dict[str, Any]:
    return {
        "id": "j1",
        "kind": "apply",
        "payload": {
            "url": (FIX / name).as_uri(),
            "application_id": "a1",
            "has_resume": True,
            "company": "Globex",
            "title": "Senior Data Engineer",
        },
    }


@pytest.fixture
async def page():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        pg = await b.new_page()
        yield pg
        await b.close()


async def test_full_flow_submits(page) -> None:
    api = FakeApi(ANSWERS)
    out = await easy_apply.run(page, job(), api, Pace(scale=0))
    assert out.status == "submitted"
    sent = await page.evaluate("window.submitted")
    assert sent == {
        "fn": "Ana",
        "ln": "Teste Silva",
        "em": "ana@example.com",
        "cc": "Brazil (+55)",
        "ph": "+55 11 90000-0000",
        "cv": "Ana_Silva_Data_Engineer_EN.pdf",
        "yp": "3",
        "lvl": "Advanced",
        "sp": "No",
        "why": "I build pipelines in Python.",
        "follow": False,
    }
    resolved_labels = [c[1] for c in api.calls if c[0] == "resolve"]
    assert "Will you now or in the future require sponsorship for employment visa status?" in resolved_labels[2]
    assert not any("Follow" in lbl for lbls in resolved_labels for lbl in lbls)  # checkbox de seguir não vai para a API
    assert ("submitted", False) in api.calls


async def test_review_mode_discards_without_submitting(page) -> None:
    api = FakeApi(ANSWERS, approve=False)
    out = await easy_apply.run(page, job(), api, Pace(scale=0))
    assert out.status == "review_pending"
    assert await page.evaluate("window.submitted") is None
    assert await page.evaluate("window.discarded") is True


async def test_pending_question_pauses(page) -> None:
    api = FakeApi(ANSWERS, pause_on="sponsorship")
    out = await easy_apply.run(page, job(), api, Pace(scale=0))
    assert out.status == "paused" and await page.evaluate("window.submitted") is None


async def test_validation_error_retries_then_fails(page) -> None:
    answers = {k: v for k, v in ANSWERS.items() if k != "years of experience"}
    api = FakeApi(answers)
    out = await easy_apply.run(page, job(), api, Pace(scale=0))
    assert out.status == "failed" and any(c[0] == "fail" and "validação" in c[2] for c in api.calls)


async def test_captcha_stops(page) -> None:
    api = FakeApi()
    with pytest.raises(StopJob):
        await easy_apply.run(page, job("captcha.html"), api, Pace(scale=0))
    assert ("safety", "captcha") in api.calls


async def test_closed_and_already_applied(page) -> None:
    api = FakeApi()
    assert (await easy_apply.run(page, job("closed.html"), api, Pace(scale=0))).status == "closed"
    assert ("fail", True, "vaga encerrada") in api.calls
    api2 = FakeApi()
    assert (await easy_apply.run(page, job("applied.html"), api2, Pace(scale=0))).status == "already_applied"
    assert ("submitted", True) in api2.calls


async def test_search_extracts_cards(page, monkeypatch) -> None:
    monkeypatch.setattr(search, "search_url", lambda q, f: (FIX / "search.html").as_uri())
    api = FakeApi()
    n = await search.run(page, {"id": "s1", "kind": "search", "payload": {"query": "data engineer"}}, api, Pace(scale=0))
    assert n == 2
    jobs = next(c[1] for c in api.calls if c[0] == "search")
    assert jobs[0]["external_id"] == "111" and jobs[0]["company"] == "Globex"
    assert jobs[0]["applicants"] == 42 and jobs[0]["easy_apply"] is True and jobs[0]["posted_at"]
