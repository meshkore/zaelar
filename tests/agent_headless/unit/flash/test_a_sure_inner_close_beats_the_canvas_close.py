"""«Vale, ya la puedes cerrar» with the appointment's card open closes the CARD'S SHEET, not nothing (V2-781 pair 5).

The brief read canvas=close at 1.00 AND screen_action=agenda:close_meeting at 1.00. «A canvas gesture is never a
data action» skipped the completion, the close backstop found no named card, and the turn said «Vale, la cierro»
over a sheet that stayed open. The earlier misses (R4, M4) had the inner action at 0.55-0.60; an inner op as SURE
as the canvas verdict (≥ 0.95) is the more specific reading and runs — in both channels.
"""
from __future__ import annotations

import pytest

from nucleo.flash import direct_action as DA


@pytest.fixture
def brief(monkeypatch):
    from nucleo.flash import turn_brief as _tb
    st = {"conf": 1.0, "ran": []}
    monkeypatch.setattr(DA, "sure_canvas", lambda b: "close")
    monkeypatch.setattr(DA, "from_brief", lambda b: ("agenda", "close_meeting"))
    monkeypatch.setattr(DA, "_action_sure", lambda b, floor=0.8: st["conf"] >= floor)
    monkeypatch.setattr(DA, "resolve", lambda *a, **k: {"widget": "agenda", "action": "close_meeting",
                                                         "payload": {}, "label": "agenda:close_meeting",
                                                         "source": "verdict"})
    monkeypatch.setattr(_tb, "read", lambda b, key, d="", **k: ("order", {"confidence": 1.0}))
    return st


def _complete(st):
    return DA.complete(object(), operator_text="Vale, ya la puedes cerrar", emit=lambda *a, **k: None,
                       present=lambda *a, **k: None,
                       apply_widget_data=lambda w, a, p: st["ran"].append((w, a)))


def test_a_sure_inner_close_runs(brief):
    assert _complete(brief) == "close_meeting" and brief["ran"] == [("agenda", "close_meeting")]


def test_an_unsure_inner_op_leaves_the_canvas_close_alone(brief):
    brief["conf"] = 0.6                                    # the R4 / M4 shape
    assert _complete(brief) == "" and brief["ran"] == []


def test_the_text_channel_asks_the_same_rule():
    assert "canvas_yields(_tbrief)" in open("nucleo/flash/probe_mirrors.py", encoding="utf-8").read()
    assert "canvas_yields(brief)" in open("nucleo/flash/direct_action.py", encoding="utf-8").read()
