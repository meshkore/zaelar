"""V2-359 — a worker's «show results» opens ITS errand sheet, never the bare base card.

The worker-facing verb takes the widget's NAME; the worker never knows its errand instance
(`results::<sheet>`), and `show_widget` passed the bare id through — the frontend then opened the BASE card
ON TOP of the errand's own sheet, empty: the intermittent «TARJETA(S) FANTASMA» the round reports keep naming
(bilbao 08:38 and coche 08:03: base `results` beside its instances) — the live opener V2-351's restore-time
sweep cannot reach. Same decision the voice channel took in 246007a: «my results» resolves to MY sheet.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from nucleo import worker_api


def _shows(monkeypatch):
    got = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit",
                        lambda *a, **k: got.append((a, k.get("extra") or {})), raising=False)
    return got


def test_show_results_resolves_to_the_errand_sheet(monkeypatch):
    got = _shows(monkeypatch)
    rec = SimpleNamespace(task_id="7", trace_id="", sheet="c4e44e-1")
    asyncio.run(worker_api._exec_allow("show_widget", {"id": "results"}, rec))
    ids = [x[1].get("id") for x in got]
    assert ids == ["results::c4e44e-1"], ids


def test_a_worker_with_no_sheet_keeps_the_base(monkeypatch):
    got = _shows(monkeypatch)
    rec = SimpleNamespace(task_id="7", trace_id="", sheet="")
    asyncio.run(worker_api._exec_allow("show_widget", {"id": "results"}, rec))
    assert [x[1].get("id") for x in got] == ["results"]


def test_other_widgets_pass_through_untouched(monkeypatch):
    got = _shows(monkeypatch)
    rec = SimpleNamespace(task_id="7", trace_id="", sheet="c4e44e-1")
    asyncio.run(worker_api._exec_allow("show_widget", {"id": "agenda"}, rec))
    assert [x[1].get("id") for x in got] == ["agenda"]
