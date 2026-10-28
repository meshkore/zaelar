# Demo pass in a sandbox, 2026-10-28, A2 «ok just put that away for now while you work on it» with the errand's
# sheet as the only card open: canvas=minimize at 0.87, the model called nothing, and the completion found no gesture
# — `sure_canvas` read the canvas verdict at a private floor of 0.9 while every other reader of a SURE verdict uses
# `verdicts.VETO` (0.85). A floor is a rule with readers, stated once (principles: «thresholds are mechanisms, not
# tunings»); a second number for the same question is where a 0.87 falls through.
from __future__ import annotations

import threading

import pytest

from nucleo.flash import card_close as _cc, direct_action as _da
from nucleo.acts import canvas_verdict as _cv   # after direct_action: the two import each other
from nucleo.turn import verdicts as _v


def _brief(canvas: str, conf: float):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["results::723152-ls1"],
            "result": {"canvas": {"choice": canvas, "confidence": conf}, "request_type": {"choice": "order", "confidence": 0.84},
                       "screen_action": {"choice": "none", "confidence": 0.33},
                       "names_a_card": {"choice": "on_screen", "confidence": 0.69}}}


def test_the_canvas_verdict_is_sure_at_the_veto_floor_not_above_it():
    assert _cv.sure_canvas(_brief("minimize", _v.VETO + 0.02)) == "minimize"
    assert _cv.sure_canvas(_brief("minimize", _v.VETO - 0.05)) == ""


@pytest.mark.parametrize("said", ["ok just put that away for now while you work on it", "quítalo de en medio mientras sigues"])
def test_put_that_away_at_0_87_minimises_the_errands_sheet(monkeypatch, said):
    monkeypatch.setattr(_da, "_open_now", lambda: ["results::723152-ls1"])
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["results::723152-ls1"])
    from nucleo import canvas_focus as cf
    cf._reset()
    tags = []
    verb = _cc.run_gesture(_brief("minimize", 0.87), tag_emit=lambda k, x: tags.append((k, x)), emit=lambda *a, **k: None,
                           operator_text=said)
    cf._reset()
    assert verb == "minimize" and tags == [("minimize", {"id": "results::723152-ls1"})], (verb, tags)
