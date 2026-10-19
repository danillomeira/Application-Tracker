"""Validação de uploads: tipos permitidos por magic bytes e limite de tamanho (docs/12 §7)."""

from __future__ import annotations

import hashlib

from fastapi import HTTPException, UploadFile

MAX_BYTES = 10 * 1024 * 1024

MAGIC = {
    "application/pdf": [b"%PDF"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [b"PK\x03\x04"],
    "image/png": [b"\x89PNG"],
    "image/jpeg": [b"\xff\xd8\xff"],
}
TEXT_TYPES = {"application/x-yaml", "text/yaml", "text/plain"}


def detect(data: bytes, filename: str) -> str | None:
    for mime, sigs in MAGIC.items():
        if any(data.startswith(s) for s in sigs):
            if mime.endswith("document") and not filename.lower().endswith(".docx"):
                return None
            return mime
    if filename.lower().endswith((".yaml", ".yml")):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return "application/x-yaml"
    return None


async def read_upload(file: UploadFile, allowed: set[str]) -> tuple[bytes, str, str]:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "arquivo maior que 10 MB")
    mime = detect(data, file.filename or "")
    if mime is None or mime not in allowed:
        raise HTTPException(415, "tipo de arquivo não permitido")
    return data, mime, hashlib.sha256(data).hexdigest()
