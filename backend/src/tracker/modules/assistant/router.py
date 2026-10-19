"""API do assistente do navegador (extensão Chrome/Edge). Auth: `Authorization: Extension <token>` ou sessão."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from tracker.api.deps import SessionDep
from tracker.core import audit, events, settings_store
from tracker.core.security import SESSION_COOKIE, CurrentUser, read_session
from tracker.core.storage import get_storage
from tracker.core.tasks import dispatch
from tracker.integrations.claude.client import AIError, AIRequest, get_ai, load_prompt, sessionmaker_from
from tracker.modules.applications import service as app_service
from tracker.modules.applications.models import ApplicationAnswer
from tracker.modules.applications.resolver import FormField, resolve_core
from tracker.modules.assistant import service
from tracker.modules.jobs import service as job_service
from tracker.modules.jobs.models import Job
from tracker.modules.jobs.normalize import RawJob, detect_language, normalize_title
from tracker.modules.jobs.schemas import JobNormalized
from tracker.modules.notifications.service import notify
from tracker.modules.profile import service as profile_service
from tracker.modules.profile.models import AnswerBankEntry
from tracker.modules.resumes import service as resume_service
from tracker.modules.resumes.models import ResumeRender, ResumeVariant

router = APIRouter(prefix="/assistant", tags=["assistant"])


async def assistant_auth(request: Request, session: SessionDep, authorization: Annotated[str | None, Header()] = None) -> str:
    if read_session(request.cookies.get(SESSION_COOKIE)):
        return "session"
    if authorization and authorization.startswith("Extension "):
        cfg = await settings_store.get(session, "extension")
        digest = hashlib.sha256(authorization.removeprefix("Extension ").strip().encode()).hexdigest()
        if cfg.get("token_sha256") and hmac.compare_digest(digest, cfg["token_sha256"]):
            return "extension"
    raise HTTPException(401, "token da extensão inválido")


Auth = Annotated[str, Depends(assistant_auth)]


@router.post("/token")
async def create_token(session: SessionDep, _user: CurrentUser) -> dict[str, str]:
    """Gera o token da extensão (mostrado uma única vez)."""
    token = secrets.token_urlsafe(32)
    cfg = await settings_store.get(session, "extension")
    await settings_store.put(session, "extension", {**cfg, "token_sha256": hashlib.sha256(token.encode()).hexdigest()})
    await audit.record(session, actor="user", action="extension.token")
    await session.commit()
    return {"token": token}


class PageIn(BaseModel):
    url: str
    title: str = ""
    text: str = Field("", max_length=60000)
    has_form: bool = False
    session_job_id: uuid.UUID | None = None  # vaga de onde você veio nesta aba (fluxo de candidatura em várias telas)


@router.post("/page")
async def page(body: PageIn, session: SessionDep, _a: Auth) -> dict[str, Any]:
    """Classifica a página e devolve o cartão da vaga se ela já for conhecida (sem IA)."""
    job = await service.find_job(session, body.url)
    if job is not None:
        card = await service.job_card(session, job)
        card["success_page"] = service.is_success_page(body.url, body.text)
        return card
    if service.is_flow_page(body.url):
        # login/etapas da candidatura: continua na vaga de origem, sem criar vaga nova nem gastar IA
        origin = await session.get(Job, body.session_job_id) if body.session_job_id else None
        if origin is not None and any(u and service.same_site(u, body.url) for u in (origin.canonical_url, origin.apply_url)):
            card = await service.job_card(session, origin)
            card.update(flow_page=True, success_page=service.is_success_page(body.url, body.text))
            return card
        return {"known": False, "looks_like_job": False, "auto_analyze": False, "flow_page": True,
                "success_page": service.is_success_page(body.url, body.text)}  # fmt: skip
    cfg = await settings_store.get(session, "extension")
    is_job = service.looks_like_job(body.url, body.title, body.text)
    return {
        "known": False,
        "looks_like_job": is_job,
        "auto_analyze": bool(
            is_job and cfg.get("auto_analyze_known_ats") and any(h in body.url for h in service.KNOWN_ATS_HOSTS)
        ),
        "success_page": service.is_success_page(body.url, body.text),
    }


@router.post("/analyze")
async def analyze(body: PageIn, session: SessionDep, _a: Auth) -> dict[str, Any]:
    """Analisa a vaga da página (uma chamada de IA, cache de 90 dias) e avalia (Chance × Atratividade)."""
    job = await service.find_job(session, body.url)
    if job is None and service.is_flow_page(body.url):
        raise HTTPException(422, "esta tela é login ou etapa da candidatura, não uma vaga; abra a página da vaga")
    if job is None:
        try:
            res = await get_ai(sessionmaker_from(session)).structured(
                AIRequest(
                    task="job.extract",
                    system=load_prompt("job.extract"),
                    effort="low",
                    max_tokens=4000,
                    cache_ttl_days=90,
                    user=f"<job>\nURL: {service.normalize_url(body.url)}\nTítulo da página: {body.title}\n{body.text[:15000]}\n</job>",
                ),
                JobNormalized,
            )
        except AIError as exc:
            raise HTTPException(503, f"IA indisponível: {exc}") from exc
        x = res.output
        if normalize_title(x.title) in service.NO_TITLE:
            raise HTTPException(422, "não encontrei uma vaga nesta página")
        existing = await service.find_job_same_site(session, body.url, x.title)
        if existing is not None:
            from tracker.modules.scoring.tasks import score_and_route

            await score_and_route(sessionmaker_from(session), str(existing.id))
            return await service.job_card(session, existing)
        source = "linkedin" if service.linkedin_job_id(body.url) else "browser"
        job, _ = await job_service.upsert_job(
            session,
            RawJob(
                source=source,
                external_id=service.external_id_for(body.url),
                title=x.title,
                company_name=x.company_name,
                url=service.normalize_url(body.url),
                location=x.location,
                description_text=body.text[:20000],
                apply_url=body.url,
                apply_kind=x.apply_kind if x.apply_kind != "unknown" else service.guess_apply_kind(body.url, body.text),
            ),
        )
        job_service.apply_extraction(job, x)
        await session.commit()
    from tracker.modules.scoring.tasks import score_and_route

    await score_and_route(sessionmaker_from(session), str(job.id))
    await session.refresh(job)
    return await service.job_card(session, job)


class FieldsIn(BaseModel):
    url: str
    job_id: uuid.UUID | None = None
    fields: list[FormField]
    allow_ai: bool = True
    language: str | None = None


def _transient_job(language: str) -> Job:
    return Job(id=uuid.UUID(int=0), title="", language=language, requirements={}, regime=None, salary=None)


@router.post("/fields")
async def fields(body: FieldsIn, session: SessionDep, _a: Auth) -> dict[str, Any]:
    """Resolve os campos do formulário da página (perfil → banco → regras → IA em lote)."""
    job = await session.get(Job, body.job_id) if body.job_id else await service.find_job(session, body.url)
    cover = None
    if job is not None:
        app = await app_service.get_for_job(session, job.id)
        cover = app.cover_letter if app else (job.extra or {}).get("cover_letter", {}).get("text")
    target = job or _transient_job(body.language or "pt")
    res, ai = await resolve_core(session, body.fields, target, cover, allow_ai=body.allow_ai)
    await session.commit()
    return {
        "values": {r.key: {"value": r.value, "source": r.resolution, "confidence": r.confidence} for r in res.values},
        "suggestions": {
            k: {"value": a.value, "confidence": a.confidence} for k, a in ai.items() if k not in {r.key for r in res.values}
        },
        "sensitive": [f.key for f in res.pending if f.key not in ai],
        "gaps": res.gaps,
        "job_id": str(job.id) if job else None,
    }


class SuggestIn(BaseModel):
    url: str
    job_id: uuid.UUID | None = None
    field: FormField
    allow_ai: bool = False


@router.post("/suggest")
async def suggest(body: SuggestIn, session: SessionDep, _a: Auth) -> dict[str, Any]:
    """Sugestão para um campo clicado. IA só se `allow_ai` (botão "✨ IA" na extensão)."""
    out = await fields(FieldsIn(url=body.url, job_id=body.job_id, fields=[body.field], allow_ai=body.allow_ai), session, _a)
    key = body.field.key
    if key in out["values"]:
        return {"key": key, **out["values"][key], "sensitive": False}
    if key in out["suggestions"]:
        return {"key": key, **out["suggestions"][key], "source": "ai", "sensitive": False}
    return {"key": key, "value": None, "source": None, "sensitive": key in out["sensitive"]}


class LearnItem(BaseModel):
    question: str
    value: Any
    field_kind: str = "text"
    options: list[str] = Field(default_factory=list)
    language: str = "any"


class LearnIn(BaseModel):
    items: list[LearnItem]


@router.post("/learn")
async def learn(body: LearnIn, session: SessionDep, _a: Auth) -> dict[str, int]:
    """Respostas que você digitou viram banco de respostas (a mesma pergunta não gasta IA de novo)."""
    saved = 0
    rows = (await session.scalars(select(AnswerBankEntry))).all()
    by_q = {profile_service.normalize_question(r.canonical_question): r for r in rows}
    for it in body.items:
        if it.value in (None, "", []) or len(it.question) < 3 or it.field_kind == "file":
            continue
        nq = profile_service.normalize_question(it.question)
        entry = by_q.get(nq)
        if entry is None:
            entry = AnswerBankEntry(
                canonical_question=it.question.strip(),
                field_kind=it.field_kind,
                answer={"value": it.value},
                language=it.language,
                source="user",
                sensitive=profile_service.is_sensitive(it.question),
            )
            await profile_service.upsert_answer(session, entry)
            by_q[nq] = entry
        else:
            entry.answer = {**(entry.answer or {}), "value": it.value}
        saved += 1
    await session.commit()
    return {"saved": saved}


class SubmittedIn(BaseModel):
    url: str
    title: str = ""
    text: str = Field("", max_length=60000)
    job_id: uuid.UUID | None = None
    company: str | None = None
    job_title: str | None = None
    answers: list[LearnItem] = Field(default_factory=list)


@router.post("/submitted")
async def submitted(body: SubmittedIn, session: SessionDep, _a: Auth) -> dict[str, Any]:
    """Você enviou a candidatura no site: registra no acompanhamento (com o que foi respondido)."""
    job = await session.get(Job, body.job_id) if body.job_id else await service.find_job(session, body.url)
    if job is None and body.job_title:
        job = await service.find_job_same_site(session, body.url, body.job_title)
    if job is None:
        company = body.company or body.title.split(" - ")[-1].split(" | ")[-1].strip() or "Empresa (a confirmar)"
        job, _ = await job_service.upsert_job(
            session,
            RawJob(
                source="browser",
                external_id=service.external_id_for(body.url),
                title=body.job_title or body.title.split(" | ")[0][:200] or "Vaga",
                company_name=company,
                url=service.normalize_url(body.url),
                description_text=body.text[:20000],
                apply_url=body.url,
                apply_kind=service.guess_apply_kind(body.url, body.text),
            ),
        )
        job.language = detect_language(body.text) if body.text else job.language
        await session.flush()
        dispatch("ai.process_job", job_id=str(job.id))
    app = await service.ensure_application(session, job)
    already = app.submitted_at is not None
    if not already:
        await app_service.register_submission(session, app, actor="user", channel="assisted")
        for i, a in enumerate(body.answers):
            if a.value in (None, "", []):
                continue
            session.add(
                ApplicationAnswer(
                    application_id=app.id,
                    step_index=i,
                    question_text=a.question[:500],
                    field_kind=a.field_kind,
                    options=a.options,
                    answer={"value": a.value},
                    resolution="user",
                    confidence=1.0,
                    locked=True,
                )
            )
        await notify(
            session,
            "review_ready",
            {"title": job.title, "message": "Candidatura registrada pelo assistente do navegador", "application_id": str(app.id)},
            telegram_too=False,
        )
    await session.commit()
    if body.answers:
        await learn(LearnIn(items=body.answers), session, _a)
    await events.apublish("applications", "application.updated", {"application_id": str(app.id), "to": app.status})
    return {"application_id": str(app.id), "status": app.status, "already": already, "job_id": str(job.id)}


@router.get("/resume")
async def resume_for_job(session: SessionDep, _a: Auth, job_id: uuid.UUID | None = None) -> Response:
    """PDF para anexar no formulário: o CV da candidatura, senão o melhor coringa aprovado."""
    render: ResumeRender | None = None
    if job_id:
        job = await session.get(Job, job_id)
        if job is not None:
            app = await app_service.get_for_job(session, job.id)
            if app and app.resume_render_id:
                render = await session.get(ResumeRender, app.resume_render_id)
            if render is None:
                sel = await resume_service.select_for_job(session, job)
                if sel["best_variant_id"]:
                    render = await resume_service.latest_render(session, sel["best_variant_id"])
    if render is None:
        v = await session.scalar(
            select(ResumeVariant)
            .where(ResumeVariant.kind == "wildcard", ResumeVariant.status == "approved")
            .order_by(ResumeVariant.updated_at.desc())
            .limit(1)
        )
        render = await resume_service.latest_render(session, v.id) if v else None
    if render is None:
        raise HTTPException(404, "nenhum CV aprovado com PDF: gere em Currículos")
    return Response(
        get_storage().get(render.storage_key),
        media_type="application/pdf",
        headers={
            "content-disposition": f'attachment; filename="{render.filename}"',
            "x-filename": render.filename,
            "access-control-expose-headers": "x-filename",
        },
    )


@router.get("/profile-summary")
async def profile_summary(session: SessionDep, _a: Auth) -> dict[str, Any]:
    _, master = await profile_service.current_master(session)
    return {"name": master.contact.full_name, "email": master.contact.email}
