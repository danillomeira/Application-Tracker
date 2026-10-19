"""Rotas de insights (RF-ANA) e importação do GitHub (RF-PER-03)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from tracker.api.deps import SessionDep, TaskAccepted
from tracker.core.security import CurrentUser
from tracker.core.tasks import dispatch, enqueue
from tracker.modules.analytics import service
from tracker.modules.platform.models import Setting
from tracker.modules.profile import service as profile_service

router = APIRouter(prefix="/insights", tags=["insights"])
github_router = APIRouter(prefix="/profile/github", tags=["profile"])


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


@router.get("/funnel")
async def funnel(session: SessionDep, _user: CurrentUser, days: int = 30) -> dict[str, Any]:
    return await service.funnel(session, _since(days))


@router.get("/performance")
async def performance(session: SessionDep, _user: CurrentUser, days: int = 90) -> dict[str, Any]:
    return await service.performance(session, _since(days))


@router.get("/skill-gaps")
async def skill_gaps(session: SessionDep, _user: CurrentUser, days: int = 60) -> list[dict[str, Any]]:
    return await service.skill_gaps(session, days)


@router.get("/rejections")
async def rejections(session: SessionDep, _user: CurrentUser, days: int = 180) -> dict[str, Any]:
    return await service.rejections(session, _since(days))


@router.get("/goals")
async def goals(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    return await service.goals(session)


@router.get("/wildcard-suggestions")
async def wildcard_suggestions(session: SessionDep, _user: CurrentUser) -> list[dict[str, Any]]:
    return await service.wildcard_suggestions(session)


async def _stored(session: SessionDep, key: str) -> dict[str, Any] | None:
    row = await session.scalar(select(Setting).where(Setting.key == key))
    return row.value if row else None


@router.get("/weekly-report")
async def weekly_report(session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    return await _stored(session, "weekly_report") or {"metrics": await service.weekly_metrics(session)}


@router.post("/weekly-report", status_code=202)
async def regenerate_weekly(_user: CurrentUser) -> dict[str, str]:
    dispatch("ai.weekly_report")
    return {"status": "queued"}


@router.get("/study-plan")
async def study_plan(session: SessionDep, _user: CurrentUser) -> dict[str, Any] | None:
    return await _stored(session, "study_plan")


@router.post("/study-plan", response_model=TaskAccepted, status_code=202)
async def make_study_plan(session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    tr = await enqueue(session, "ai.study_plan")
    return TaskAccepted(task_id=tr.id)


class LinkedinIn(BaseModel):
    current_profile: str = ""


@router.get("/linkedin-profile")
async def linkedin_suggestions(session: SessionDep, _user: CurrentUser) -> dict[str, Any] | None:
    return await _stored(session, "linkedin_suggestions")


@router.post("/linkedin-profile", response_model=TaskAccepted, status_code=202)
async def make_linkedin_suggestions(body: LinkedinIn, session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    tr = await enqueue(session, "ai.linkedin_optimize", current_profile=body.current_profile)
    return TaskAccepted(task_id=tr.id)


# ---------- GitHub ----------
_gh_transport: httpx.AsyncBaseTransport | None = None


@github_router.get("/repos")
async def github_repos(session: SessionDep, _user: CurrentUser, user: str | None = None) -> list[dict[str, Any]]:
    if not user:
        _, master = await profile_service.current_master(session)
        user = (master.contact.github or "").rstrip("/").split("/")[-1]
    if not user:
        raise HTTPException(422, "informe o usuário do GitHub")
    async with httpx.AsyncClient(timeout=20, transport=_gh_transport) as c:
        r = await c.get(
            f"https://api.github.com/users/{user}/repos",
            params={"sort": "updated", "per_page": 100, "type": "owner"},
            headers={"Accept": "application/vnd.github+json"},
        )
    if r.status_code != 200:
        raise HTTPException(502, f"GitHub respondeu {r.status_code}")
    return [
        {
            "name": x["name"],
            "description": x.get("description"),
            "language": x.get("language"),
            "stars": x.get("stargazers_count", 0),
            "url": x.get("html_url"),
            "topics": x.get("topics", []),
            "fork": x.get("fork", False),
            "updated_at": x.get("updated_at"),
        }
        for x in r.json()
        if not x.get("fork")
    ]


class GithubImportIn(BaseModel):
    repos: list[dict[str, Any]]


@github_router.post("/import")
async def github_import(body: GithubImportIn, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    """Adiciona repositórios escolhidos como projetos do mestre (nova versão; descrição = a do repositório)."""
    version, master = await profile_service.current_master(session)
    data = master.model_dump(mode="json")
    existing = {p["id"] for p in data.get("projects", [])}
    added = []
    for repo in body.repos:
        pid = repo["name"].lower()
        if pid in existing or not repo.get("description"):
            continue
        skills = [s for s in [repo.get("language"), *repo.get("topics", [])] if s]
        data.setdefault("projects", []).append(
            {
                "id": pid,
                "name": repo["name"],
                "url": (repo.get("url") or "").removeprefix("https://"),
                "description_en": repo["description"],
                "skills": skills,
                "source": "github",
            }
        )
        added.append(pid)
    if added:
        await profile_service.save_master(session, data, "manual_edit", f"projetos do GitHub: {', '.join(added)}")
        await session.commit()
    return {"added": added, "previous_version": version}
