"""The research criteria go to the errand's OWN sheet, and an errand with no sheet seeds none (2.501).

show-real-photo-of-a-new-car__us (2026-10-11): `seed_criteria` called `results/criteria` with no `sheet`, so the
criteria landed in the BASE `results` box while the errand's sheet was `results::8eeb89-1` — a base card with
nothing of his in it, beside its own instance. A picture errand has no sheet at all: nothing is seeded and the
browser delivery does not open one under it either.
"""
from __future__ import annotations

import asyncio
import types

from nucleo import sheets, surfaces

from nucleo.workers import brief as research

BRIEF = {"goal": "Verified photos of the Ferrari Amalfi", "round": 1}


def _capture(monkeypatch):
    calls = []

    async def _action(wid, action, payload):
        calls.append((wid, action, payload))
        return {"ok": True}
    monkeypatch.setattr("widgets.server_api.brain_action", _action)
    return calls


def test_the_criteria_land_in_the_errands_sheet(monkeypatch):
    calls = _capture(monkeypatch)
    asyncio.run(research.seed_criteria(BRIEF, types.SimpleNamespace(sheet="8eeb89-1")))
    assert calls and calls[0][:2] == ("results", "criteria") and calls[0][2]["sheet"] == "8eeb89-1"


def test_an_errand_with_no_sheet_seeds_nothing(monkeypatch):
    calls = _capture(monkeypatch)
    asyncio.run(research.seed_criteria(BRIEF, types.SimpleNamespace(sheet="")))
    assert calls == [], "no sheet → no criteria in the base box"


def test_a_picture_errand_gets_no_sheet_opened_under_its_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(sheets, "_sheet_open", lambda r, **k: opened.append(r))
    rec = types.SimpleNamespace(status="running", surface=surfaces.IMAGES, nav_task="", task_id="2", sheet="")
    assert sheets.sheet_for_delivery("2", [rec], ("running",)) == "" and opened == []
