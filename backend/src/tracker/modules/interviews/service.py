"""Dossiê de entrevista, página de cola e simulação (RF-ENT-01..06)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core.config import get_settings
from tracker.integrations.claude.client import WEB_SEARCH_TOOL, AIRequest, get_ai, load_prompt
from tracker.modules.applications.models import Application, ApplicationAnswer
from tracker.modules.calendar.models import CalendarEvent
from tracker.modules.companies.models import Company, CompanyProfile
from tracker.modules.companies.tasks import get_or_build_profile
from tracker.modules.interviews.models import Interview, InterviewDossier, InterviewQuestionLog, MockSession
from tracker.modules.interviews.schemas import DossierContent, MockTurn
from tracker.modules.jobs.models import Job, JobSnapshot
from tracker.modules.notifications.service import notify
from tracker.modules.profile import service as profile_service
from tracker.modules.profile.models import StarStory
from tracker.modules.resumes.models import ResumeVariant
from tracker.workers.runtime import SM, progress


async def gather_context(s: AsyncSession, app: Application, interview: Interview | None) -> dict[str, Any]:
    job = await s.get(Job, app.job_id)
    assert job is not None
    company = await s.get(Company, job.company_id)
    assert company is not None
    snap = None
    if app.applied_snapshot_id:
        snap = await s.get(JobSnapshot, app.applied_snapshot_id)
    if snap is None:
        snap = await s.scalar(
            select(JobSnapshot).where(JobSnapshot.job_id == job.id).order_by(JobSnapshot.captured_at.desc()).limit(1)
        )
    variant = await s.get(ResumeVariant, app.resume_variant_id) if app.resume_variant_id else None
    answers = (await s.scalars(select(ApplicationAnswer).where(ApplicationAnswer.application_id == app.id))).all()
    stories = (await s.scalars(select(StarStory))).all()
    prof = await s.scalar(
        select(CompanyProfile)
        .where(CompanyProfile.company_id == company.id)
        .order_by(CompanyProfile.collected_at.desc())
        .limit(1)
    )
    past_q = (await s.scalars(select(InterviewQuestionLog).where(InterviewQuestionLog.company_id == company.id).limit(30))).all()
    _, master = await profile_service.current_master(s)
    event = await s.get(CalendarEvent, interview.scheduled_event_id) if interview and interview.scheduled_event_id else None
    return {
        "job": job,
        "company": company,
        "master": master,
        "description": snap.description_text if snap else job.description_text,
        "resume": variant.content if variant else None,
        "answers": [{"q": a.question_text, "a": a.answer} for a in answers],
        "stories": [
            {
                "title": st.title,
                "experience_id": st.experience_id,
                "situation": st.situation,
                "task": st.task,
                "action": st.action,
                "result": st.result,
                "competencies": st.competencies,
            }
            for st in stories
        ],
        "company_profile": prof.content if prof else None,
        "past_questions": [{"kind": q.interview_kind, "q": q.question} for q in past_q],
        "event": event,
    }


def _context_block(ctx: dict[str, Any], interview: Interview | None) -> tuple[str, str]:
    job, company, master = ctx["job"], ctx["company"], ctx["master"]
    stable = (
        "<profile>\n" + master.model_dump_json(exclude_none=True) + "\n</profile>\n"
        "<star_stories>\n" + json.dumps(ctx["stories"], ensure_ascii=False) + "\n</star_stories>"
    )
    ev = ctx["event"]
    when = ev.starts_at.isoformat() if ev else (interview.starts_at.isoformat() if interview and interview.starts_at else None)
    variable = (
        f"<job>\nEmpresa: {company.name}\nVaga: {job.title}\nRequisitos: {json.dumps(job.requirements, ensure_ascii=False)}\n"
        f"Descrição (como estava na candidatura):\n{ctx['description'][:12000]}\n</job>\n"
        f"<resume_sent>{json.dumps(ctx['resume'], ensure_ascii=False) if ctx['resume'] else 'n/d'}</resume_sent>\n"
        f"<answers_sent>{json.dumps(ctx['answers'], ensure_ascii=False)}</answers_sent>\n"
        f"<company_profile>{json.dumps(ctx['company_profile'], ensure_ascii=False) if ctx['company_profile'] else 'n/d'}</company_profile>\n"
        f"<past_interview_questions>{json.dumps(ctx['past_questions'], ensure_ascii=False)}</past_interview_questions>\n"
        f"Entrevista: etapa={interview.kind if interview else 'n/d'}, quando={when}, "
        f"link={ev.location_or_link if ev else ''}, entrevistadores={json.dumps(interview.interviewers if interview else [], ensure_ascii=False)}"
    )
    return stable, variable


def validate_dossier(content: DossierContent, master_ids: set[str], found_urls: set[str]) -> DossierContent:
    """Remove afirmações sem fonte e matches que não apontam para experiências reais."""
    valid = found_urls | {s.url for s in content.sources}

    def ok(urls: list[str]) -> bool:
        return bool(urls) and (any(u in valid for u in urls) if valid else True)

    content.company.history = [c for c in content.company.history if ok(c.source_urls)]
    content.company.news = [c for c in content.company.news if ok(c.source_urls)]
    content.values = [v for v in content.values if ok(v.source_urls)]
    content.match = [m for m in content.match if m.experience_id in master_ids]
    return content


def cheatsheet(content: DossierContent, company: str, title: str) -> str:
    c = content
    lines = [f"# {company} · {title}", ""]
    if c.logistics.when or c.logistics.link:
        lines += [f"**Quando:** {c.logistics.when or '—'} · **Link:** {c.logistics.link or '—'}", ""]
    lines += ["## Em uma frase", c.company.overview, ""]
    if c.mission:
        lines += [f"**Missão:** {c.mission}", ""]
    lines += ["## Valores → minha história"] + [f"- **{v.value}:** {v.how_to_connect}" for v in c.values[:5]] + [""]
    lines += ["## Meus pontos de match"] + [f"- **{m.requirement}:** {m.what_to_say}" for m in c.match[:6]] + [""]
    if c.gaps:
        lines += ["## Gaps (com honestidade)"] + [f"- {g.requirement}: {g.honest_approach}" for g in c.gaps[:3]] + [""]
    lines += ["## Perguntas prováveis"] + [f"- {q.question}" for q in c.likely_questions[:8]] + [""]
    lines += ["## Minhas perguntas"] + [f"- {q}" for q in c.questions_to_ask[:5]] + [""]
    if c.points_to_defend:
        lines += ["## Esteja pronto para defender"] + [f"- {p}" for p in c.points_to_defend] + [""]
    if c.company.news:
        lines += ["## Notícias recentes"] + [f"- {n.text}" for n in c.company.news[:3]]
    return "\n".join(lines)


async def build_dossier(sm: SM, application_id: str, interview_id: str | None = None, task_run_id: str | None = None) -> str:
    async with sm() as s:
        app = await s.get(Application, uuid.UUID(application_id))
        assert app is not None
        job = await s.get(Job, app.job_id)
        assert job is not None
        company_id = str(job.company_id)
        dossier = InterviewDossier(
            application_id=app.id, interview_id=uuid.UUID(interview_id) if interview_id else None, status="running"
        )
        s.add(dossier)
        await s.commit()
        dossier_id = dossier.id
    await progress(sm, task_run_id, 10, "pesquisando a empresa")
    try:
        await get_or_build_profile(sm, company_id)
    except Exception:  # noqa: S110 (dossiê segue com o que houver)
        pass
    async with sm() as s:
        app = await s.get(Application, uuid.UUID(application_id))
        assert app is not None
        interview = await s.get(Interview, uuid.UUID(interview_id)) if interview_id else None
        ctx = await gather_context(s, app, interview)
        stable, variable = _context_block(ctx, interview)
        master_ids = {e.id for e in ctx["master"].experience} | {p.id for p in ctx["master"].projects}
        company_name, job_title = ctx["company"].name, ctx["job"].title
    await progress(sm, task_run_id, 40, "montando o dossiê")
    res = await get_ai(sm).structured(
        AIRequest(
            task="interview.dossier",
            system=load_prompt("interview.dossier"),
            context=stable,
            user=variable + "\n\nMonte o dossiê completo.",
            effort="high",
            max_tokens=16000,
            tools=[{**WEB_SEARCH_TOOL, "max_uses": 5}],
            entity_type="application",
            entity_id=uuid.UUID(application_id),
        ),
        DossierContent,
    )
    content = validate_dossier(res.output, master_ids, {x["url"] for x in res.sources})
    async with sm() as s:
        d = await s.get(InterviewDossier, dossier_id)
        assert d is not None
        d.content = content.model_dump(mode="json")
        d.sources = [x.model_dump() for x in content.sources] + res.sources
        d.cheatsheet_md = cheatsheet(content, company_name, job_title)
        d.model, d.prompt_version, d.status = res.model, "v1", "ready"
        d.generated_at = datetime.now(UTC)
        await notify(
            s,
            "dossier_ready",
            {
                "company": company_name,
                "title": job_title,
                "url": f"{get_settings().app_base_url}/entrevistas/{interview_id or ''}",
                "application_id": application_id,
            },
        )
        await s.commit()
    return str(dossier_id)


async def mock_turn(s: AsyncSession, sm: SM, session: MockSession, answer: str | None) -> MockTurn:
    app = await s.get(Application, session.application_id)
    assert app is not None
    ctx = await gather_context(s, app, None)
    stable, variable = _context_block(ctx, None)
    history = "\n".join(
        f"{'Entrevistador' if t['role'] == 'interviewer' else 'Candidato'}: {t['text']}" for t in session.transcript
    )
    user = (
        f"{variable}\n\nEtapa simulada: {session.interview_kind}.\n<transcript>\n{history}\n</transcript>\n"
        + (f"Última resposta do candidato:\n{answer}\n" if answer else "Comece a entrevista com a primeira pergunta.\n")
        + f"Perguntas feitas até agora: {sum(1 for t in session.transcript if t['role'] == 'interviewer')}."
    )
    res = await get_ai(sm).structured(
        AIRequest(
            task="interview.mock",
            system=load_prompt("interview.mock"),
            context=stable,
            user=user,
            effort="medium",
            max_tokens=4000,
            entity_type="mock_session",
            entity_id=session.id,
        ),
        MockTurn,
    )
    turn = res.output
    transcript = list(session.transcript)
    if answer:
        transcript.append({"role": "candidate", "text": answer, "at": datetime.now(UTC).isoformat()})
    if turn.feedback:
        session.feedback = [*session.feedback, {"question_index": len(session.feedback), **turn.feedback.model_dump()}]
    if turn.next_question and not turn.done:
        transcript.append({"role": "interviewer", "text": turn.next_question, "at": datetime.now(UTC).isoformat()})
    session.transcript = transcript
    if turn.done:
        session.status = "finished"
    return turn
