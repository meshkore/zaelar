"""A correction that reaches the errand reaches its SHEET (V2-782 T3.3).

search-buy-used-car ES (2026-10-11): «solo coches completos, nada de maquetas ni recambios» was injected and the worker
answered «lo descarto» — yet the rows stayed on the sheet, and the delivery backstop kept offering them as news. The
injection (`dispatch.inject`) now re-judges the errand's sheet with his words; so does a `criteria` op.
"""
from __future__ import annotations

import asyncio

from widgets.results import data as sheet


def _seed(sid: str) -> None:
    # written before the gate knew the ask: no `asked`, a default title — so nothing was judged at the door
    sheet.store.save(sheet.sheet_key(sid), {"title": "Resultados", "items": [
        {"title": "Maqueta Seat 600 escala", "price": "35 €"}, {"title": "Seat Ibiza 1.4 TDI", "price": "7.750 €"},
        {"title": "Recambios Seat Ibiza", "price": "20 €"}]})


def test_recheck_moves_what_the_correction_rules_out():
    from widgets.results import category_gate
    _seed("t2511a")
    n = category_gate.recheck("t2511a", "solo coches completos de segunda mano, nada de maquetas ni recambios")
    view = sheet.view_data("t2511a")
    assert n == 2 and [i["title"] for i in view["items"]] == ["Seat Ibiza 1.4 TDI"]
    assert {r["title"] for r in view["rejected"]} == {"Maqueta Seat 600 escala", "Recambios Seat Ibiza"}
    sheet.apply_action("append", {"sheet": "t2511a", "items": [{"title": "Maqueta Seat Panda", "price": "12 €"}]})
    assert [i["title"] for i in sheet.view_data("t2511a")["items"]] == ["Seat Ibiza 1.4 TDI"], "the correction stays"


def test_the_injection_itself_rechecks_the_errands_sheet(monkeypatch):
    from nucleo import dispatch
    from nucleo.workers.session import Inject  # noqa: F401 — the queued path appends one

    _seed("t2511b")

    class _Rec:
        session = None
        sheet = "t2511b"
        injects: list = []

    monkeypatch.setitem(dispatch._SESSIONS, "t2511b-task", _Rec())
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda which: ["t2511b-task"])
    done = asyncio.run(dispatch.inject("coche", "nada de maquetas ni recambios, solo coches"))
    assert done == ["t2511b-task"]
    assert [i["title"] for i in sheet.view_data("t2511b")["items"]] == ["Seat Ibiza 1.4 TDI"]


def test_a_criteria_change_rechecks_the_rows_already_there():
    _seed("t2511c")
    sheet.apply_action("criteria", {"sheet": "t2511c", "criteria": {"changes": ["solo coches: nada de maquetas"]}})
    titles = [i["title"] for i in sheet.view_data("t2511c")["items"]]
    assert "Maqueta Seat 600 escala" not in titles and "Seat Ibiza 1.4 TDI" in titles
