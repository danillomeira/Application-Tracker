"""Rotas do perfil (docs/06 §Perfil)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from tracker.api.deps import SessionDep, TaskAccepted, get_or_404
from tracker.core import audit
from tracker.core.security import CurrentUser
from tracker.core.storage import get_storage
from tracker.core.tasks import enqueue
from tracker.core.uploads import read_upload
from tracker.integrations.embeddings import embed_one, get_embedder
from tracker.modules.profile import facts, service
from tracker.modules.profile.models import (
    AnswerBankEntry,
    BlocklistEntry,
    Document,
    MasterProfileVersion,
    ProfileImport,
    Reference,
    StarStory,
)
from tracker.modules.profile.schemas import (
    AnswerIn,
    AnswerOut,
    BlockIn,
    BlockOut,
    DiffEntry,
    DocumentOut,
    ImportOut,
    MasterIn,
    MasterOut,
    MasterProfile,
    MasterVersionOut,
    PreferenceData,
    ReferenceIn,
    ReferenceOut,
    StarIn,
    StarOut,
)

router = APIRouter(prefix="/profile", tags=["profile"])
answers_router = APIRouter(prefix="/answer-bank", tags=["profile"])
blocklist_router = APIRouter(prefix="/blocklist", tags=["profile"])
documents_router = APIRouter(prefix="/documents", tags=["profile"])


def _master_out(version: int, master: MasterProfile) -> MasterOut:
    return MasterOut(
        version=version,
        data=master,
        pending_confirmations=master.pending_confirmations(),
        total_years=facts.total_years(master),
    )


@router.get("/master", response_model=MasterOut)
async def get_master(session: SessionDep, _user: CurrentUser) -> MasterOut:
    version, master = await service.current_master(session)
    return _master_out(version, master)


@router.put("/master", response_model=MasterOut)
async def put_master(body: MasterIn, session: SessionDep, _user: CurrentUser) -> MasterOut:
    row = await service.save_master(session, body.data, "manual_edit", body.change_note)
    await session.commit()
    return _master_out(row.version, body.data)


@router.get("/master/versions", response_model=list[MasterVersionOut])
async def list_versions(session: SessionDep, _user: CurrentUser) -> list[MasterProfileVersion]:
    return list((await session.scalars(select(MasterProfileVersion).order_by(MasterProfileVersion.version.desc()))).all())


@router.get("/master/versions/{version}", response_model=MasterOut)
async def get_version(version: int, session: SessionDep, _user: CurrentUser) -> MasterOut:
    row = await session.scalar(select(MasterProfileVersion).where(MasterProfileVersion.version == version))
    if row is None:
        raise HTTPException(404, "versão não encontrada")
    return _master_out(row.version, MasterProfile.model_validate(row.data))


@router.get("/master/diff", response_model=list[DiffEntry])
async def diff_versions(from_: int, to: int, session: SessionDep, _user: CurrentUser) -> list[DiffEntry]:
    rows = {
        r.version: r.data
        for r in (await session.scalars(select(MasterProfileVersion).where(MasterProfileVersion.version.in_([from_, to])))).all()
    }
    if from_ not in rows or to not in rows:
        raise HTTPException(404, "versão não encontrada")
    return service.diff(rows[from_], rows[to])


@router.post("/master/translate", response_model=TaskAccepted, status_code=202)
async def translate(session: SessionDep, _user: CurrentUser, target: str = "pt") -> TaskAccepted:
    if target not in ("pt", "en"):
        raise HTTPException(422, "target deve ser pt ou en")
    tr = await enqueue(session, "ai.profile_translate", target=target)
    return TaskAccepted(task_id=tr.id)


@router.get("/skills/years")
async def skill_years(skill: str, session: SessionDep, _user: CurrentUser) -> dict[str, Any]:
    _, master = await service.current_master(session)
    return {"skill": skill, "canonical": facts.has_skill(master, skill), "years": facts.years_for_skill(master, skill)}


@router.post("/import", response_model=ImportOut, status_code=202)
async def import_file(session: SessionDep, _user: CurrentUser, file: UploadFile = File(...)) -> ImportOut:
    data, mime, sha = await read_upload(
        file,
        {
            "application/pdf",
            "application/x-yaml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    )
    key = get_storage().put(f"imports/{sha}/{file.filename}", data, mime)
    imp = ProfileImport(filename=file.filename or "upload", storage_key=key)
    session.add(imp)
    await session.flush()
    tr = await enqueue(session, "ai.profile_extract", entity_type="profile_import", entity_id=imp.id, import_id=str(imp.id))
    await session.refresh(imp)
    out = ImportOut.model_validate(imp)
    out.task_id = tr.id
    return out


@router.get("/import/{import_id}", response_model=ImportOut)
async def get_import(import_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> ProfileImport:
    return await get_or_404(session, ProfileImport, import_id)


@router.post("/import/{import_id}/confirm", response_model=MasterOut)
async def confirm_import(import_id: uuid.UUID, body: MasterIn, session: SessionDep, _user: CurrentUser) -> MasterOut:
    imp = await get_or_404(session, ProfileImport, import_id)
    if imp.status != "extracted":
        raise HTTPException(409, "importação ainda não extraída")
    row = await service.save_master(session, body.data, "import_pdf", body.change_note or f"importado de {imp.filename}")
    imp.status = "applied"
    created = await service.seed_defaults(session, body.data)
    await session.commit()
    out = _master_out(row.version, body.data)
    out.pending_confirmations.append({"seeded": created})
    return out


@router.get("/preferences", response_model=PreferenceData)
async def get_preferences(session: SessionDep, _user: CurrentUser) -> PreferenceData:
    return await service.get_preferences(session)


@router.put("/preferences", response_model=PreferenceData)
async def put_preferences(body: PreferenceData, session: SessionDep, _user: CurrentUser) -> PreferenceData:
    before = (await service.get_preferences(session)).model_dump()
    out = await service.put_preferences(session, body)
    if body.linkedin_risk_accepted and not before.get("linkedin_risk_accepted"):
        await audit.record(
            session,
            actor="user",
            action="linkedin.risk_accepted",
            reason="aceite explícito do risco de automação no LinkedIn",
        )
    await session.commit()
    return out


# ---------- STAR ----------
@router.get("/star-stories", response_model=list[StarOut])
async def list_star(session: SessionDep, _user: CurrentUser) -> list[StarStory]:
    return list((await session.scalars(select(StarStory).order_by(StarStory.created_at))).all())


def _star_text(s: StarIn) -> str:
    return f"{s.title}. {s.situation} {s.task} {s.action} {s.result} {' '.join(s.competencies + s.skills)}"


@router.post("/star-stories", response_model=StarOut, status_code=201)
async def create_star(body: StarIn, session: SessionDep, _user: CurrentUser) -> StarStory:
    row = StarStory(**body.model_dump(), embedding=embed_one(_star_text(body)))
    session.add(row)
    await session.commit()
    return row


@router.put("/star-stories/{story_id}", response_model=StarOut)
async def update_star(story_id: uuid.UUID, body: StarIn, session: SessionDep, _user: CurrentUser) -> StarStory:
    row = await get_or_404(session, StarStory, story_id)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    row.embedding = embed_one(_star_text(body))
    await session.commit()
    return row


@router.delete("/star-stories/{story_id}", status_code=204)
async def delete_star(story_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    await session.delete(await get_or_404(session, StarStory, story_id))
    await session.commit()
    return Response(status_code=204)


# ---------- Referências ----------
@router.get("/references", response_model=list[ReferenceOut])
async def list_refs(session: SessionDep, _user: CurrentUser) -> list[Reference]:
    return list((await session.scalars(select(Reference).order_by(Reference.name))).all())


@router.post("/references", response_model=ReferenceOut, status_code=201)
async def create_ref(body: ReferenceIn, session: SessionDep, _user: CurrentUser) -> Reference:
    row = Reference(**body.model_dump())
    session.add(row)
    await session.commit()
    return row


@router.delete("/references/{ref_id}", status_code=204)
async def delete_ref(ref_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    await session.delete(await get_or_404(session, Reference, ref_id))
    await session.commit()
    return Response(status_code=204)


# ---------- Banco de respostas ----------
class AnswerSearchHit(AnswerOut):
    score: float


@answers_router.get("", response_model=list[AnswerSearchHit])
async def list_answers(session: SessionDep, _user: CurrentUser, q: str | None = None) -> list[dict[str, Any]]:
    stmt = select(AnswerBankEntry)
    if q:
        emb = get_embedder().embed([q])[0]
        dist = AnswerBankEntry.question_embedding.cosine_distance(emb)
        rows = (await session.execute(stmt.add_columns(dist).order_by(dist).limit(20))).all()
        return [{**AnswerOut.model_validate(r[0]).model_dump(), "score": round(1 - float(r[1]), 3)} for r in rows]
    rows2 = (await session.scalars(stmt.order_by(AnswerBankEntry.use_count.desc(), AnswerBankEntry.canonical_question))).all()
    return [{**AnswerOut.model_validate(r).model_dump(), "score": 1.0} for r in rows2]


@answers_router.post("", response_model=AnswerOut, status_code=201)
async def create_answer(body: AnswerIn, session: SessionDep, _user: CurrentUser) -> AnswerBankEntry:
    data = body.model_dump()
    data["sensitive"] = body.sensitive or service.is_sensitive(body.canonical_question)
    row = await service.upsert_answer(session, AnswerBankEntry(**data, source="user"))
    await session.commit()
    return row


@answers_router.put("/{answer_id}", response_model=AnswerOut)
async def update_answer(answer_id: uuid.UUID, body: AnswerIn, session: SessionDep, _user: CurrentUser) -> AnswerBankEntry:
    row = await get_or_404(session, AnswerBankEntry, answer_id)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    row.sensitive = body.sensitive or service.is_sensitive(body.canonical_question)
    await service.upsert_answer(session, row)
    await session.commit()
    return row


@answers_router.delete("/{answer_id}", status_code=204)
async def delete_answer(answer_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    await session.delete(await get_or_404(session, AnswerBankEntry, answer_id))
    await session.commit()
    return Response(status_code=204)


# ---------- Bloqueios ----------
@blocklist_router.get("", response_model=list[BlockOut])
async def list_blocks(session: SessionDep, _user: CurrentUser) -> list[BlocklistEntry]:
    return list((await session.scalars(select(BlocklistEntry).order_by(BlocklistEntry.kind, BlocklistEntry.value))).all())


@blocklist_router.post("", response_model=BlockOut, status_code=201)
async def create_block(body: BlockIn, session: SessionDep, _user: CurrentUser) -> BlocklistEntry:
    row = BlocklistEntry(**body.model_dump())
    session.add(row)
    await audit.record(session, actor="user", action="blocklist.add", after=body.model_dump())
    await session.commit()
    return row


@blocklist_router.delete("/{block_id}", status_code=204)
async def delete_block(block_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    await session.delete(await get_or_404(session, BlocklistEntry, block_id))
    await session.commit()
    return Response(status_code=204)


# ---------- Documentos ----------
@documents_router.get("", response_model=list[DocumentOut])
async def list_documents(session: SessionDep, _user: CurrentUser) -> list[Document]:
    return list((await session.scalars(select(Document).order_by(Document.created_at.desc()))).all())


@documents_router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    session: SessionDep,
    _user: CurrentUser,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    title: str = Form(...),
    expires_at: datetime | None = Form(None),
) -> Document:
    data, mime, sha = await read_upload(
        file,
        {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    )
    key = get_storage().put(f"documents/{sha}/{file.filename}", data, mime)
    row = Document(kind=kind, title=title, storage_key=key, mime=mime, sha256=sha, expires_at=expires_at)
    session.add(row)
    await session.commit()
    return row


@documents_router.get("/{doc_id}/download")
async def download_document(doc_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    row = await get_or_404(session, Document, doc_id)
    return Response(
        get_storage().get(row.storage_key),
        media_type=row.mime,
        headers={"content-disposition": f'attachment; filename="{row.title}"'},
    )


@documents_router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> Response:
    row = await get_or_404(session, Document, doc_id)
    get_storage().delete(row.storage_key)
    await session.delete(row)
    await session.commit()
    return Response(status_code=204)


class SeedResult(BaseModel):
    version: int
    seeded: dict[str, int]


@router.post("/seed-defaults", response_model=SeedResult)
async def seed_defaults(session: SessionDep, _user: CurrentUser) -> SeedResult:
    version, master = await service.current_master(session)
    created = await service.seed_defaults(session, master)
    await session.commit()
    if not created:
        raise HTTPException(status.HTTP_409_CONFLICT, "nada a criar")
    return SeedResult(version=version, seeded=created)
