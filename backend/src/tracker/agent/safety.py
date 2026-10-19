"""Detecção de proteções: captcha, checkpoint, login, avisos (RF-CAN-10). Nunca contorna: só para."""

from __future__ import annotations

import re
from dataclasses import dataclass

from playwright.async_api import Page

CHECKPOINT_URL = re.compile(r"/checkpoint/|/challenge/", re.I)
LOGIN_URL = re.compile(r"/login|/uas/login|/authwall|signup", re.I)
WARNING_TEXT = re.compile(
    r"unusual activity|atividade incomum|temporarily restricted|restringimos temporariamente|"
    r"we've restricted|account (has been )?restricted|conta (foi )?restrita|too many requests|"
    r"you('ve| have) reached the (weekly|daily) limit|limite (semanal|di[aá]rio)",
    re.I,
)
CAPTCHA_TEXT = re.compile(
    r"captcha|verify you('re| are) (a )?human|verifica[cç][aã]o de seguran[cç]a|"
    r"security verification|confirme que voc[eê] n[aã]o [eé] um rob[oô]",
    re.I,
)
ERROR_TEXT = re.compile(r"something went wrong|algo deu errado|this page (isn't|is not) available", re.I)


@dataclass
class SafetySignal:
    kind: str
    message: str


async def check(page: Page) -> SafetySignal | None:
    url = page.url
    if CHECKPOINT_URL.search(url):
        return SafetySignal("checkpoint", f"página de verificação: {url}")
    if LOGIN_URL.search(url) and "linkedin.com" in url:
        return SafetySignal("login", "sessão expirada: faça login manualmente (tracker-agent login)")
    for frame in page.frames:
        if re.search(r"recaptcha|hcaptcha|arkoselabs|funcaptcha|challenges\.cloudflare", frame.url or "", re.I):
            return SafetySignal("captcha", "captcha detectado")
    try:
        text = await page.inner_text("body", timeout=3000)
    except Exception:
        return None
    if CAPTCHA_TEXT.search(text):
        return SafetySignal("captcha", "verificação humana solicitada")
    if WARNING_TEXT.search(text):
        return SafetySignal("warning", "aviso de atividade incomum ou limite atingido")
    if ERROR_TEXT.search(text) and len(text) < 2000:
        return SafetySignal("error_page", "página de erro")
    return None
