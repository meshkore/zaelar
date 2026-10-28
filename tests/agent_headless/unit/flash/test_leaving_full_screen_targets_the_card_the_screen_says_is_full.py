# Demo pass in a sandbox, 2026-10-28, V4 «ok that's enough, go back to normal size» over the player at full screen:
#
#     jev turn-brief   canvas=exit_fullscreen (1.00) · screen_action=none (0.69) · names_a_card=nothing
#     ⚡ reply         «Back to normal size now.»          (no call)
#     🤝 promesa cerrada — dice que no lo ha hecho         «I haven't done it — I couldn't carry it out from here.»
#
# The verdict was sure and the completion that exists for exactly this (`card_close.run_gesture`, «the model called
# NOTHING and the brief SURELY names a canvas gesture») found no target: the verdict named no card, his words named
# none, and the fallback is the card his last turn acted on, else the only one open — two cards were open (the
# messages card left from INIT, the player) and the last act was a canvas gesture, not a data-op. The card at full
# screen is a fact the canvas reports (`state.maximized_widget`, V2-609) and two other doors already read it (the
# model's `fullscreen_widget` call, the action map's «unfullscreen»); the verdict completion did not. The rule lived
# on two of three branches.
#
# THE CLASS: a gesture whose target the SCREEN STATE determines resolves from that state — one reader
# (`show_target.at_full_screen`: the canvas report, else the full screen his own order set) for every door.
from __future__ import annotations

import threading

import pytest

from nucleo.flash import card_close as _cc, direct_action as _da, show_target as _st


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria", "youtube"],
            "result": {k: {"choice": v, "confidence": c} for k, (v, c) in verdicts.items()}}


V4 = _brief(canvas=("exit_fullscreen", 1.0), request_type=("order", 0.9), screen_action=("none", 0.69),
            names_a_card=("nothing", 0.67), wants_words=("act", 0.9))


@pytest.fixture
def two_open(monkeypatch):
    monkeypatch.setattr(_da, "_open_now", lambda: ["mensajeria", "youtube"])
    from nucleo import canvas_focus
    canvas_focus._reset()
    yield
    canvas_focus._reset()


def _state(monkeypatch, maximized: str):
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {"open_widgets": ["mensajeria", "youtube"], "maximized_widget": maximized})


@pytest.mark.parametrize("said", ["ok that's enough, go back to normal size", "vale, ya está, vuelve al tamaño normal"])
def test_leaving_full_screen_goes_to_the_card_the_canvas_reports_at_full_screen(two_open, monkeypatch, said):
    _state(monkeypatch, "youtube")
    tags = []
    verb = _cc.run_gesture(V4, tag_emit=lambda k, x: tags.append((k, x)), emit=lambda *a, **k: None, operator_text=said)
    assert verb == "exit_fullscreen"
    assert tags == [("fullscreen", {"id": "youtube", "on": False})]


def test_before_the_report_lands_the_full_screen_his_own_order_set_is_the_target(two_open, monkeypatch):
    _state(monkeypatch, "")
    from nucleo import canvas_focus
    with canvas_focus._lock:                        # what his `fullscreen` tag leaves behind (the event sink's write)
        canvas_focus._state["fs"] = "youtube"
    tags = []
    _cc.run_gesture(V4, tag_emit=lambda k, x: tags.append((k, x)), emit=lambda *a, **k: None,
                    operator_text="go back to normal size")
    assert tags == [("fullscreen", {"id": "youtube", "on": False})]


def test_with_nothing_at_full_screen_the_gesture_has_no_target(two_open, monkeypatch):
    """Toggling «the only card» or the focused one would put it INTO full screen — the opposite of the order."""
    _state(monkeypatch, "")
    tags = []
    assert _cc.run_gesture(V4, tag_emit=lambda k, x: tags.append((k, x)), emit=lambda *a, **k: None,
                           operator_text="go back to normal size") == ""
    assert tags == []


def test_the_one_reader_serves_the_models_call_too(monkeypatch):
    _state(monkeypatch, "youtube")
    assert _st.at_full_screen() == "youtube"
    assert _st.fullscreen_target("", "exit full screen") == "youtube"
