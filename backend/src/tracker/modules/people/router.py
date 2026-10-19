"""CRM leve de pessoas e indicações (RF-REL-01..03)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from tracker.api.deps import SessionDep, get_or_404
from tracker.core.security import CurrentUser
from tracker.core.tasks import dispatch
from tracker.modules.applications.models import Application
from tracker.modules.companies.models import Company
from tracker.modules.jobs.models import Job
from tracker.modules.people.models import Person, PersonApplication

router = APIRouter(prefix="/people", tags=["people"])


class PersonIn(BaseModel):
    full_name: str
    company_id: uuid.UUID | None = None
    role: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    kind: str = "recruiter"  # recruiter|hiring_manager|interviewer|connection|referrer
    notes: str | None = None
    referral_status: str | None = None  # none|asked|accepted|declined


class PersonOut(PersonIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    last_contact_at: datetime | None
    company_name: str | None = None
    applications: list[dict] = []


class LinkIn(BaseModel):
    application_id: uuid.UUID
    relation: str = "recruiter"


async def _out(session: SessionDep, p: Person) -> PersonOut:
    o = PersonOut.model_validate(p)
    if p.company_id:
        c = await session.get(Company, p.company_id)
        o.company_name = c.name if c else None
    rows = (
        await session.execute(
            select(PersonApplication, Application, Job)
            .join(Application, Application.id == PersonApplication.application_id)
            .join(Job, Job.id == Application.job_id)
            .where(PersonApplication.person_id == p.id)
        )
    ).all()
    o.applications = [
        {"application_id": str(a.id), "job_title": j.title, "status": a.status, "relation": pa.relation} for pa, a, j in rows
    ]
    return o


@router.get("", response_model=list[PersonOut])
async def list_people(
    session: SessionDep,
    _user: CurrentUser,
    q: str | None = None,
    kind: str | None = None,
    company_id: uuid.UUID | None = None,
) -> list[PersonOut]:
    stmt = select(Person).order_by(Person.last_contact_at.desc().nulls_last(), Person.full_name)
    if q:
        stmt = stmt.where(Person.full_name.ilike(f"%{q}%") | Person.email.ilike(f"%{q}%"))
    if kind:
        stmt = stmt.where(Person.kind == kind)
    if company_id:
        stmt = stmt.where(Person.company_id == company_id)
    return [await _out(session, p) for p in (await session.scalars(stmt.limit(300))).all()]


@router.post("", response_model=PersonOut, status_code=201)
async def create_person(body: PersonIn, session: SessionDep, _user: CurrentUser) -> PersonOut:
    p = Person(**body.model_dump())
    session.add(p)
    await session.commit()
    if p.company_id and p.kind in ("referrer", "connection"):
        for jid in (await session.scalars(select(Job.id).where(Job.company_id == p.company_id, Job.status == "open"))).all():
            dispatch("scoring.score_job", job_id=str(jid))  # conexões mudam a nota de Chance
    return await _out(session, p)


@router.put("/{person_id}", response_model=PersonOut)
async def update_person(person_id: uuid.UUID, body: PersonIn, session: SessionDep, _user: CurrentUser) -> PersonOut:
    p = await get_or_404(session, Person, person_id)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    await session.commit()
    if p.company_id:
        for jid in (await session.scalars(select(Job.id).where(Job.company_id == p.company_id, Job.status == "open"))).all():
            dispatch("scoring.score_job", job_id=str(jid))
    return await _out(session, p)


@router.post("/{person_id}/link", response_model=PersonOut)
async def link(person_id: uuid.UUID, body: LinkIn, session: SessionDep, _user: CurrentUser) -> PersonOut:
    p = await get_or_404(session, Person, person_id)
    await get_or_404(session, Application, body.application_id)
    exists = await session.scalar(
        select(PersonApplication.id).where(
            PersonApplication.person_id == p.id,
            PersonApplication.application_id == body.application_id,
            PersonApplication.relation == body.relation,
        )
    )
    if not exists:
        session.add(PersonApplication(person_id=p.id, application_id=body.application_id, relation=body.relation))
    await session.commit()
    return await _out(session, p)


@router.delete("/{person_id}", status_code=204)
async def delete_person(person_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    """Exclusão sob demanda de dados de terceiros (RNF-36)."""
    await session.delete(await get_or_404(session, Person, person_id))
    await session.commit()
    return Response(status_code=204)
