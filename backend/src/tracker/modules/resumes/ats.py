"""Checagem ATS do PDF gerado (RF-CV-06, docs/11 §7)."""

from __future__ import annotations

import re

from tracker.modules.profile import facts
from tracker.modules.profile.schemas import MasterProfile
from tracker.modules.resumes.content import LABELS
from tracker.modules.resumes.schemas import AtsCheck, AtsReport


def keyword_coverage(text: str, keywords: list[str]) -> tuple[float, list[str]]:
    if not keywords:
        return 1.0, []
    plain = " " + facts.norm(text) + " "
    missing = []
    for kw in keywords:
        k = facts.norm(re.sub(r"\(.*?\)", "", kw))
        if not k or not re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", plain):
            missing.append(kw)
    return round(1 - len(missing) / len(keywords), 3), missing


def check(text: str, master: MasterProfile, lang: str, keywords: list[str] | None = None) -> AtsReport:
    labels = LABELS.get(lang, LABELS["en"])
    norm_text = facts.norm(text)
    c = master.contact
    checks = [
        AtsCheck(name="nome", ok=facts.norm(c.full_name) in norm_text),
        AtsCheck(name="e-mail", ok=c.email.lower() in text.lower()),
        AtsCheck(name="telefone", ok=bool(c.phone) and re.sub(r"\D", "", c.phone or "") in re.sub(r"\D", "", text)),
    ]
    for key in ("summary", "skills", "experience", "education"):
        title = labels[key]
        checks.append(AtsCheck(name=f"seção {title}", ok=facts.norm(title) in norm_text))
    dates_ok = bool(re.search(r"(?:[A-Z][a-z]{2}|[a-z]{3}) \d{4}", text))
    checks.append(AtsCheck(name="datas legíveis", ok=dates_ok))
    broken = re.search(r"[�]|\(cid:\d+\)", text)
    checks.append(AtsCheck(name="sem caracteres quebrados", ok=broken is None, detail=broken.group(0) if broken else None))
    order = [norm_text.find(facts.norm(labels[k])) for k in ("summary", "skills", "experience")]
    checks.append(AtsCheck(name="ordem de leitura", ok=all(i >= 0 for i in order) and order == sorted(order)))
    coverage, missing = keyword_coverage(text, keywords or [])
    return AtsReport(
        ok=all(ch.ok for ch in checks),
        checks=checks,
        keyword_coverage=coverage if keywords else None,
        missing_keywords=missing,
    )
