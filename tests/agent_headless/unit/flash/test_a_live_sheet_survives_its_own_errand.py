"""A live sheet keeps what its own errand delivered; the reply reads the errand he is looking at (node 2.748).

Audit V2-783 P1-2 (2026-10-16), three holes the sheet gates did not cover:
  · `_a_criteria` emptied the sheet whenever the brief's `goal` changed — and a worker re-words its goal mid-errand,
    so a paraphrase wiped the delivered rows. A NAMED sheet belongs to one errand (`sheet_id_for(task_id)`); only
    the shared sheet, or an explicit `reset`, starts over;
  · `search_listing.fast_pass` on an INHERITED sheet (the same hunt refined) opened it `fresh`, losing its criteria, the
    sentence that opened it and the rows he rejected;
  · the delivery backstop read the rows of the FIRST live task, so with two errands running the reply about one
    carried the other's rows (the judge's «the result is in another card»).
"""
from __future__ import annotations

from widgets.results import data as sheet_mod
from nucleo.acts import search_listing
from nucleo.flash import live_blocks

_SHEET = "results--t-live-1"


def _rows(n):
    return [{"title": f"Monitor {i}", "price": f"{100 + i} €", "url": f"https://x/{i}"} for i in range(n)]


def test_a_reworded_goal_keeps_the_errands_rows():
    sheet_mod.apply_action("criteria", {"sheet": _SHEET, "criteria": {"goal": "Find a used 27-inch monitor"}})
    sheet_mod.apply_action("present", {"sheet": _SHEET, "items": _rows(4)})
    res = sheet_mod.apply_action("criteria", {"sheet": _SHEET, "criteria": {"goal": "Second-hand 27\" monitors under 150"}})
    assert res.get("reset") is False
    assert len(sheet_mod.view_data(_SHEET).get("items") or []) == 4


def test_an_explicit_reset_still_starts_over():
    sheet = _SHEET + "-r"
    sheet_mod.apply_action("criteria", {"sheet": sheet, "criteria": {"goal": "Find a used monitor"}})
    sheet_mod.apply_action("present", {"sheet": sheet, "items": _rows(3)})
    sheet_mod.apply_action("criteria", {"sheet": sheet, "reset": True, "criteria": {"goal": "Find a bike"}})
    assert not (sheet_mod.view_data(sheet).get("items") or [])


def test_an_inherited_sheet_is_not_opened_fresh(monkeypatch):
    import search.listing as LS
    begun = []
    monkeypatch.setattr(LS, "search", lambda q: {"items": [{"title": "LG 27", "url": "https://x/lg", "price": 120,
                                                            "currency": "EUR", "source": "x"}] * 6,
                                                 "sources": [], "needs_browser": False, "reason": ""})
    monkeypatch.setattr(sheet_mod, "begin_task", lambda title="", fresh=True, sheet="": begun.append(fresh) or {"ok": True})
    monkeypatch.setattr(sheet_mod, "rename_task", lambda title="", sheet="": begun.append("renamed") or {"ok": True})
    monkeypatch.setattr(sheet_mod, "apply_action", lambda a, p=None: {"ok": True})
    monkeypatch.setattr(sheet_mod, "prune_sheets", lambda *a, **k: 0)
    from nucleo.workers import ended
    monkeypatch.setattr(ended, "note_listing_delivery", lambda *a, **k: None)
    search_listing.fast_pass("monitor 27", operator_text="un monitor de 27", sheet=_SHEET)
    search_listing.fast_pass("monitor 27", operator_text="un monitor de 27")
    assert begun == ["renamed", True], "an inherited sheet is renamed, never opened fresh"


def test_the_delivery_reads_the_errand_he_is_looking_at(monkeypatch):
    from nucleo import canvas_focus, dispatch
    from nucleo.flash import errand_sheet
    from widgets.navegador import tasks as nav
    monkeypatch.setattr(nav, "active_summaries", lambda: [])
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"request": "a used monitor", "sheet": "results--a"},
        {"request": "a road bike", "sheet": "results--b"}])
    monkeypatch.setattr(errand_sheet, "rows_of_sheet",
                        lambda s, n: ["Monitor LG — 120 €"] if s == "results--a" else ["Bike Orbea — 400 €"])
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "results::results--b")
    assert live_blocks.any_live_task_rows(3) == ("a road bike", ["Bike Orbea — 400 €"])
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "")
    assert live_blocks.any_live_task_rows(3) == ("a used monitor", ["Monitor LG — 120 €"])
