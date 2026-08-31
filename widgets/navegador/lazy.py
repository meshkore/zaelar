"""widgets/navegador/lazy.py — materialise what a page renders WHEN APPROACHED (V2-323).

A VIRTUALIZED listing does not create its cards until you approach them, so “zero rows extracted” and “the
page has no results” are two different things that read the same. Measured on 2026-08-25 against the exact URL
that a worker had just navigated to (`autoscout24.es/lst/cit_madrid/ft_diesel?…`):

    without scrolling: 0 listing anchors in the DOM · 1 row (furniture)
    after scrolling  : 40 anchors                  · 19 rows

HTTP 200, correct title, and the page's own text said “16,752 used diesel cars”. The run
(`search-buy-used-car__es`, 19:11) reported an empty sheet after four minutes of real navigation.

OWN MODULE rather than another method on `owner.TaskBrowser` because the architectural ratchet called for it as
that file grew — and it was right beneath the line count: this is page mechanics, not tab state. It receives
the page and knows nothing about tasks, sheets, or workers.
"""
from __future__ import annotations

import asyncio
import os

#: How much taller than the screen a page must be before we believe it hides rows below the fold.
#: Measured: autoscout24 WITH results 11.5× · a genuinely empty search (wallapop) 0.2×. The 2 is far from
#: both, and is what makes this mechanism RESPECT the cost argument from V2-294 instead of overriding it: a
#: results page with nothing on it does not even reach one screen, so it never pays for this.
FOLD_RATIO = float(os.environ.get("ZAELAR_NAV_FOLD_RATIO", "2") or 2)
FOLD_STEPS = int(os.environ.get("ZAELAR_NAV_FOLD_STEPS", "4") or 4)
_STEP_WAIT_S = 0.7
_SETTLE_S = 1.2


async def materialise_below_the_fold(page) -> bool:
    """Scroll through the page to force lazy rows to appear, and RETURN THE VIEW to its place.

    `True` = it pushed (there was content below the fold). `False` = there was nothing to materialise, and the
    caller must read it as “this page is genuinely empty”, not as a failure.

    Returning the view is not cleanup: the worker's next `click_at` carries coordinates from a screenshot
    taken BEFORE this, and a tool that moves the page underneath would break clicking to fix the
    extraction. Verified live: the materialised cards SURVIVE the return to the top.

    The page is used directly rather than `agent_act("scroll")` because the latter captures one screenshot per
    step: four pushes would cost four PNGs and four milestones for a movement nobody asked to see.

    Fail-soft like the entire module: if something breaks, it returns `False` and extraction continues on its way.
    """
    try:
        alto, viewport, y0 = await page.evaluate(
            "() => [document.body.scrollHeight, window.innerHeight, window.scrollY]")
        if not viewport or viewport <= 0 or alto <= viewport * FOLD_RATIO:
            return False
        for _ in range(FOLD_STEPS):
            await page.mouse.wheel(0, viewport)
            await asyncio.sleep(_STEP_WAIT_S)
        await asyncio.sleep(_SETTLE_S)
        await page.evaluate("y => window.scrollTo(0, y)", float(y0 or 0))
        await asyncio.sleep(0.2)
        return True
    except Exception:  # noqa: BLE001
        return False
