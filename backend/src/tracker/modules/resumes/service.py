"""Serviço de currículos: variantes, render/armazenamento, escolha por vaga."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import settings_store
from tracker.core.storage import get_storage
from tracker.integrations.embeddings import cosine, embed_one
from tracker.modules.jobs.models import Job
from tracker.modules.profile.schemas import MasterProfile
from tracker.modules.resumes import ats, render
from tracker.modules.resumes.content import content_text
from tracker.modules.resumes.models import ResumeRender, ResumeTemplate, ResumeVariant
from tracker.modules.resumes.schemas import ResumeContent
from tracker.modules.resumes.validator import validate


async def ensure_template(session: AsyncSession, slug: str = "classic") -> ResumeTemplate:
    row = await session.scalar(select(ResumeTemplate).where(ResumeTemplate.slug == slug))
    if row is None:
        row = ResumeTemplate(
            slug=slug,
            name=slug.title(),
            engine="latex",
            path=f"templates/resumes/{slug}",
            supports_languages=["en", "pt"],
        )
        session.add(row)
        await session.flush()
    return row


async def create_variant(
    session: AsyncSession,
    *,
    master_version: int,
    master: MasterProfile,
    content: ResumeContent,
    kind: str,
    slug: str,
    name: str,
    focus: dict[str, Any] | None = None,
    changes: list[Any] | None = None,
    job_id: Any = None,
    parent_variant_id: Any = None,
    status: str = "draft",
) -> ResumeVariant:
    tpl = await ensure_template(session)
    report = validate(content, master)
    variant = ResumeVariant(
        kind=kind,
        slug=slug,
        name=name,
        language=content.language,
        focus=focus or {},
        content=content.model_dump(mode="json"),
        changes=changes or [],
        master_version=master_version,
        template_id=tpl.id,
        job_id=job_id,
        parent_variant_id=parent_variant_id,
        status=status,
        validation=report.model_dump(mode="json"),
        embedding=embed_one(content_text(content)),
    )
    session.add(variant)
    await session.flush()
    return variant


def revalidate(variant: ResumeVariant, master: MasterProfile) -> None:
    content = ResumeContent.model_validate(variant.content)
    variant.validation = validate(content, master).model_dump(mode="json")
    variant.embedding = embed_one(content_text(content))


class ValidationFailed(Exception):
    pass


async def render_variant(
    session: AsyncSession,
    variant: ResumeVariant,
    master: MasterProfile,
    keywords: list[str] | None = None,
) -> ResumeRender:
    """Valida, compila e salva o PDF (imutável, com hash). Violação bloqueia o render."""
    content = ResumeContent.model_validate(variant.content)
    report = validate(content, master)
    variant.validation = report.model_dump(mode="json")
    if not report.passed:
        await session.flush()
        raise ValidationFailed("; ".join(v.text for v in report.violations[:5]))
    tpl_slug = "classic"
    tex = render.render_tex(content, master, tpl_slug)
    compiled = await asyncio.to_thread(render.compile_pdf, tex, tpl_slug)
    filename = render.pdf_filename(master, variant.name, content.language)
    storage = get_storage()
    pdf_key = storage.put(f"resumes/{variant.id}/{compiled.sha256[:12]}/{filename}", compiled.pdf, "application/pdf")
    tex_key = storage.put(f"resumes/{variant.id}/{compiled.sha256[:12]}/source.tex", tex.encode(), "application/x-tex")
    report_ats = ats.check(compiled.text, master, content.language, keywords)
    row = ResumeRender(
        variant_id=variant.id,
        storage_key=pdf_key,
        tex_source_key=tex_key,
        filename=filename,
        sha256=compiled.sha256,
        ats_text=compiled.text,
        ats_report=report_ats.model_dump(mode="json"),
        page_count=compiled.page_count,
    )
    session.add(row)
    await session.flush()
    return row


async def latest_render(session: AsyncSession, variant_id: Any) -> ResumeRender | None:
    return await session.scalar(
        select(ResumeRender).where(ResumeRender.variant_id == variant_id).order_by(ResumeRender.rendered_at.desc()).limit(1)
    )


def must_coverage(text: str, job: Job) -> float:
    must = list((job.requirements or {}).get("must") or [])
    cov, _ = ats.keyword_coverage(text, must)
    return cov


async def select_for_job(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Escolhe o coringa (RF-CV-03): 0,6 × cosseno + 0,4 × cobertura dos obrigatórios."""
    cfg = await settings_store.get(session, "resume")
    threshold = float(cfg["match_threshold"])
    rows = list(
        (
            await session.scalars(
                select(ResumeVariant).where(ResumeVariant.kind == "wildcard", ResumeVariant.status == "approved")
            )
        ).all()
    )
    same_lang = [v for v in rows if v.language == job.language] or rows
    scores: dict[str, float] = {}
    best: ResumeVariant | None = None
    best_score = -1.0
    for v in same_lang:
        text = content_text(ResumeContent.model_validate(v.content))
        sim = cosine(
            list(v.embedding) if v.embedding is not None else None,
            list(job.embedding) if job.embedding is not None else None,
        )
        score = round(0.6 * max(sim, 0.0) + 0.4 * must_coverage(text, job), 4)
        scores[str(v.id)] = score
        if score > best_score:
            best, best_score = v, score
    return {
        "best_variant_id": best.id if best else None,
        "best_score": best_score if best else None,
        "scores": scores,
        "needs_tailored": best is None or best_score < threshold,
        "threshold": threshold,
    }
