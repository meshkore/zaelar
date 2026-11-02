"""What the brain READS of a card, served as it reads it — two read-only routes over one concern.

  · `GET /widgets/{wid}/reading` — `nucleo.flash.widget_read.read`: the card's digest, its coach context and its items,
    the exact text the turn's model reasons over. Anyone checking what the agent could see asks here instead of
    re-reading the card's state with a reader of its own (S1 audit H8: a test harness taught itself five card fields
    and drifted from the engine with every one).
  · `GET /widgets/{wid}/context` — the coach seam (`coach_context()`), the text the assistant injects to adopt a role
    over the widget. Moved here from `server_api.py` with no behaviour change: same concern, and that file sat on the
    800-line ceiling.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/widgets/{wid}/reading")
async def widget_reading(wid: str):
    """The brain's reading of this card; empty when the card publishes nothing."""
    try:
        from nucleo.flash import widget_read
        return JSONResponse({"reading": await asyncio.to_thread(widget_read.read, wid)})
    except Exception as e:  # noqa: BLE001 — a reading nobody could make is empty, never a guess
        return JSONResponse({"reading": "", "error": type(e).__name__})


@router.get("/widgets/{wid}/context")
async def widget_context(wid: str):
    """Coach 'memory seam' — text context the assistant injects to adopt the role over this widget."""
    from widgets import server_api as _api      # the hook runner lives with the other widget routes
    res = await _api._run_widget(wid, "coach_context", lambda fn: fn())
    if res is _api._MISSING or isinstance(res, dict):       # dict = degraded {"error": …} → empty context
        return JSONResponse({"context": ""})
    return JSONResponse({"context": res})
