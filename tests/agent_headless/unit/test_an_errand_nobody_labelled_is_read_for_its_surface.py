"""An errand that arrives with NO declared surface is read for what the operator will look at (demo A1, 2026-09-28).

«Johnny, find me three 27-inch 4K monitors under 400 dollars — show me when you have them.» escalated without a
surface; the kind was `generic`, whose fallback is «voice», so no sheet opened. The operator watched an empty
screen, «Minimise that» had nothing to minimise, and the results turned up minutes later over a playing video.
Jev now reads the request against the same closed vocabulary; unsure or unavailable leaves today's fallback.
"""
import inspect

from nucleo import surfaces


def _jev(monkeypatch, choice, confidence):
    from nucleo import jev
    monkeypatch.setattr(jev, "choose_sync", lambda *a, **k: {"choice": choice, "confidence": confidence})


def test_a_sure_reading_names_the_surface(monkeypatch):
    _jev(monkeypatch, "lista", 0.93)
    s = surfaces.decided("Johnny, find me three 27-inch 4K monitors under 400 dollars — show me when you have them.")
    assert s == surfaces.LIST and surfaces.opens_sheet(s)


def test_an_unsure_reading_leaves_the_fallback(monkeypatch):
    _jev(monkeypatch, "lista", 0.55)
    assert surfaces.decided("do the thing") == ""


def test_jev_down_leaves_the_fallback(monkeypatch):
    from nucleo import jev
    monkeypatch.setattr(jev, "choose_sync", lambda *a, **k: None)
    assert surfaces.decided("find me monitors") == ""


def test_an_answer_outside_the_vocabulary_is_not_a_surface(monkeypatch):
    _jev(monkeypatch, "carousel", 0.99)
    assert surfaces.decided("find me monitors") == ""


def test_the_dispatcher_asks_only_when_nobody_declared_one():
    from nucleo import dispatch
    src = inspect.getsource(dispatch)
    at = src.index("surfaces.decided, request")
    assert src.rindex("if not surfaces.normalize(_declared)", 0, at) > 0, "a declared surface is never re-read"
    assert at < src.index("surfaces.set_once(rec, _declared)"), "read BEFORE the seal, which is once"
