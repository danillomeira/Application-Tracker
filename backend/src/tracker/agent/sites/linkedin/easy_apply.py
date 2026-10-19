"""Fluxo do Easy Apply (docs/09 §3). O agente executa; a API decide."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import Page

from tracker.agent import forms, safety
from tracker.agent.api import AgentApi
from tracker.agent.human import Pace

SELECTORS = yaml.safe_load((Path(__file__).parent / "selectors.yaml").read_text(encoding="utf-8"))
MAX_STEPS = 12


class StopJob(Exception):
    """Encerra a tarefa atual (já reportada à API)."""


@dataclass
class Outcome:
    status: str  # submitted | paused | review_pending | dry_run | already_applied | closed | failed | safety
    detail: str = ""


async def _has_text(page: Page, texts: list[str]) -> bool:
    try:
        body = await page.inner_text("body", timeout=3000)
    except Exception:
        return False
    return any(re.search(re.escape(t), body, re.I) for t in texts)


async def _safety(page: Page, api: AgentApi, job_id: str) -> None:
    sig = await safety.check(page)
    if sig is not None:
        await shot(page, api, job_id, f"safety-{sig.kind}")
        await api.safety_stop(job_id, sig.kind, sig.message, page.url)
        raise StopJob(sig.kind)


async def shot(page: Page, api: AgentApi, job_id: str, name: str) -> str | None:
    try:
        data = await page.screenshot(full_page=False)
        return await api.artifact(job_id, f"{name}.png", data, "image/png")
    except Exception:
        return None


async def run(page: Page, job: dict[str, Any], api: AgentApi, pace: Pace, follow_company: bool = False) -> Outcome:
    jid = job["id"]
    p = job["payload"]
    url = p.get("url")
    if not url:
        await api.fail(jid, "vaga sem URL")
        return Outcome("failed", "sem URL")
    await page.goto(url, wait_until="domcontentloaded")
    await pace.pause()
    await _safety(page, api, jid)
    texts, buttons = SELECTORS["texts"], SELECTORS["buttons"]
    if await _has_text(page, texts["closed"]):
        await api.fail(jid, "vaga encerrada", closed=True)
        return Outcome("closed")
    if not await forms.visible_button(page, buttons["easy_apply"]):
        if await _has_text(page, texts["applied"]):
            await api.submitted(jid, "já candidatado (reconciliação)", await shot(page, api, jid, "already"), True)
            return Outcome("already_applied")
        await api.fail(jid, "botão Easy Apply não encontrado (vaga externa ou layout novo)")
        return Outcome("failed", "sem Easy Apply")
    await forms.click_button(page, buttons["easy_apply"], pace)
    modal = page.locator(SELECTORS["modal"]).first
    try:
        await modal.wait_for(timeout=10000)
    except Exception:
        await _safety(page, api, jid)
        await api.safety_stop(jid, "unknown_layout", "modal do Easy Apply não abriu", page.url)
        raise StopJob("unknown_layout") from None

    resume_path: Path | None = None
    tmpdir = Path(tempfile.mkdtemp(prefix="tracker-cv-"))
    error_rounds = 0
    for step in range(MAX_STEPS):
        await _safety(page, api, jid)
        fields = await forms.extract_fields(page, modal)
        heading = modal.locator("h2:visible, h3:visible")
        title = (await heading.first.inner_text(timeout=2000)) if await heading.count() else f"etapa {step + 1}"
        key = await shot(page, api, jid, f"step-{step + 1}")
        await api.step(jid, step, title.strip()[:120], f"{len(fields)} campos", key)
        to_resolve = [
            f for f in fields if f["kind"] != "checkbox" or not re.search("|".join(texts["follow_company"]), f["label"], re.I)
        ]
        if to_resolve:
            res = await api.resolve(jid, step, to_resolve)
            if res.get("pause"):
                await _discard(page, pace)
                return Outcome("paused", ", ".join(res.get("pending", [])))
            values = res.get("values", {})
            if "__resume__" in values.values() and resume_path is None and p.get("has_resume"):
                resume_path = await api.resume(p["application_id"], tmpdir)
            failed = await forms.fill_fields(page, fields, values, pace, resume_path)
            if failed:
                await api.step(jid, step, "campos não preenchidos", ", ".join(failed))
        # Revisão final: botão de envio visível
        if await forms.visible_button(page, buttons["submit"], modal):
            for f in fields:
                if f["kind"] == "checkbox" and re.search("|".join(texts["follow_company"]), f["label"], re.I):
                    await page.locator(f'[data-tracker-key="{f["key"]}"]').set_checked(follow_company)
            key = await shot(page, api, jid, "review")
            decision = await api.review(jid, f"{p.get('company')} · {p.get('title')}", key)
            if not decision.get("approved"):
                await _discard(page, pace)
                return Outcome("dry_run" if decision.get("dry_run") else "review_pending", decision.get("reason", ""))
            await forms.click_button(page, buttons["submit"], pace, modal)
            await pace.pause(2, 4)
            await _safety(page, api, jid)
            if await _has_text(page, texts["success"]):
                key = await shot(page, api, jid, "submitted")
                await api.submitted(jid, "confirmação de envio exibida", key)
                await forms.click_button(page, buttons["done"] + buttons["dismiss"], pace)
                return Outcome("submitted")
            await api.fail(jid, "envio sem confirmação visível; verificar manualmente")
            return Outcome("failed", "sem confirmação")
        clicked = await forms.click_button(page, buttons["review"], pace, modal) or await forms.click_button(
            page, buttons["next"], pace, modal
        )
        if not clicked:
            await api.safety_stop(jid, "unknown_layout", "nenhum botão de avanço reconhecido no modal", page.url)
            raise StopJob("unknown_layout")
        await pace.pause(0.8, 2)
        after = await forms.extract_fields(page, modal)
        errors = [f for f in after if f.get("error")]
        if errors:  # validação falhou: a próxima volta reenvia só o que está na tela (máx. 2)
            error_rounds += 1
            if error_rounds > 2:
                await api.fail(jid, "erro de validação persistente: " + "; ".join(f"{f['label']}: {f['error']}" for f in errors))
                await _discard(page, pace)
                return Outcome("failed", "validação")
    await api.fail(jid, f"excedeu {MAX_STEPS} etapas")
    return Outcome("failed", "etapas demais")


async def _discard(page: Page, pace: Pace) -> None:
    b = SELECTORS["buttons"]
    try:
        if await forms.click_button(page, b["dismiss"], pace):
            await forms.click_button(page, b["discard"], pace)
    except Exception:  # noqa: S110
        pass
