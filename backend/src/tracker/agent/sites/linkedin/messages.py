"""Leitura de conversas novas do LinkedIn (somente leitura, RF-ACO-09)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from playwright.async_api import Page

from tracker.agent import safety
from tracker.agent.api import AgentApi
from tracker.agent.human import Pace
from tracker.agent.sites.linkedin.easy_apply import SELECTORS, StopJob

THREAD_JS = r"""
(sel) => Array.from(document.querySelectorAll(sel)).slice(-6).map((li, i) => {
  const name = (li.querySelector('[class*="profile-link"], [class*="sender"], h3, .msg-s-message-group__name')?.innerText || '').trim();
  const body = (li.querySelector('[class*="event__content"], [class*="message-body"], p')?.innerText || li.innerText || '').trim();
  const link = li.querySelector('a[href*="/in/"]')?.href || null;
  return {idx: i, from_name: name, text: body, from_profile_url: link};
}).filter(m => m.text)
"""


async def run(page: Page, job: dict[str, Any], api: AgentApi, pace: Pace) -> int:
    jid = job["id"]
    sel = SELECTORS["messaging"]
    await page.goto(SELECTORS["messaging_url"], wait_until="domcontentloaded")
    await pace.pause()
    sig = await safety.check(page)
    if sig:
        await api.safety_stop(jid, sig.kind, sig.message, page.url)
        raise StopJob(sig.kind)
    convs = page.locator(sel["conversation"])
    n = min(await convs.count(), int(sel["max_conversations"]))
    out: list[dict[str, Any]] = []
    for i in range(n):
        conv = convs.nth(i)
        if await conv.locator(sel["unread_marker"]).count() == 0:
            continue
        await pace.click(conv)
        href = await conv.locator("a").first.get_attribute("href") if await conv.locator("a").count() else None
        conv_id = (href or f"conv-{i}").rstrip("/").split("/")[-1]
        for m in await page.evaluate(THREAD_JS, sel["message_item"]):
            out.append(
                {
                    "conversation_id": conv_id,
                    "message_id": f"{conv_id}-{abs(hash(m['text'])) % 10**12}",
                    "from_name": m["from_name"],
                    "from_profile_url": m["from_profile_url"],
                    "text": m["text"][:5000],
                    "received_at": datetime.now(UTC).isoformat(),
                }
            )
    await api.messages(jid, out)
    return len(out)
