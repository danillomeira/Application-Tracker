"""Alertas de vagas do LinkedIn que chegam no seu Gmail → vagas em "Vagas" (sem robô, sem acessar o LinkedIn).

O texto do alerta lista cada vaga como: título, empresa, local e um link .../jobs/view/<id>.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tracker.integrations.google.gmail import ParsedEmail

JOB_LINK = re.compile(r"https?://(?:[\w.]*\.)?linkedin\.com/(?:comm/)?jobs/view/(\d+)")
ALERT_SENDERS = ("jobalerts-noreply@linkedin.com", "jobs-noreply@linkedin.com", "jobs-listings@linkedin.com")
NOISE = re.compile(
    # linha inteira (senão "Novo Nordisk" ou "Apply Digital" seriam descartadas como ruído)
    r"^(?:(?:view job|ver vaga|apply|candidatar|easy apply|candidatura simplificada|actively recruiting|recrutando ativamente|"
    r"new|novo|nova|promoted|promovida|be an early applicant|seja um dos primeiros|see all jobs|ver todas)[\s:.!]*|[-=_*·•\s]+)$"
    r"|^\d+ (?:connections?|conex|applicants?|candidat)",
    re.I,
)


@dataclass
class AlertJob:
    external_id: str
    title: str
    company: str
    location: str | None
    easy_apply: bool


def is_linkedin_alert(email: ParsedEmail) -> bool:
    sender = email.from_addr.lower()
    return any(sender.endswith(s) or sender == s for s in ALERT_SENDERS) and bool(JOB_LINK.search(email.body_text))


def parse_alert(email: ParsedEmail) -> list[AlertJob]:
    lines = [ln.strip() for ln in email.body_text.splitlines()]
    out: dict[str, AlertJob] = {}
    for i, line in enumerate(lines):
        m = JOB_LINK.search(line)
        if not m or m.group(1) in out:
            continue
        # sobe a partir do link pegando as linhas de texto da vaga (até a anterior em branco/separador)
        block: list[str] = []
        j = i - 1
        while j >= 0 and len(block) < 6:
            prev = lines[j]
            if JOB_LINK.search(prev) or re.fullmatch(r"[-=_]{3,}", prev or "---"):
                break
            if prev and not NOISE.match(prev) and "http" not in prev:
                block.insert(0, prev.removeprefix("View job:").strip())
            j -= 1
        info = [b for b in block if b]
        if len(info) < 2:
            continue
        window = " ".join(lines[max(0, j) : i + 2]).lower()
        out[m.group(1)] = AlertJob(
            external_id=m.group(1),
            title=info[0][:300],
            company=info[1][:200],
            location=info[2][:200] if len(info) > 2 else None,
            easy_apply="easy apply" in window or "candidatura simplificada" in window,
        )
    return list(out.values())
