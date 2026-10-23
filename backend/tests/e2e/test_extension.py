"""Extensão real (Chromium) + API real (processo uvicorn) + página de candidatura local.

Fluxo: painel mostra a vaga conhecida → "Preencher" completa perfil/CV/anos → pergunta sensível fica
para o usuário → usuário responde e envia → extensão detecta "Thank you" → candidatura registrada e
resposta aprendida no banco.
"""

from __future__ import annotations

import asyncio
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
from tracker.modules.jobs.models import Job, JobSource, SavedSearch
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
            # preenche SOZINHO ao abrir (sem clicar em nada)
            await panel.get_by_text("preenchido(s) automaticamente").wait_for(timeout=15000)
            assert await page.input_value("#first") == "Ana"
            assert await page.input_value("#last") == "Teste Silva"
            assert await page.input_value("#email") == "ana@example.com"
            assert await page.input_value("#li") == "https://linkedin.com/in/ana-teste"
            assert int(await page.input_value("#years")) >= 5  # calculado pelo mestre
            assert await page.input_value("#eng") == "3"  # "Advanced" do perfil → opção "Avançado"
            assert await page.evaluate("document.getElementById('cv').files[0].name") == "Ana_Silva_Data_Engineer_EN.pdf"
            assert not await page.is_checked("#s-n")  # sensível: fica para o usuário
            assert await page.input_value("#why") == ""  # pergunta aberta: só com IA, a pedido

            # etapa seguinte: campo novo é preenchido assim que aparece
            await page.click("#next")
            await page.wait_for_function("document.getElementById('gh').value.includes('ana-teste')", timeout=15000)

            # "Completar com IA" escreve a pergunta aberta
            await panel.get_by_text("Completar com IA").click()
            await page.wait_for_function("document.getElementById('why').value.length > 10", timeout=20000)

            # sugestão ao clicar num campo vazio, e "Usar" preenche de verdade
            await page.fill("#phone", "")
            await page.click("h1")
            await page.hover("#phone", position={"x": 4, "y": 4})  # parte visível: o painel sai da frente
            await page.wait_for_timeout(400)
            await page.click("#phone")
            await page.get_by_text("💡").wait_for(timeout=10000)
            await page.get_by_role("button", name="Usar").dispatch_event("mousedown")
            await page.wait_for_function("document.getElementById('phone').value.length > 5", timeout=5000)

            await panel.locator('button[title="Minimizar"]').click()  # tira o painel da frente
            await page.click("label[for=s-n]")  # o usuário responde a pergunta sensível
            await page.click("text=Submit application")  # e ele mesmo envia
            sent = await page.evaluate("window.sent")
            assert sent["spons"] == "No" and sent["cv"] == "Ana_Silva_Data_Engineer_EN.pdf" and sent["eng"] == "3"
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


async def test_linkedin_discovery_imports_visible_results(servers, session, client, tmp_path) -> None:
    """Real extension + API import a visible LinkedIn job card."""
    await settings_store.put(session, "extension", {"token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest()})
    search = SavedSearch(
        name="Go remoto",
        query="Go",
        filters={},
        sources=["linkedin"],
        schedule_cron="* * * * *",
        is_active=True,
    )
    session.add(search)
    await session.commit()

    linkedin_html = """<!doctype html><html><body>
      <ul class="scaffold-layout__list">
        <li class="scaffold-layout__list-item">
          <div class="job-card-container" data-job-id="4012345678">
            <a class="job-card-list__title" href="https://www.linkedin.com/jobs/view/4012345678/">
              <span>Senior Go Engineer</span>
            </a>
            <div class="artdeco-entity-lockup__subtitle">Globex</div>
            <ul><li class="job-card-container__metadata-item">Brazil Remote</li></ul>
            <span>Easy Apply</span>
          </div>
        </li>
        <li class="scaffold-layout__list-item">
          <div data-occludable-job-id="urn:li:fsd_jobPosting:4012345679">
            <a href="https://www.linkedin.com/jobs/search/?currentJobId=4012345679">
              <span data-test-job-card-title>Go Platform Engineer</span>
            </a>
            <span data-test-job-card-company-name>Initech</span>
            <span data-test-job-card-location>Brazil Remote</span>
          </div>
        </li>
      </ul>
    </body></html>"""

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(tmp_path / "linkedin-profile"),
            headless=False,
            args=["--headless=new", f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
        )

        async def mock_linkedin(route):
            await route.fulfill(status=200, content_type="text/html", body=linkedin_html)

        try:
            await ctx.route("https://www.linkedin.com/jobs/search/**", mock_linkedin)
            sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
            await sw.evaluate(
                "cfg => chrome.storage.sync.set(cfg)",
                {"apiUrl": servers["api"], "token": TOKEN, "enabled": True, "ignoredDomains": []},
            )

            imported = alternate = None
            for _ in range(60):
                session.expire_all()
                imported = await session.scalar(
                    select(Job).join(JobSource, JobSource.job_id == Job.id).where(
                        JobSource.source == "linkedin", JobSource.external_id == "4012345678"
                    )
                )
                alternate = await session.scalar(
                    select(Job).join(JobSource, JobSource.job_id == Job.id).where(
                        JobSource.source == "linkedin", JobSource.external_id == "4012345679"
                    )
                )
                if imported is not None and alternate is not None:
                    break
                await asyncio.sleep(0.5)

            assert imported is not None, "visible LinkedIn job did not reach the database through the extension"
            assert imported.title == "Senior Go Engineer"
            assert imported.location == "Brazil Remote"
            assert imported.work_model == "remote"
            assert alternate is not None
            assert alternate.title == "Go Platform Engineer"
            assert alternate.company_id is not None

            status = await client.get("/api/v1/assistant/discovery/status")
            assert status.status_code == 200
            assert status.json()["last_result"]["status"] == "completed"
            assert status.json()["last_result"]["created"] == 2

            visible = await client.get(
                "/api/v1/jobs",
                params={"status": "open", "triage": "discovered", "q": "Go", "location": "Brazil", "work_model": "remote"},
            )
            assert visible.status_code == 200
            visible_ids = {row["id"] for row in visible.json()}
            assert {str(imported.id), str(alternate.id)} <= visible_ids
        finally:
            await ctx.close()
