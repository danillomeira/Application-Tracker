"""Busca de vagas no LinkedIn (RF-VAG-02): poucas páginas, ritmo humano, só leitura."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from playwright.async_api import Page

from tracker.agent import safety
from tracker.agent.api import AgentApi
from tracker.agent.human import Pace
from tracker.agent.sites.linkedin.easy_apply import SELECTORS, StopJob

WT = {"onsite": "1", "remote": "2", "hybrid": "3"}

CARDS_JS = r"""
(sel) => {
  const seen = new Set(); const out = [];
  document.querySelectorAll(sel).forEach(a => {
    const m = (a.getAttribute('href') || '').match(/\/jobs\/view\/(\d+)/); if (!m || seen.has(m[1])) return;
    seen.add(m[1]);
    const card = a.closest('li, [data-job-id], div') || a;
    const lines = (card.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    out.push({external_id: m[1], title: (a.innerText || lines[0] || '').trim().split('\n')[0],
              company: lines[1] || '', location: lines[2] || '',
              easy_apply: /easy apply|candidatura simplificada/i.test(card.innerText || ''),
              url: 'https://www.linkedin.com/jobs/view/' + m[1] + '/'});
  });
  return out;
}
"""


def search_url(query: str, filters: dict[str, Any]) -> str:
    params: dict[str, str] = {
        "keywords": query.replace("|", " OR "),
        "f_AL": "true",
        "sortBy": "DD",
        "f_TPR": f"r{int(filters.get('posted_within_hours', 24)) * 3600}",
    }
    if filters.get("location"):
        params["location"] = filters["location"]
    wms = [WT[w] for w in filters.get("work_models", []) if w in WT]
    if wms:
        params["f_WT"] = ",".join(wms)
    return f"{SELECTORS['search_url']}?{urlencode(params)}"


def parse_posted(text: str) -> datetime | None:
    m = re.search(r"(\d+)\s*(minute|minuto|hour|hora|day|dia|week|semana|month|m[eê]s)", text, re.I)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    delta = (
        timedelta(minutes=n)
        if unit.startswith("min")
        else timedelta(hours=n)
        if unit.startswith(("hour", "hora"))
        else timedelta(days=n)
        if unit.startswith(("day", "dia"))
        else timedelta(weeks=n)
        if unit.startswith(("week", "semana"))
        else timedelta(days=30 * n)
    )
    return datetime.now(UTC) - delta


async def run(page: Page, job: dict[str, Any], api: AgentApi, pace: Pace) -> int:
    jid, p = job["id"], job["payload"]
    await page.goto(search_url(p.get("query", ""), p.get("filters") or {}), wait_until="domcontentloaded")
    await pace.pause()
    sig = await safety.check(page)
    if sig:
        await api.safety_stop(jid, sig.kind, sig.message, page.url)
        raise StopJob(sig.kind)
    cards = await page.evaluate(CARDS_JS, SELECTORS["search"]["job_link"])
    cards = cards[: int(SELECTORS["search"]["max_per_search"])]
    results = []
    for c in cards:
        link = page.locator(f"a[href*='/jobs/view/{c['external_id']}']").first
        try:
            await pace.click(link)
            pane = page.locator(SELECTORS["search"]["detail_pane"]).first
            text = await pane.inner_text(timeout=8000)
        except Exception:  # noqa: S112 (cartão que não abriu: segue para o próximo)
            continue
        sig = await safety.check(page)
        if sig:
            await api.search_results(jid, results, done=False)
            await api.safety_stop(jid, sig.kind, sig.message, page.url)
            raise StopJob(sig.kind)
        m = re.search(SELECTORS["search"]["applicants_regex"], text, re.I)
        posted = parse_posted(text[:600])
        results.append(
            {
                **c,
                "description": text[:15000],
                "applicants": int(re.sub(r"[.,]", "", m.group(1))) if m else None,
                "posted_at": posted.isoformat() if posted else None,
                "easy_apply": c["easy_apply"] or bool(re.search(r"easy apply|candidatura simplificada", text, re.I)),
            }
        )
    await api.search_results(jid, results, done=True)
    return len(results)
