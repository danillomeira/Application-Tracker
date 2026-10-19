"""Assistente do navegador (extensão): reconhecer vagas, analisar, preencher e registrar candidaturas.

Princípios: o usuário navega com a própria sessão; a extensão só sugere/preenche; nunca envia formulários.
IA só quando necessário (lote por formulário, cache, análise de vaga sob demanda).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.modules.applications import service as app_service
from tracker.modules.applications.models import Application
from tracker.modules.companies.models import Company
from tracker.modules.jobs.models import Job, JobSource
from tracker.modules.jobs.normalize import detect_apply_kind
from tracker.modules.scoring.models import JobScore
from tracker.modules.scoring.service import company_profile, responsiveness

KNOWN_ATS_HOSTS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "gupy.io",
    "myworkdayjobs.com",
    "smartrecruiters.com",
    "workable.com",
    "inhire",
    "solides",
    "kenoby",
    "recrutei",
    "teamtailor.com",
    "breezy.hr",
    "jobvite.com",
    "icims.com",
    "bamboohr.com",
    "recruitee.com",
    "pandape",
    "vagas.com.br",
    "infojobs.com.br",
    "catho.com.br",
    "remotive.com",
    "remoteok.com",
    "himalayas.app",
    "jobicy.com",
    "arbeitnow.com",
    "weworkremotely.com",
    "workingnomads.com",
    "programathor.com.br",
)
JOB_WORDS = re.compile(
    r"(responsibilities|requirements|qualifications|what you.ll do|about the role|job description|apply now|"
    r"responsabilidades|requisitos|qualifica[cç][oõ]es|atividades|sobre a vaga|candidatar|candidate-se|"
    r"benef[ií]cios|regime de contrata[cç][aã]o|modelo de trabalho)",
    re.I,
)
SUCCESS_WORDS = re.compile(
    r"(application (was )?(sent|submitted|received)|thank(s| you) for (applying|your application)|we.ve received your application|"
    r"candidatura (foi )?(enviada|recebida|realizada|conclu[ií]da)|obrigad[oa] por se candidatar|inscri[cç][aã]o (realizada|conclu[ií]da)|"
    r"recebemos sua candidatura|sua candidatura foi)",
    re.I,
)


# Telas do fluxo de candidatura que NÃO são vagas: login/cadastro e etapas (ex.: Gupy /candidates/applications/.../steps).
FLOW_PAGE = re.compile(
    r"/(candidates?|candidatos?|applications?/\d+/steps)/|"
    r"/(sign[-_]?in|sign[-_]?up|signin|signup|login|logout|auth|oauth2?|register|cadastro|account|minha-conta|"
    r"my-applications|minhas-candidaturas)(/|$|\?)",
    re.I,
)
NO_TITLE = {"", "nao informado", "não informado", "n/a", "vaga", "job", "unknown"}


def is_flow_page(url: str) -> bool:
    u = urlparse(url)
    return bool(FLOW_PAGE.search(u.path + ("?" + u.query if u.query else ""))) or "accounts.google.com" in u.netloc


def same_site(a: str, b: str) -> bool:
    """Mesmo site de carreiras (ex.: stefanini.gupy.io nas duas URLs)."""
    return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()


def normalize_url(url: str) -> str:
    """Remove rastreamento, mantendo o que identifica a vaga (ex.: currentJobId do LinkedIn)."""
    u = urlparse(url)
    keep = {}
    qs = parse_qs(u.query)
    for k in ("currentJobId", "gh_jid", "jobId", "job_id", "id", "lever-origin"):
        if k in qs and k != "lever-origin":
            keep[k] = qs[k][0]
    query = "&".join(f"{k}={v}" for k, v in sorted(keep.items()))
    return urlunparse((u.scheme, u.netloc.lower(), u.path.rstrip("/"), "", query, ""))


def linkedin_job_id(url: str) -> str | None:
    m = re.search(r"linkedin\.com/jobs/view/(\d+)", url) or re.search(r"[?&]currentJobId=(\d+)", url)
    return m.group(1) if m else None


def external_id_for(url: str) -> str:
    return linkedin_job_id(url) or hashlib.sha256(normalize_url(url).encode()).hexdigest()[:24]


def looks_like_job(url: str, title: str, text: str) -> bool:
    if is_flow_page(url):
        return False
    host = urlparse(url).netloc.lower()
    if linkedin_job_id(url) or any(h in host for h in KNOWN_ATS_HOSTS):
        return True
    hits = len(set(m.group(0).lower() for m in JOB_WORDS.finditer(text[:20000])))
    return hits >= 3 or (hits >= 2 and re.search(r"(vaga|job|career|carreira|position)", title + url, re.I) is not None)


def is_success_page(url: str, text: str) -> bool:
    return bool(SUCCESS_WORDS.search(text[:8000])) or bool(
        re.search(r"/(thank[-_]?you|confirmation|obrigado|sucesso)", url, re.I)
    )


async def find_job(session: AsyncSession, url: str) -> Job | None:
    lid = linkedin_job_id(url)
    if lid:
        src = await session.scalar(select(JobSource).where(JobSource.source == "linkedin", JobSource.external_id == lid))
        if src:
            return await session.get(Job, src.job_id)
    norm = normalize_url(url)
    src = await session.scalar(select(JobSource).where(or_(JobSource.url == url, JobSource.url == norm)).limit(1))
    if src:
        return await session.get(Job, src.job_id)
    return await session.scalar(
        select(Job)
        .where(or_(Job.canonical_url == url, Job.canonical_url == norm, Job.apply_url == url, Job.apply_url == norm))
        .limit(1)
    )


async def find_job_same_site(session: AsyncSession, url: str, title: str) -> Job | None:
    """Vaga aberta com o mesmo título no mesmo site de carreiras: evita duplicar quando o nome da empresa varia
    ("Stefanini" x "Stefanini Group") ou a URL é de outra tela do mesmo processo."""
    from tracker.modules.jobs.normalize import normalize_title

    ntitle = normalize_title(title or "")
    host = urlparse(url).netloc.lower()
    if not host or ntitle in NO_TITLE:
        return None
    rows = (await session.scalars(select(Job).where(Job.normalized_title == ntitle, Job.status == "open"))).all()
    return next((j for j in rows if any(u and same_site(u, url) for u in (j.canonical_url, j.apply_url))), None)


async def job_card(session: AsyncSession, job: Job) -> dict[str, Any]:
    company = await session.get(Company, job.company_id)
    score = await session.scalar(select(JobScore).where(JobScore.job_id == job.id, JobScore.is_current.is_(True)))
    app = await app_service.get_for_job(session, job.id)
    prof, _ = await company_profile(session, job.company_id)
    _, resp = await responsiveness(session, job.company_id, prof)
    reputation = None
    if prof is not None:
        reputation = {
            "rating": prof.reputation.rating,
            "rating_source": prof.reputation.rating_source,
            "trend": prof.reputation.rating_trend_12m,
            "positives": prof.culture_positive[:3],
            "alerts": prof.culture_alerts[:3],
            "layoffs": prof.layoffs_12m,
            "ghosting_reports": prof.ghosting_reports,
            "avg_process_days": prof.avg_process_days,
        }
    return {
        "known": True,
        "job_id": str(job.id),
        "title": job.title,
        "company": company.name if company else "",
        "company_id": str(job.company_id),
        "location": job.location,
        "work_model": job.work_model,
        "regime": job.regime,
        "salary": job.salary,
        "requirements": job.requirements,
        "score": {
            "chance": score.chance,
            "attractiveness": score.attractiveness,
            "quadrant": score.quadrant,
            "action": score.suggested_action,
            "reasons": score.explanation.get("chance", {}).get("positives", [])
            + score.explanation.get("attractiveness", {}).get("positives", []),
            "concerns": score.explanation.get("knockout", [])
            + score.explanation.get("chance", {}).get("negatives", [])
            + score.explanation.get("attractiveness", {}).get("negatives", []),
            "missing_must": score.explanation.get("missing_must", []),
        }
        if score
        else None,
        "responsiveness": resp,
        "reputation": reputation,
        "application": {
            "id": str(app.id),
            "status": app.status,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        }
        if app
        else None,
    }


async def ensure_application(session: AsyncSession, job: Job) -> Application:
    app = await app_service.get_for_job(session, job.id)
    if app is None:
        app = await app_service.create_for_job(session, job, channel="assisted", mode="manual", actor="user")
    return app


def guess_apply_kind(url: str, text: str) -> str:
    kind, _ = detect_apply_kind(url, text)
    return kind
