"""Tarefas do perfil: extração de CV importado e tradução PT↔EN do mestre."""

from __future__ import annotations

import base64
import io
import re
import uuid
from typing import Any

from tracker.core.storage import get_storage
from tracker.integrations.claude.client import AIRequest, get_ai, load_prompt
from tracker.modules.profile import service
from tracker.modules.profile.ai_schemas import ExtractedProfile, Translation
from tracker.modules.profile.models import ProfileImport
from tracker.modules.profile.schemas import MasterProfile
from tracker.workers.celery_app import celery_app
from tracker.workers.runtime import SM, progress, tracked


def _docx_text(data: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def extracted_to_master(x: ExtractedProfile, current: MasterProfile | None) -> dict[str, Any]:
    """Converte a extração para o formato do mestre, preservando campos do mestre atual."""
    base: dict[str, Any] = current.model_dump(mode="json") if current else {}
    base["contact"] = {**base.get("contact", {}), **x.contact.model_dump(exclude_none=True)}
    if x.headline:
        base.setdefault("headlines", {})["imported"] = x.headline
    from tracker.modules.resumes.content import category_key

    skills: dict[str, list[str]] = {}
    for g in x.skills:  # chaves canônicas: "Data Engineering" → data_engineering (usadas pelos perfis coringa)
        skills.setdefault(category_key(g.category), []).extend(
            i for i in g.items if i not in skills.get(category_key(g.category), [])
        )
    base["skills"] = skills
    base["experience"] = [e.model_dump() for e in x.experience]
    base["projects"] = [p.model_dump() for p in x.projects]
    base["education"] = [e.model_dump() for e in x.education]
    base["certifications"] = [c.model_dump() for c in x.certifications]
    base["languages"] = [lang.model_dump() for lang in x.languages]
    return base


async def _extract(sm: SM, task_run_id: str | None, import_id: str) -> dict[str, Any]:
    async with sm() as s:
        imp = await s.get(ProfileImport, uuid.UUID(import_id))
        assert imp is not None
        key, filename = imp.storage_key, imp.filename
        try:
            _, current = await service.current_master(s)
        except Exception:
            current = None
    data = get_storage().get(key)
    if filename.lower().endswith((".yaml", ".yml")):
        import yaml

        extracted = MasterProfile.model_validate(yaml.safe_load(data)).model_dump(mode="json")
        low: list[str] = []
    else:
        await progress(sm, task_run_id, 20, "lendo o documento com IA")
        if filename.lower().endswith(".pdf"):
            content: list[dict[str, Any]] = [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(data).decode(),
                    },
                },
                {"type": "text", "text": "Extraia o perfil profissional deste documento."},
            ]
        else:
            content = [
                {
                    "type": "text",
                    "text": f"<document>\n{_docx_text(data)}\n</document>\nExtraia o perfil profissional deste documento.",
                }
            ]
        ai = get_ai(sm)
        res = await ai.structured(
            AIRequest(
                task="profile.extract",
                system=load_prompt("profile.extract"),
                user=content,
                effort="high",
                entity_type="profile_import",
                entity_id=uuid.UUID(import_id),
            ),
            ExtractedProfile,
        )
        extracted = extracted_to_master(res.output, current)
        low = res.output.low_confidence
    async with sm() as s:
        imp = await s.get(ProfileImport, uuid.UUID(import_id))
        assert imp is not None
        imp.status = "extracted"
        imp.extracted = {"profile": extracted, "low_confidence": low}
        await s.commit()
    return {"import_id": import_id, "low_confidence": len(low)}


celery_app.task(name="ai.profile_extract")(tracked("ai.profile_extract")(_extract))


async def _translate(sm: SM, task_run_id: str | None, target: str = "pt") -> dict[str, Any]:
    async with sm() as s:
        _, master = await service.current_master(s)
    src_field, dst_field = ("bullets_en", "bullets_pt") if target == "pt" else ("bullets_pt", "bullets_en")
    todo = [e for e in master.experience if getattr(e, src_field) and not getattr(e, dst_field)]
    projects = [p for p in master.projects if target == "pt" and p.description_en and not p.description_pt]
    if not todo and not projects:
        return {"translated": 0}
    payload = (
        "\n\n".join(
            f'<experience id="{e.id}">\n' + "\n".join(f"- {b}" for b in getattr(e, src_field)) + "\n</experience>" for e in todo
        )
        + "\n\n"
        + "\n".join(f'<project id="{p.id}">{p.description_en}</project>' for p in projects)
    )
    lang = "português do Brasil" if target == "pt" else "inglês"
    res = await get_ai(sm).structured(
        AIRequest(
            task="profile.translate",
            system=load_prompt("profile.translate"),
            user=f"Traduza para {lang}, mantendo **negritos**, números e nomes próprios.\n\n{payload}",
            effort="medium",
        ),
        Translation,
    )
    by_id = {t.experience_id: t.bullets for t in res.output.experiences}
    data = master.model_dump(mode="json")
    for e in data["experience"]:
        if e["id"] in by_id:
            e[dst_field] = by_id[e["id"]]
    proj = {t.project_id: t.description for t in res.output.projects}
    for p in data["projects"]:
        if p["id"] in proj:
            p["description_pt"] = proj[p["id"]]
    async with sm() as s:
        await service.save_master(s, data, "translation", f"tradução para {target}")
        await s.commit()
    return {"translated": len(by_id) + len(proj)}


celery_app.task(name="ai.profile_translate")(tracked("ai.profile_translate")(_translate))


def strip_md(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)
