"""Tabela de preços (US$ por milhão de tokens). Fonte: tabela de modelos, out/2026.

Preços mudam: ajuste aqui. Cache write (TTL 5 min) = 1,25x input; cache read conforme modelo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(4.00, 20.00, 0.20),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.20),
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01),
    "claude-fable-5-1": Price(10.00, 50.00, 0.25),
}
WEB_SEARCH_PER_1K = 10.00
CACHE_WRITE_MULTIPLIER = 1.25


def cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    web_search_requests: int = 0,
) -> float:
    p = PRICES.get(model, PRICES["claude-opus-5-5"])
    total = (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_read_tokens * p.cache_read
        + cache_write_tokens * p.input * CACHE_WRITE_MULTIPLIER
    ) / 1_000_000
    total += web_search_requests * WEB_SEARCH_PER_1K / 1000
    return round(total, 6)
