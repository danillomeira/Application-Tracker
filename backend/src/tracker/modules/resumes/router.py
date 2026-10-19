"""Rotas de currículos (docs/06 §Currículos)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from tracker.api.deps import SessionDep, TaskAccepted, get_or_404
from tracker.core import audit
from tracker.core.security import CurrentUser
from tracker.core.storage import get_storage
from tracker.core.tasks import enqueue
from tracker.modules.jobs.models import Job
from tracker.modules.profile import service as profile_service
from tracker.modules.resumes import content as content_mod
from tracker.modules.resumes import service
from tracker.modules.resumes.models import ResumeRender, ResumeTemplate, ResumeVariant
from tracker.modules.resumes.schemas import (
    BaselineIn,
    RenderOut,
    ResumeContent,
    TailorIn,
    TemplateOut,
    ValidationReport,
    VariantDetail,
    VariantOut,
    VariantUpdate,
    WildcardsIn,
)
from tracker.modules.resumes.validator import validate

router = APIRouter(prefix="/resumes", tags=["resumes"])


async def _detail(session: SessionDep, v: ResumeVariant) -> VariantDetail:
    renders = (
        await session.scalars(
            select(ResumeRender).where(ResumeRender.variant_id == v.id).order_by(ResumeRender.rendered_at.desc())
        )
    ).all()
    out = VariantDetail.model_validate(v)
    out.renders = [RenderOut.model_validate(r) for r in renders]
    return out


@router.get("/templates", response_model=list[TemplateOut])
async def templates(session: SessionDep, _user: CurrentUser) -> list[ResumeTemplate]:
    await service.ensure_template(session)
    await session.commit()
    return list((await session.scalars(select(ResumeTemplate))).all())


@router.get("/profiles")
async def wildcard_profiles(_user: CurrentUser) -> dict[str, Any]:
    return {k: {"name": v["name"], "focus": v["focus"]} for k, v in content_mod.WILDCARD_PROFILES.items()}


@router.get("/variants", response_model=list[VariantOut])
async def list_variants(
    session: SessionDep,
    _user: CurrentUser,
    kind: str | None = None,
    job_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[ResumeVariant]:
    stmt = select(ResumeVariant).order_by(ResumeVariant.kind, ResumeVariant.created_at.desc())
    if kind:
        stmt = stmt.where(ResumeVariant.kind == kind)
    if job_id:
        stmt = stmt.where(ResumeVariant.job_id == job_id)
    if not include_archived:
        stmt = stmt.where(ResumeVariant.status != "archived")
    return list((await session.scalars(stmt)).all())


@router.post("/variants/baseline", response_model=VariantDetail, status_code=201)
async def create_baseline(body: BaselineIn, session: SessionDep, _user: CurrentUser) -> VariantDetail:
    """Coringa direto do mestre, sem IA (útil antes de configurar a API do Claude)."""
    if body.profile not in content_mod.WILDCARD_PROFILES:
        raise HTTPException(422, "perfil desconhecido")
    version, master = await profile_service.current_master(session)
    content = content_mod.baseline(master, body.profile, body.language)
    spec = content_mod.WILDCARD_PROFILES[body.profile]
    v = await service.create_variant(
        session,
        master_version=version,
        master=master,
        content=content,
        kind="wildcard",
        slug=f"{body.profile}-{body.language}",
        name=body.name or str(spec["name"]),
        focus={"profile": body.profile, "source": "baseline"},
    )
    await session.commit()
    return await _detail(session, v)


@router.post("/variants/wildcards/generate", response_model=TaskAccepted, status_code=202)
async def generate_wildcards(body: WildcardsIn, session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    await profile_service.current_master(session)
    unknown = [p for p in (body.profiles or []) if p not in content_mod.WILDCARD_PROFILES]
    if unknown:
        raise HTTPException(422, f"perfis desconhecidos: {unknown}")
    tr = await enqueue(session, "ai.resume_wildcards", profiles=body.profiles, languages=body.languages)
    return TaskAccepted(task_id=tr.id)


@router.post("/variants/tailored", response_model=TaskAccepted, status_code=202)
async def tailor(body: TailorIn, session: SessionDep, _user: CurrentUser) -> TaskAccepted:
    await get_or_404(session, Job, body.job_id)
    tr = await enqueue(
        session,
        "ai.resume_tailor",
        entity_type="job",
        entity_id=body.job_id,
        job_id=str(body.job_id),
        base_variant_id=str(body.base_variant_id) if body.base_variant_id else None,
    )
    return TaskAccepted(task_id=tr.id)


@router.get("/variants/{variant_id}", response_model=VariantDetail)
async def get_variant(variant_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> VariantDetail:
    return await _detail(session, await get_or_404(session, ResumeVariant, variant_id))


@router.put("/variants/{variant_id}", response_model=VariantDetail)
async def update_variant(variant_id: uuid.UUID, body: VariantUpdate, session: SessionDep, _user: CurrentUser) -> VariantDetail:
    v = await get_or_404(session, ResumeVariant, variant_id)
    _, master = await profile_service.current_master(session)
    if body.name is not None:
        v.name = body.name
    if body.content is not None:
        v.content = body.content.model_dump(mode="json")
        service.revalidate(v, master)
    if body.status is not None:
        if body.status == "approved" and not v.validation.get("passed"):
            raise HTTPException(422, "corrija as violações do validador antes de aprovar")
        v.status = body.status
    await session.commit()
    return await _detail(session, v)


@router.post("/variants/{variant_id}/approve", response_model=VariantDetail)
async def approve(variant_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> VariantDetail:
    v = await get_or_404(session, ResumeVariant, variant_id)
    _, master = await profile_service.current_master(session)
    service.revalidate(v, master)
    if not v.validation.get("passed"):
        raise HTTPException(422, "corrija as violações do validador antes de aprovar")
    v.status = "approved"
    await audit.record(session, actor="user", action="resume.approve", entity_type="resume_variant", entity_id=v.id)
    await session.commit()
    return await _detail(session, v)


@router.post("/variants/{variant_id}/render", response_model=TaskAccepted, status_code=202)
async def render_variant(
    variant_id: uuid.UUID, session: SessionDep, _user: CurrentUser, job_id: uuid.UUID | None = None
) -> TaskAccepted:
    await get_or_404(session, ResumeVariant, variant_id)
    keywords = None
    if job_id:
        job = await get_or_404(session, Job, job_id)
        keywords = list((job.requirements or {}).get("must", []))
    tr = await enqueue(
        session,
        "docs.resume_render",
        entity_type="resume_variant",
        entity_id=variant_id,
        variant_id=str(variant_id),
        keywords=keywords,
    )
    return TaskAccepted(task_id=tr.id)


@router.get("/variants/{variant_id}/validation", response_model=ValidationReport)
async def variant_validation(variant_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> ValidationReport:
    v = await get_or_404(session, ResumeVariant, variant_id)
    _, master = await profile_service.current_master(session)
    return validate(ResumeContent.model_validate(v.content), master)


@router.get("/renders/{render_id}/pdf")
async def download_pdf(render_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    r = await get_or_404(session, ResumeRender, render_id)
    return Response(
        get_storage().get(r.storage_key),
        media_type="application/pdf",
        headers={"content-disposition": f'inline; filename="{r.filename}"'},
    )


@router.get("/renders/{render_id}/tex")
async def download_tex(render_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    r = await get_or_404(session, ResumeRender, render_id)
    return Response(get_storage().get(r.tex_source_key), media_type="text/plain; charset=utf-8")


@router.post("/cover-letter", response_model=TaskAccepted, status_code=202)
async def cover_letter(
    session: SessionDep, _user: CurrentUser, job_id: uuid.UUID, variant_id: uuid.UUID | None = None
) -> TaskAccepted:
    await get_or_404(session, Job, job_id)
    tr = await enqueue(
        session,
        "ai.cover_letter",
        entity_type="job",
        entity_id=job_id,
        job_id=str(job_id),
        variant_id=str(variant_id) if variant_id else None,
    )
    return TaskAccepted(task_id=tr.id)
