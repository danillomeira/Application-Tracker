"""Pacote de candidatura externa (RF-EXT-02), busca global (RF-DSH-12), exportação e exclusão (RF-PLA-07)."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, text

from tracker.api.deps import SessionDep, get_or_404
from tracker.core import audit
from tracker.core.security import CurrentUser
from tracker.core.storage import get_storage
from tracker.integrations import job_sources
from tracker.models import Base
from tracker.modules.applications.models import Application, ApplicationAnswer
from tracker.modules.companies.models import Company
from tracker.modules.jobs.models import Job, JobSource
from tracker.modules.people.models import Person
from tracker.modules.profile import service as profile_service
from tracker.modules.resumes.models import ResumeRender

router = APIRouter(tags=["data"])

COMMON_QUESTIONS = [
    "Pretensão salarial",
    "Disponibilidade para início",
    "Nível de inglês",
    "Anos de experiência com a stack principal",
    "Por que você quer trabalhar aqui?",
    "LinkedIn",
    "GitHub",
    "Portfólio",
]


@router.get("/applications/{app_id}/package")
async def package(app_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    """Tudo pronto para a candidatura externa: CV, carta, respostas sugeridas e checklist."""
    app = await get_or_404(session, Application, app_id)
    job = await session.get(Job, app.job_id)
    assert job is not None
    company = await session.get(Company, job.company_id)
    render = await session.get(ResumeRender, app.resume_render_id) if app.resume_render_id else None
    _, master = await profile_service.current_master(session)
    from tracker.modules.applications.resolver import FormField, resolve_fields

    questions: list[str] = list(COMMON_QUESTIONS)
    if job.ats_kind == "greenhouse" and company and company.ats_board_token:
        src = await session.scalar(select(JobSource).where(JobSource.job_id == job.id, JobSource.source == "greenhouse"))
        if src:
            try:
                qs = await job_sources.greenhouse_questions(company.ats_board_token, src.external_id)
                questions = [q["label"] for q in qs if q.get("label")] or questions
            except Exception:  # noqa: S110
                pass
    fields = [
        FormField(key=f"q{i}", label=q, kind="textarea" if "por que" in q.lower() or "why" in q.lower() else "text")
        for i, q in enumerate(questions)
    ]
    res = await resolve_fields(session, app, fields, step_index=100)
    await session.commit()
    answers = {f.label: next((r.value for r in res.values if r.key == f.key), None) for f in fields}
    return {
        "application_id": str(app.id),
        "company": company.name if company else "",
        "title": job.title,
        "apply_url": job.apply_url or job.canonical_url,
        "ats": job.ats_kind,
        "resume": {
            "render_id": str(render.id),
            "filename": render.filename,
            "download": f"/api/v1/resumes/renders/{render.id}/pdf",
        }
        if render
        else None,
        "cover_letter": app.cover_letter,
        "answers": answers,
        "pending": [f.label for f in res.pending],
        "contact": master.contact.model_dump(),
        "checklist": [
            "Conferir se o CV anexado é o indicado acima",
            "Colar a carta de apresentação, se houver campo",
            "Revisar as respostas sugeridas antes de enviar",
            "Enviar e clicar em 'enviei' no dashboard",
        ],
    }


@router.get("/search")
async def global_search(q: str, session: SessionDep, _user: CurrentUser) -> dict[str, list[dict[str, Any]]]:
    like = f"%{q}%"
    jobs = (
        await session.execute(
            select(Job, Company)
            .join(Company, Company.id == Job.company_id)
            .where(Job.title.ilike(like) | Company.name.ilike(like))
            .limit(10)
        )
    ).all()
    companies = (await session.scalars(select(Company).where(Company.name.ilike(like)).limit(10))).all()
    people = (
        await session.scalars(select(Person).where(Person.full_name.ilike(like) | Person.email.ilike(like)).limit(10))
    ).all()
    apps = (
        await session.execute(
            select(Application, Job, Company)
            .join(Job, Job.id == Application.job_id)
            .join(Company, Company.id == Job.company_id)
            .where(Job.title.ilike(like) | Company.name.ilike(like))
            .limit(10)
        )
    ).all()
    return {
        "jobs": [{"id": str(j.id), "title": j.title, "company": c.name} for j, c in jobs],
        "companies": [{"id": str(c.id), "name": c.name} for c in companies],
        "people": [{"id": str(p.id), "name": p.full_name, "role": p.role} for p in people],
        "applications": [{"id": str(a.id), "title": j.title, "company": c.name, "status": a.status} for a, j, c in apps],
    }


@router.post("/export")
async def export_all(session: SessionDep, _user: CurrentUser) -> Response:
    """Exportação completa: JSON por tabela + PDFs (RF-PLA-07). Segredos ficam de fora."""
    skip = {"oauth_credential", "alembic_version"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for table in Base.metadata.sorted_tables:
            if table.name in skip:
                continue
            rows = (await session.execute(select(table))).mappings().all()
            data = [{k: v for k, v in r.items() if k not in ("embedding", "question_embedding")} for r in rows]
            z.writestr(f"data/{table.name}.json", json.dumps(data, default=str, ensure_ascii=False, indent=1))
        storage = get_storage()
        for r in (await session.scalars(select(ResumeRender))).all():
            try:
                z.writestr(f"resumes/{r.filename.removesuffix('.pdf')}_{r.sha256[:8]}.pdf", storage.get(r.storage_key))
            except Exception:  # noqa: S110
                pass
        apps = (
            await session.execute(
                select(Application, Job, Company)
                .join(Job, Job.id == Application.job_id)
                .join(Company, Company.id == Job.company_id)
            )
        ).all()
        lines = ["empresa;vaga;status;enviada_em;canal"]
        lines += [f"{c.name};{j.title};{a.status};{a.submitted_at or ''};{a.channel}" for a, j, c in apps]
        z.writestr("candidaturas.csv", "\n".join(lines))
    await audit.record(session, actor="user", action="data.export")
    await session.commit()
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"content-disposition": f'attachment; filename="application-tracker-{stamp}.zip"'},
    )


class DeleteAllIn(BaseModel):
    confirm: str


@router.delete("/data")
async def delete_all(body: DeleteAllIn, session: SessionDep, _user: CurrentUser) -> dict[str, str]:
    if body.confirm != "APAGAR TUDO":
        raise HTTPException(422, "confirme com o texto 'APAGAR TUDO'")
    tables = [t.name for t in Base.metadata.sorted_tables if t.name != "alembic_version"]
    await session.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    storage = get_storage()
    for key in storage.list(""):
        if not key.startswith("backups/"):
            storage.delete(key)
    await session.commit()
    return {"status": "apagado"}


__all__ = ["ApplicationAnswer"]
