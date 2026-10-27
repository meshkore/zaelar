"""An errand opens only its DELIVERABLE on his screen; the work behind it opens nothing (V2-822).

The operator asked for a document describing how he writes. The worker read his sent mail, extracted, analysed —
and on the way its `show_widget` calls put the results sheet and the messaging card in front of him before the
document. He had asked for the document alone. When he asks for «the three best X», the results sheet with its cards
IS the deliverable, and it opens as before.

Driven through the worker's real door (`/api/worker/act` → `worker_act`, gate and all) with the commission's own
opener, counting every card the errand puts on screen. Disarm: drop the gate call from `worker_act` → the document
errand opens three cards and the list errand two.
"""
from __future__ import annotations

import asyncio
import json
import types

import pytest

from nucleo import docsheet, sheets, worker_api


@pytest.fixture
def shown(monkeypatch):
    from voice import observer
    out: list = []
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, **k: out.append((k.get("extra") or {}).get("id"))
                        if (kind, label) == ("widget", "show") else None)
    monkeypatch.setattr(worker_api, "_piggyback", lambda tid: [])
    return out


def _rec(surface: str):
    return types.SimpleNamespace(task_id="t7", uid="", trace_id="", surface=surface, sheet="", status="running",
                                 title="Tu estilo al escribir", goal="un documento con mi estilo", started=0.0,
                                 kind="generic", phases=[], plan=[], done=0, nav_task="")


def _act(monkeypatch, rec, action: str, payload: dict) -> dict:
    monkeypatch.setattr(worker_api, "_verify", lambda tid, tok: rec)
    res = asyncio.run(worker_api.worker_act(task_id=rec.task_id, token="x", action=action, payload=payload))
    return json.loads(res.body)


def test_a_document_errand_opens_exactly_the_document(shown, monkeypatch):
    rec = _rec("informe")
    docsheet.doc_open(rec)                                              # the commission opens its deliverable
    shows = [_act(monkeypatch, rec, "show_widget", {"id": w}) for w in ("results", "mensajeria")]
    assert shown == ["documento"], f"the errand put {shown} on his screen; only its document may open"
    assert all(r["ok"] is False and "documento" in r["error"] for r in shows), \
        "the worker is told why, and where its result goes"
    assert _act(monkeypatch, rec, "show_widget", {"id": "documento"})["ok"] is True
    assert shown == ["documento", "documento"], "its own deliverable is never refused"


def test_a_list_errand_opens_its_results_sheet(shown, monkeypatch):
    rec = _rec("lista")
    sheets._sheet_open(rec)                                             # «the three best X»: the sheet IS it
    sheet = "results::" + rec.sheet
    assert shown == [sheet], shown
    assert _act(monkeypatch, rec, "show_widget", {"id": "results"})["ok"] is True
    assert _act(monkeypatch, rec, "show_widget", {"id": "mensajeria"})["ok"] is False
    assert shown == [sheet, sheet], f"a list errand opens its sheet and nothing else: {shown}"


def test_an_errand_whose_surface_names_no_card_is_not_this_gates_business(shown, monkeypatch):
    rec = _rec("widget")                                                # it builds/fills a card of his
    assert _act(monkeypatch, rec, "show_widget", {"id": "agenda"})["ok"] is True
    assert shown == ["agenda"]
