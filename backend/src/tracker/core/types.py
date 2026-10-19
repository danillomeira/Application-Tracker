"""Tipos de coluna compartilhados."""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY

EMBEDDING_DIM = 768

TextArray = ARRAY(Text)


def EmbeddingColumn() -> Vector:
    return Vector(EMBEDDING_DIM)
