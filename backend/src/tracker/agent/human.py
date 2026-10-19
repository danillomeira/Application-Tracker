"""Ritmo humano (docs/09 §2): atrasos log-normais, digitação com atraso, rolagem antes de clicar."""

from __future__ import annotations

import asyncio
import math
import random

from playwright.async_api import Locator


class Pace:
    def __init__(
        self, action_s: tuple[float, float] = (2, 7), typing_ms: tuple[int, int] = (40, 120), scale: float = 1.0
    ) -> None:
        self.action_s = action_s
        self.typing_ms = typing_ms
        self.scale = scale  # testes usam 0

    def _lognormal(self, lo: float, hi: float) -> float:
        mu = math.log(math.sqrt(lo * hi))
        sigma = (math.log(hi) - math.log(lo)) / 4
        return min(hi, max(lo, random.lognormvariate(mu, sigma)))

    async def pause(self, lo: float | None = None, hi: float | None = None) -> None:
        if self.scale <= 0:
            return
        a, b = (lo, hi) if lo is not None and hi is not None else self.action_s
        await asyncio.sleep(self._lognormal(max(a, 0.05), max(b, a + 0.1)) * self.scale)

    async def click(self, loc: Locator) -> None:
        await loc.scroll_into_view_if_needed()
        await self.pause(0.4, 1.2)
        await loc.click()
        await self.pause()

    async def type(self, loc: Locator, text: str) -> None:
        await loc.scroll_into_view_if_needed()
        await loc.fill("")
        if self.scale <= 0:
            await loc.fill(text)
            return
        await loc.press_sequentially(text, delay=random.randint(*self.typing_ms))
