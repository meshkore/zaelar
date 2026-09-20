"""Node 3.61 — Jev picks the widget action among DECLARED manifest actions (T-jev-action).

Contract under test (`nucleo/flash/frontend.py`): when the model names an action the manifest
never declared, `resolve_undeclared_action` answers with ONE shared verdict for both channels
(voice rail + probe mirror): a canvas verb keeps its existing boundary mapping, otherwise Jev
chooses among the target widget's DECLARED actions (+ `none`) and the call continues through
the normal mode flow; `none`, unsure, slow, failed, disabled, or an unknown widget keep today's
path (escalate) bit-for-bit. An invented action name can never win — the winner must be a key
of the per-call enumerated criteria.
"""
from __future__ import annotations

import pytest

from nucleo import jev
from nucleo.flash import frontend as _fe


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV_TIMEOUT_MS", "900")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    yield


def _canned(choice="add_to_playlist", confidence=0.9, key="widget_action"):
    return {"model": "jev-latest",
            "answers": {key: {"type": "choice", "choice": choice,
                              "probabilities": {choice: confidence},
                              "confidence": confidence}}}


def test_candidates_are_the_widgets_declared_actions_plus_none(monkeypatch):
    """The candidate set is enumerated per call from the cached catalog — the same source
    `action_mode` reads — so it can never contain an invented action."""
    seen: dict = {}
    monkeypatch.setattr(jev, "_post_question",
                        lambda ak, st, ins, crit, to: (seen.update(
                            answer_key=ak, criteria=crit, state=st), _canned())[1])
    out = _fe.repair_action("musica", "reproducir", "pon esa canción")
    assert out == "add_to_playlist"
    assert seen["answer_key"] == "widget_action"
    assert set(seen["criteria"]) == set(_fe.declared_actions("musica")) | {"none"}
    assert "pon esa canción" in seen["state"]


def test_an_invented_name_from_the_wire_can_never_win(monkeypatch):
    """Even if Jev itself answers an undeclared name, `_parse` constrains it to criteria keys
    and the repair abstains instead of executing something the manifest never declared."""
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned(choice="teleport"))
    assert _fe.repair_action("musica", "reproducir", "pon esa canción") is None


def test_none_and_unsure_keep_todays_path(monkeypatch):
    """`none` or a shrug is an abstention, not a veto: the caller escalates exactly as today."""
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned(choice="none"))
    assert _fe.repair_action("musica", "reproducir", "pon esa canción") is None
    monkeypatch.setattr(jev, "_post_question",
                        lambda *a: _canned(choice="add_to_playlist", confidence=0.2))
    assert _fe.repair_action("musica", "reproducir", "pon esa canción") is None


def test_failed_disabled_and_unknown_never_fire(monkeypatch):
    def _boom(*a):
        raise TimeoutError("slow")
    monkeypatch.setattr(jev, "_post_question", _boom)
    assert _fe.repair_action("musica", "reproducir", "pon esa canción") is None

    calls: list = []
    monkeypatch.setattr(jev, "_post_question", lambda *a: (calls.append(a), _canned())[1])
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert _fe.repair_action("musica", "reproducir", "pon esa canción") is None
    monkeypatch.delenv("ZAELAR_JEV")
    assert _fe.repair_action("no_existe", "reproducir", "pon esa canción") is None
    assert calls == []


def test_canvas_verbs_keep_their_boundary_without_firing(monkeypatch):
    """A smuggled canvas verb maps deterministically WITHOUT consulting Jev — the boundary
    rule predates this task and fires first, so Jev can never shadow it."""
    calls: list = []
    monkeypatch.setattr(jev, "_post_question", lambda *a: (calls.append(a), _canned())[1])
    assert _fe.resolve_undeclared_action("musica", "mostrar", "muéstrame música") == ("canvas", "show")
    assert _fe.resolve_undeclared_action("musica", "cierra", "ciérralo") == ("canvas", "close")
    assert calls == []


def test_repair_and_escalate_verdicts(monkeypatch):
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned(choice="add_to_playlist"))
    assert _fe.resolve_undeclared_action("musica", "reproducir", "pon esa canción") == (
        "repair", "add_to_playlist")
    monkeypatch.setattr(jev, "_post_question",
                        lambda *a: _canned(choice="add_to_playlist", confidence=0.1))
    assert _fe.resolve_undeclared_action("musica", "reproducir", "pon esa canción") == (
        "escalate", None)
    assert _fe.resolve_undeclared_action("no_existe", "reproducir", "pon eso") == (
        "escalate", None)
