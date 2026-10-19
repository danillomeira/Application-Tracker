"""Preenchimento assistido em ATS externos (Greenhouse, Lever, Gupy) — sempre para na revisão (RF-EXT-03).

O agente preenche e anexa o CV; o envio é sempre feito pelo usuário, que depois marca "enviei".
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from tracker.agent import forms
from tracker.agent.api import AgentApi
from tracker.agent.human import Pace
from tracker.agent.sites.linkedin.easy_apply import Outcome, shot

APPLY_BUTTONS = ["Apply for this job", "Apply", "Candidatar-se", "Candidatar", "Quero me candidatar", "Apply now"]
LOGIN_HINT = re.compile(r"(entrar|login|sign in|fa[cç]a login|crie sua conta|create account)", re.I)


async def run(page: Page, job: dict[str, Any], api: AgentApi, pace: Pace) -> Outcome:
    jid, p = job["id"], job["payload"]
    url = p.get("apply_url") or p.get("url")
    await page.goto(url, wait_until="domcontentloaded")
    await pace.pause()
    if not await page.locator("form input, form textarea").count():
        await forms.click_button(page, APPLY_BUTTONS, pace)
        await pace.pause()
    if await page.locator("input[type=password]").count() and LOGIN_HINT.search(await page.inner_text("body")):
        await api.fail(jid, f"{p.get('ats')}: login necessário; candidate-se manualmente com o pacote")
        return Outcome("failed", "login")
    fields = await forms.extract_fields(page, None)
    if not fields:
        await api.fail(jid, "formulário não encontrado")
        return Outcome("failed", "sem formulário")
    res = await api.resolve(jid, 0, fields)
    if res.get("pause"):
        return Outcome("paused", ", ".join(res.get("pending", [])))
    resume = None
    if "__resume__" in res.get("values", {}).values() and p.get("has_resume"):
        resume = await api.resume(p["application_id"], Path(tempfile.mkdtemp(prefix="tracker-cv-")))
    await forms.fill_fields(page, fields, res.get("values", {}), pace, resume)
    key = await shot(page, api, jid, "external-filled")
    await api.step(jid, 0, "formulário preenchido", f"{len(fields)} campos", key)
    decision = await api.review(jid, f"{p.get('company')} · {p.get('title')} (revise e envie no navegador)", key)
    return Outcome("review_pending", decision.get("reason", "aguardando envio manual"))
