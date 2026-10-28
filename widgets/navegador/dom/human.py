"""Human-like input: a curved mouse path with jitter, clicks on a handle or a point, typing with uneven delays.
Names are read through the package (`_f.<name>`)."""
from __future__ import annotations

import asyncio
import random

from widgets.navegador import dom as _f


async def _human_move(page, tx: float, ty: float, mouse: dict) -> None:
    """Move the mouse from its current position to (tx,ty) along a Bezier curve with jitter and micro-pauses — it looks
    human and costs NO tokens (lives here, not in the model). `mouse` = position dict PER TAB (each task has its
    own mouse; the caller always passes it explicitly)."""
    m = mouse
    sx, sy = m["x"], m["y"]
    steps = random.randint(8, 18)
    cx = (sx + tx) / 2 + random.uniform(-60, 60)       # random control point → curved trajectory
    cy = (sy + ty) / 2 + random.uniform(-40, 40)
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * tx
        y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * ty
        try:
            await page.mouse.move(x, y)
        except Exception:
            break
        await asyncio.sleep(random.uniform(0.006, 0.02))
    m["x"], m["y"] = tx, ty


async def _human_click_handle(page, h, mouse: dict) -> None:
    # V2-247 — scroll-into-view is a COURTESY, not the click: if it fails (covered, collapsed, no layout, detached),
    # `h.click()` still does its own scroll and wait, so a failed courtesy must not kill the action.
    try:
        await h.scroll_into_view_if_needed(timeout=5000)
    except Exception:  # noqa: BLE001
        pass
    try:
        box = await h.bounding_box()
    except Exception:  # noqa: BLE001
        box = None                                     # detached from the DOM: the `click` below says so
    if box:
        tx = box["x"] + box["width"] / 2 + random.uniform(-4, 4)
        ty = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
        await _f._human_move(page, tx, ty, mouse)
        await asyncio.sleep(random.uniform(0.05, 0.18))
        await page.mouse.click(tx, ty, delay=random.randint(40, 110))
    else:
        await h.click(timeout=5000)                    # fallback if there is no box (element without layout)


async def _human_type_handle(page, h, text: str, submit: bool, mouse: dict) -> None:
    await _f._human_click_handle(page, h, mouse)          # focus by clicking, like a human
    try:
        await h.fill("")                               # clear the field before typing
    except Exception:
        pass
    await page.keyboard.type(text, delay=random.randint(40, 120))   # typing with jitter
    if submit:
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await page.keyboard.press("Enter")


async def _human_click_at(page, x: float, y: float, mouse: dict) -> None:
    """Human click at ABSOLUTE viewport coordinates (vision mode: the model sees the screenshot and returns pixels)."""
    m = mouse
    await _f._human_move(page, x + random.uniform(-3, 3), y + random.uniform(-3, 3), m)
    await asyncio.sleep(random.uniform(0.05, 0.18))
    await page.mouse.click(m["x"], m["y"], delay=random.randint(40, 110))
