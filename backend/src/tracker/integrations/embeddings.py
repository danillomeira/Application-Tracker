"""Embeddings locais (ADR-006).

`fastembed` com modelo multilíngue (768 dim). `HashEmbedder` é determinístico e sem
download, usado em testes (EMBEDDINGS_BACKEND=hash) e como fallback.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import os
import re
import threading
import unicodedata
from typing import Protocol

from tracker.core.types import EMBEDDING_DIM

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s+#./-]", " ", text)).strip()


class HashEmbedder:
    """Bag-of-words com hashing + bigramas; normalizado (cosseno ~ sobreposição lexical)."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * EMBEDDING_DIM
            tokens = normalize_text(text).split()
            grams = tokens + [f"{a}_{b}" for a, b in itertools.pairwise(tokens)]
            for tok in grams:
                h = int(hashlib.md5(tok.encode(), usedforsecurity=False).hexdigest(), 16)
                vec[h % EMBEDDING_DIM] += 1.0 if (h >> 8) % 2 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FastEmbedder:
    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(MODEL_NAME)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.embed(texts)]


_lock = threading.Lock()
_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    with _lock:
        if _embedder is None:
            backend = os.environ.get("EMBEDDINGS_BACKEND", "fastembed")
            if backend == "hash":
                _embedder = HashEmbedder()
            else:
                try:
                    _embedder = FastEmbedder()
                except Exception:  # sem rede/modelo: degrada para hash
                    _embedder = HashEmbedder()
        return _embedder


def set_embedder(e: Embedder | None) -> None:
    global _embedder
    _embedder = e


def embed_one(text: str) -> list[float]:
    return get_embedder().embed([text])[0]


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
