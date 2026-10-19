"""Empresas: normalização de nome e get-or-create."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import any_, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.modules.companies.models import Company

_SUFFIXES = r"\b(ltda|ltd|s\.?a\.?|s/a|inc|llc|corp|corporation|gmbh|plc|eireli|me|epp|co)\b\.?"


def normalize_company(name: str) -> str:
    n = unicodedata.normalize("NFKD", name.lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(_SUFFIXES, " ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


async def get_or_create(session: AsyncSession, name: str, *, domain: str | None = None, **fields: object) -> Company:
    norm = normalize_company(name) or name.lower()
    row = await session.scalar(select(Company).where(Company.normalized_name == norm))
    if row is None and domain:
        row = await session.scalar(select(Company).where(literal(domain) == any_(Company.domains)))
    if row is None:
        row = Company(name=name.strip(), normalized_name=norm, domains=[domain] if domain else [])
        for k, v in fields.items():
            if v is not None:
                setattr(row, k, v)
        session.add(row)
        await session.flush()
    elif domain and domain not in (row.domains or []):
        row.domains = [*(row.domains or []), domain]
    return row
