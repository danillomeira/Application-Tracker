"""Cliente Gmail (REST). Leitura + criação de RASCUNHOS. Nunca envia (ADR-009, docs/12 §3)."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

import httpx

from tracker.modules.jobs.normalize import html_to_text

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

_transport: httpx.AsyncBaseTransport | None = None


def set_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t


class GmailError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Gmail {status}: {message}")
        self.status = status


@dataclass
class ParsedEmail:
    gmail_id: str
    thread_id: str | None
    from_addr: str
    from_name: str | None
    to_addrs: list[str]
    subject: str
    snippet: str
    body_text: str
    received_at: datetime
    labels: list[str] = field(default_factory=list)
    message_id_header: str | None = None


class Gmail:
    def __init__(self, access_token: str) -> None:
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def _req(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, transport=_transport) as c:
            r = await c.request(method, f"{BASE}{path}", headers=self.headers, **kw)
        if r.status_code >= 400:
            raise GmailError(r.status_code, r.text[:300])
        return r.json() if r.content else {}

    async def profile(self) -> dict[str, Any]:
        return await self._req("GET", "/profile")

    async def history(self, start_history_id: str) -> tuple[list[str], str | None]:
        ids: list[str] = []
        page: str | None = None
        latest: str | None = None
        while True:
            params: dict[str, Any] = {"startHistoryId": start_history_id, "historyTypes": "messageAdded"}
            if page:
                params["pageToken"] = page
            data = await self._req("GET", "/history", params=params)
            latest = data.get("historyId", latest)
            for h in data.get("history", []):
                for m in h.get("messagesAdded", []):
                    ids.append(m["message"]["id"])
            page = data.get("nextPageToken")
            if not page:
                return list(dict.fromkeys(ids)), latest

    async def list_ids(self, query: str, max_results: int = 200) -> list[str]:
        data = await self._req("GET", "/messages", params={"q": query, "maxResults": max_results})
        return [m["id"] for m in data.get("messages", [])]

    async def get(self, msg_id: str) -> ParsedEmail:
        return parse_message(await self._req("GET", f"/messages/{msg_id}", params={"format": "full"}))

    async def watch(self, topic: str) -> dict[str, Any]:
        return await self._req("POST", "/watch", json={"topicName": topic, "labelIds": ["INBOX"]})

    async def labels(self) -> dict[str, str]:
        data = await self._req("GET", "/labels")
        return {lb["name"]: lb["id"] for lb in data.get("labels", [])}

    async def ensure_label(self, name: str, cache: dict[str, str]) -> str:
        if name in cache:
            return cache[name]
        data = await self._req(
            "POST", "/labels", json={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        )
        cache[name] = data["id"]
        return data["id"]

    async def add_labels(self, msg_id: str, label_ids: list[str]) -> None:
        """Só adiciona marcadores (escopo gmail.modify). Nunca envia, apaga ou arquiva."""
        await self._req("POST", f"/messages/{msg_id}/modify", json={"addLabelIds": label_ids})

    async def create_draft(
        self, to: str, subject: str, body: str, thread_id: str | None = None, in_reply_to: str | None = None
    ) -> str:
        msg = MIMEText(body, "plain", "utf-8")
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        payload: dict[str, Any] = {"message": {"raw": raw}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        data = await self._req("POST", "/drafts", json=payload)
        return str(data["id"])


def _b64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _walk(part: dict[str, Any], out: dict[str, list[str]]) -> None:
    mime = part.get("mimeType", "")
    body = (part.get("body") or {}).get("data")
    if body and mime in ("text/plain", "text/html"):
        out.setdefault(mime, []).append(_b64(body))
    for p in part.get("parts", []) or []:
        _walk(p, out)


def parse_message(m: dict[str, Any]) -> ParsedEmail:
    payload = m.get("payload") or {}
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    parts: dict[str, list[str]] = {}
    _walk(payload, parts)
    text = "\n".join(parts.get("text/plain", [])) or html_to_text("\n".join(parts.get("text/html", [])))
    try:
        received = parsedate_to_datetime(headers["date"]) if "date" in headers else None
    except (TypeError, ValueError):
        received = None
    if received is None:
        received = datetime.fromtimestamp(int(m.get("internalDate", "0")) / 1000, UTC)
    to = [parseaddr(x)[1] for x in re.split(r",\s*", headers.get("to", "")) if x]
    return ParsedEmail(
        gmail_id=m["id"],
        thread_id=m.get("threadId"),
        from_addr=addr.lower(),
        from_name=name or None,
        to_addrs=to,
        subject=headers.get("subject", ""),
        snippet=m.get("snippet", ""),
        body_text=text.strip(),
        received_at=received if received.tzinfo else received.replace(tzinfo=UTC),
        labels=m.get("labelIds", []),
        message_id_header=headers.get("message-id"),
    )
