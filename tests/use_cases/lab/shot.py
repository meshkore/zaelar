"""A screenshot of a lab agent, as REINFORCEMENT — never as the primary reading.

`screen.py` answers «what opened and what is inside it» from the engine: cheap, headless, and it is
what a round can be judged on. This answers a different question — «does it LOOK right» — and it is the
only thing that can, because a widget can be present in every event and every payload and still paint
nothing. That failure is real and this codebase has paid for it (V2-124: an orb built inside a
reactive branch left a DISCONNECTED canvas, 0 painted pixels of 9216, with no error anywhere and a
green contract test).

So: use it when a claim is VISUAL. Do not use it to find out whether a widget opened — the events
already say that, sooner and without a browser.

⚠️ WHAT A HEADLESS SHOT CANNOT TELL YOU: the LiveKit media path does not come up in this environment
(«could not establish pc connection» — the ICE limitation this repo already documents), so the
connection light and anything downstream of live audio read as broken here and are fine in the
operator's own browser. Judge widgets and layout from a shot; never the voice link.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


async def _grab(url: str, out: Path, *, settle_ms: int, width: int, height: int) -> dict:
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--use-fake-ui-for-media-stream",
                                           "--use-fake-device-for-media-stream"])
        page = await b.new_page(viewport={"width": width, "height": height})
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        # NOT `networkidle`: `/events` is a permanent SSE stream, so idle never arrives and the wait
        # dies on its timeout looking exactly like a page that failed to load.
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(settle_ms)
        facts = await page.evaluate("""() => {
          const box = s => { const e = document.querySelector(s); if (!e) return null;
                             const r = e.getBoundingClientRect();
                             return {w: Math.round(r.width), h: Math.round(r.height)}; };
          const o = document.querySelector('.boot-ovl');
          return {
            // The veil is retired with opacity, NOT display — checking display says "still up" over a
            // page that is perfectly visible. Measured the hard way on 2026-08-21.
            veil: !!o && !o.classList.contains('gone') && parseFloat(getComputedStyle(o).opacity) > 0,
            orb: box('#orb'),
            cards: [...document.querySelectorAll('[data-widget], .wcard, .widget-card')]
                     .map(e => e.getAttribute('data-widget') || e.className).slice(0, 12),
            text: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 400),
          };
        }""")
        out.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out))
        await b.close()
        return {**facts, "errors": errs[:5], "path": str(out)}


def grab(url: str, out: Path, *, settle_ms: int = 20000,
         width: int = 1440, height: int = 900) -> dict:
    return asyncio.run(_grab(url, out, settle_ms=settle_ms, width=width, height=height))
