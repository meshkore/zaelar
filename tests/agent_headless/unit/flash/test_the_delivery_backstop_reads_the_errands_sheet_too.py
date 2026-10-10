"""The delivery backstop reads the errand's own sheet, not only a browser task's (V2-781 T521/T528, 2026-10-10).

Camera pair, EN: the sheet held priced DSLRs for 151 s, the turn prompt carried them under «ENCONTRADO (en su hoja)»
(the TAREAS DE FONDO block reads `dispatch.pending_summaries()` → its `sheet`), and four waiting replies went out
(«Will do.») with the backstop logging `rows: 0`. Its reader looked only at `widgets.navegador.tasks` — the browser
task registry — and this errand had no browser task. Two registries describing one errand, again: the backstop
now falls back to the errand's sheet, the same source the prompt shows.
"""
from __future__ import annotations

from nucleo.flash import live_blocks as LB


def test_an_errand_sheet_without_a_browser_task_is_read(monkeypatch):
    from widgets.navegador import tasks as NT
    from nucleo import dispatch as D
    from nucleo.flash import errand_sheet as ES
    monkeypatch.setattr(NT, "active_summaries", lambda: [])
    monkeypatch.setattr(D, "pending_summaries", lambda: [{"id": "t1", "request": "used DSLR under $400",
                                                          "sheet": "results::ab12"}])
    monkeypatch.setattr(ES, "rows_of_sheet", lambda sheet, n=3: ["«Canon Rebel T7 — $274.99»", "«Nikon D3100 — $219.95»"]
                        if sheet == "results::ab12" else [])
    goal, rows = LB.any_live_task_rows()
    assert goal == "used DSLR under $400" and rows == ["Canon Rebel T7 — $274.99", "Nikon D3100 — $219.95"]


def test_nothing_live_reads_nothing(monkeypatch):
    from widgets.navegador import tasks as NT
    from nucleo import dispatch as D
    monkeypatch.setattr(NT, "active_summaries", lambda: [])
    monkeypatch.setattr(D, "pending_summaries", lambda: [])
    assert LB.any_live_task_rows() == ("", [])
