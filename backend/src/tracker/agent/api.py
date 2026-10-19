"""Cliente da API para o agente local (token de dispositivo, só conexões de saída)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import httpx


class AgentApi(Protocol):
    async def hello(self, version: str, sites: list[str]) -> dict[str, Any]: ...
    async def next_job(self, kinds: list[str] | None = None) -> dict[str, Any]: ...
    async def heartbeat(self, job_id: str) -> dict[str, Any]: ...
    async def step(
        self, job_id: str, index: int, title: str, log: str | None = None, screenshot_key: str | None = None
    ) -> None: ...
    async def artifact(self, job_id: str, name: str, data: bytes, content_type: str) -> str: ...
    async def checkpoint(self, job_id: str, state: dict[str, Any]) -> None: ...
    async def resolve(self, job_id: str, step_index: int, fields: list[dict[str, Any]]) -> dict[str, Any]: ...
    async def resume(self, application_id: str, dest: Path) -> Path: ...
    async def review(self, job_id: str, summary: str | None, screenshot_key: str | None) -> dict[str, Any]: ...
    async def submitted(
        self, job_id: str, evidence: str | None, screenshot_key: str | None, already_applied: bool = False
    ) -> None: ...
    async def safety_stop(self, job_id: str, kind: str, message: str, url: str | None) -> None: ...
    async def fail(self, job_id: str, error: str, closed: bool = False) -> None: ...
    async def search_results(self, job_id: str, jobs: list[dict[str, Any]], done: bool = True) -> dict[str, Any]: ...
    async def messages(self, job_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]: ...
    async def done(self, job_id: str) -> None: ...
    async def login_ok(self) -> None: ...


class HttpAgentApi:
    def __init__(self, base_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/api/v1/agent",
            timeout=60,
            headers={"Authorization": f"Device {token}"},
            transport=transport,
        )

    async def _post(self, path: str, **kw: Any) -> dict[str, Any]:
        r = await self.client.post(path, **kw)
        r.raise_for_status()
        return r.json() if r.content else {}

    async def close(self) -> None:
        await self.client.aclose()

    async def hello(self, version: str, sites: list[str]) -> dict[str, Any]:
        import platform

        return await self._post("/hello", json={"version": version, "sites": sites, "machine": platform.node()})

    async def next_job(self, kinds: list[str] | None = None) -> dict[str, Any]:
        return await self._post("/jobs/next", json={"kinds": kinds})

    async def heartbeat(self, job_id: str) -> dict[str, Any]:
        return await self._post(f"/jobs/{job_id}/heartbeat")

    async def step(self, job_id: str, index: int, title: str, log: str | None = None, screenshot_key: str | None = None) -> None:
        await self._post(
            f"/jobs/{job_id}/step", json={"index": index, "title": title, "log": log, "screenshot_key": screenshot_key}
        )

    async def artifact(self, job_id: str, name: str, data: bytes, content_type: str) -> str:
        r = await self._post(f"/jobs/{job_id}/artifact", files={"file": (name, data, content_type)}, data={"name": name})
        return str(r["key"])

    async def checkpoint(self, job_id: str, state: dict[str, Any]) -> None:
        await self._post(f"/jobs/{job_id}/checkpoint", json={"state": state})

    async def resolve(self, job_id: str, step_index: int, fields: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._post(f"/jobs/{job_id}/resolve", json={"step_index": step_index, "fields": fields})

    async def resume(self, application_id: str, dest: Path) -> Path:
        r = await self.client.get(f"/applications/{application_id}/resume")
        r.raise_for_status()
        path = dest / (r.headers.get("x-filename") or "resume.pdf")
        path.write_bytes(r.content)
        return path

    async def review(self, job_id: str, summary: str | None, screenshot_key: str | None) -> dict[str, Any]:
        return await self._post(f"/jobs/{job_id}/review", json={"summary": summary, "screenshot_key": screenshot_key})

    async def submitted(
        self, job_id: str, evidence: str | None, screenshot_key: str | None, already_applied: bool = False
    ) -> None:
        await self._post(
            f"/jobs/{job_id}/submitted",
            json={"evidence": evidence, "screenshot_key": screenshot_key, "already_applied": already_applied},
        )

    async def safety_stop(self, job_id: str, kind: str, message: str, url: str | None) -> None:
        await self._post(f"/jobs/{job_id}/safety-stop", json={"kind": kind, "message": message, "url": url})

    async def fail(self, job_id: str, error: str, closed: bool = False) -> None:
        await self._post(f"/jobs/{job_id}/fail", json={"error": error, "closed": closed})

    async def search_results(self, job_id: str, jobs: list[dict[str, Any]], done: bool = True) -> dict[str, Any]:
        return await self._post(f"/jobs/{job_id}/search-results", json={"jobs": jobs, "done": done})

    async def messages(self, job_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._post(f"/jobs/{job_id}/messages", json={"messages": messages})

    async def done(self, job_id: str) -> None:
        await self._post(f"/jobs/{job_id}/done")

    async def login_ok(self) -> None:
        await self._post("/login-ok")
