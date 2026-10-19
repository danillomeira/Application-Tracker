"""Extensão real (Chromium) + API real (processo uvicorn) + página de candidatura local.

Fluxo: painel mostra a vaga conhecida → "Preencher" completa perfil/CV/anos → pergunta sensível fica
para o usuário → usuário responde e envia → extensão detecta "Thank you" → candidatura registrada e
resposta aprendida no banco.
"""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from playwright.async_api import async_playwright
from sqlalchemy import select

from tests import factories
from tracker.core import settings_store
from tracker.modules.applications.models import Application, ApplicationAnswer
from tracker.modules.jobs import service as job_service
from tracker.modules.jobs.normalize import RawJob
from tracker.modules.profile.models import AnswerBankEntry
from tracker.modules.profile.service import current_version
from tracker.modules.resumes.content import baseline
from tracker.modules.resumes.models import ResumeRender, ResumeVariant

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT / "apps" / "extension"
FIX = Path(__file__).resolve().parents[1] / "fixtures"
TOKEN = "test-extension-token"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servers(tmp_path_factory):
    storage = tmp_path_factory.mktemp("ext-storage")
    api_port, web_port = free_port(), free_port()
    env = {
        **os.environ,
        "TRACKER_NO_DOTENV": "1",
        "APP_ENV": "test",
        "STORAGE_LOCAL_DIR": str(storage),
        "AI_FAKE": "true",
        "EMBEDDINGS_BACKEND": "hash",
        "CORS_ORIGINS": "[]",
    }
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tracker.main:app", "--port", str(api_port), "--log-level", "warning"],
        env=env,
        cwd=ROOT / "backend",
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", web_port), partial(SimpleHTTPRequestHandler, directory=str(FIX)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{api_port}/api/v1/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    yield {"api": f"http://127.0.0.1:{api_port}", "web": f"http://127.0.0.1:{web_port}", "storage": storage}
    api.terminate()
    httpd.shutdown()


async def _seed(session, servers) -> str:
    from tracker.core.storage import LocalStorage

    m = await factories.seed_master(session)
    await settings_store.put(session, "extension", {"token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest()})
    page_url = f"{servers['web']}/apply_form.html"
    job, _ = await job_service.upsert_job(
        session,
        RawJob(
            source="browser",
            external_id="x1",
            title="Senior Data Engineer",
            company_name="Globex",
            url=page_url,
            description_text="Python Spark Kafka pipelines",
            apply_url=page_url,
        ),
    )
    v = ResumeVariant(
        kind="wildcard",
        slug="de-en",
        name="Data Engineer",
        language="en",
        status="approved",
        content=baseline(m, "data_engineer", "en").model_dump(),
        master_version=(await current_version(session)).version,
        validation={"passed": True},
    )
    session.add(v)
    await session.flush()
    key = LocalStorage(servers["storage"]).put("resumes/v/Ana_Silva_Data_Engineer_EN.pdf", b"%PDF-1.4 fake")
    session.add(
        ResumeRender(variant_id=v.id, storage_key=key, tex_source_key=key, filename="Ana_Silva_Data_Engineer_EN.pdf", sha256="x")
    )
    await session.commit()
    return str(job.id)


async def test_extension_end_to_end(servers, session, tmp_path) -> None:
    job_id = await _seed(session, servers)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(tmp_path / "profile"),
            headless=False,
            args=["--headless=new", f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
        )
        try:
            sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
            await sw.evaluate(
                "cfg => chrome.storage.sync.set(cfg)",
                {"apiUrl": servers["api"], "token": TOKEN, "enabled": True, "ignoredDomains": []},
            )
            page = await ctx.new_page()
            await page.goto(f"{servers['web']}/apply_form.html")
            panel = page.locator("#tracker-assistant")
            await panel.get_by_text("Senior Data Engineer").wait_for(timeout=15000)  # cartão da vaga conhecida
            await panel.get_by_text("Preencher").first.click()
            await panel.get_by_text("campo(s) preenchido(s)").wait_for(timeout=15000)

            assert await page.input_value("#first") == "Ana"
            assert await page.input_value("#last") == "Teste Silva"
            assert await page.input_value("#email") == "ana@example.com"
            assert await page.input_value("#li") == "https://linkedin.com/in/ana-teste"
            assert int(await page.input_value("#years")) >= 5  # calculado pelo mestre
            assert await page.evaluate("document.getElementById('cv').files[0].name") == "Ana_Silva_Data_Engineer_EN.pdf"
            assert not await page.is_checked("#s-n")  # sensível: fica para o usuário

            # sugestão ao focar um campo vazio
            await page.fill("#phone", "")
            await page.click("h1")  # tira o foco
            await page.click("#phone")  # usuário clica no campo vazio
            await page.get_by_text("💡").wait_for(timeout=10000)

            await page.click("label[for=s-n]")  # o usuário responde a pergunta sensível
            await page.click("text=Submit application")  # e ele mesmo envia
            sent = await page.evaluate("window.sent")
            assert sent["spons"] == "No" and sent["cv"] == "Ana_Silva_Data_Engineer_EN.pdf"
            await page.locator("#tracker-assistant").get_by_text("acompanhamento").wait_for(timeout=15000)
        finally:
            await ctx.close()

    await session.close()
    app = await session.scalar(select(Application).where(Application.job_id == __import__("uuid").UUID(job_id)))
    assert app is not None and app.status == "submitted" and app.channel == "assisted"
    answers = (await session.scalars(select(ApplicationAnswer).where(ApplicationAnswer.application_id == app.id))).all()
    assert any("sponsorship" in a.question_text and a.answer["value"] == "No" for a in answers)
    learned = await session.scalar(select(AnswerBankEntry).where(AnswerBankEntry.canonical_question.like("%sponsorship%")))
    assert learned is not None and learned.answer["value"] == "No"  # da próxima vez, sem perguntar
