"""An errand shows only its DELIVERABLE; its steps stay off his screen (refactor2710-15, node 2.893).

The operator's feedback (Master row 30e302f2): «how do I write» ran inner steps (read his mails, extract, analyse) and
the only deliverable was a document — yet the results card opened beside it. The licence lived on ONE of the doors a
worker reaches the screen by (`show_widget`); a search filling the errand's sheet (`src="sheet:…"`) went around it.
Now the canvas door asks `circuit.a_step_not_a_show` for every show that comes from an errand: the Request's surface
decides (document → documento · list → results · told → nothing), never the worker's words. A step is told as a `step`
event instead.

Disarm: make `circuit.a_step_not_a_show` return False and the document-errand test goes red.
"""
from __future__ import annotations

import types

import pytest

from nucleo import surfaces


@pytest.fixture
def errand(monkeypatch):
    from nucleo import dispatch as _d
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)          # the arbiter's verdict row
    sessions = {}
    monkeypatch.setattr(_d, "_SESSIONS", sessions)

    def _make(surface, *, tid="t15", sheet="s15"):
        rec = types.SimpleNamespace(task_id=tid, surface=surface, sheet=sheet, done_when=None)
        sessions[tid] = rec
        return rec
    return _make


def _show(wid, src):
    from nucleo.acts import canvas
    rows = []
    shown = canvas.apply("show", wid, src=src, emit=lambda kind, label, **kw: rows.append((kind, label, kw)))
    return shown, rows


def test_a_document_errand_shows_the_document_and_keeps_its_listing_off_screen(errand):
    errand(surfaces.DOC)
    shown, rows = _show("results::s15", "sheet:s15")                        # a search step filled the errand's sheet
    assert shown is False and [k for k, *_ in rows] == ["step"], rows
    assert rows[0][2]["extra"]["deliverable"] == "documento"
    shown, rows = _show("results", "worker:t15")                           # the worker asked to show it
    assert shown is False and rows[0][0] == "step"
    shown, rows = _show("documento", "worker:t15")
    assert shown is True and rows[0][:2] == ("widget", "show")


def test_a_list_errand_shows_the_results(errand):
    errand(surfaces.LIST)
    assert _show("results::s15", "sheet:s15")[0] is True
    shown, rows = _show("documento", "worker:t15")
    assert shown is False and rows[0][0] == "step"


def test_a_told_errand_opens_nothing_and_a_turn_is_never_judged_here(errand):
    errand(surfaces.VOICE)
    assert _show("results", "worker:t15")[0] is False
    assert _show("results::other", "sheet:no-errand")[0] is True, "a sheet no errand owns is the turn's own search"
