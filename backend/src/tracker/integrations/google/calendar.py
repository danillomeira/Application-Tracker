"""Cliente Google Calendar (REST): freebusy e eventos no calendário primário."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

BASE = "https://www.googleapis.com/calendar/v3"

_transport: httpx.AsyncBaseTransport | None = None


def set_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t


class CalendarError(Exception):
    pass


class Calendar:
    def __init__(self, access_token: str) -> None:
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def _req(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, transport=_transport) as c:
            r = await c.request(method, f"{BASE}{path}", headers=self.headers, **kw)
        if r.status_code >= 400:
            raise CalendarError(f"Calendar {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    async def freebusy(self, start: datetime, end: datetime, tz: str) -> list[tuple[datetime, datetime]]:
        data = await self._req(
            "POST",
            "/freeBusy",
            json={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "timeZone": tz,
                "items": [{"id": "primary"}],
            },
        )
        busy = data.get("calendars", {}).get("primary", {}).get("busy", [])
        return [
            (
                datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
                datetime.fromisoformat(b["end"].replace("Z", "+00:00")),
            )
            for b in busy
        ]

    async def insert(self, event: dict[str, Any]) -> str:
        data = await self._req("POST", "/calendars/primary/events", json=event, params={"conferenceDataVersion": 0})
        return str(data["id"])

    async def patch(self, event_id: str, event: dict[str, Any]) -> None:
        await self._req("PATCH", f"/calendars/primary/events/{event_id}", json=event)

    async def delete(self, event_id: str) -> None:
        await self._req("DELETE", f"/calendars/primary/events/{event_id}")


def event_body(
    *,
    title: str,
    start: datetime,
    end: datetime,
    tz: str,
    description: str = "",
    location: str | None = None,
    application_id: str | None = None,
    reminders_min: list[int] | None = None,
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": m} for m in (reminders_min or [1440, 60])],
        },
    }
    if location:
        body["location"] = location
    if application_id:
        body["extendedProperties"] = {"private": {"tracker_application_id": application_id}}
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    return body
