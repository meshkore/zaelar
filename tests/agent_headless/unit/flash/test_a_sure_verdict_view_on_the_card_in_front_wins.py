"""A SURE verdict view on the card in front wins over a model view on another card (demo pass 114, I3).

«open the second one» with the F40 photos up: the verdict read `imagenes:select` at 0.97, the model called
`results:detail {index: 2}` on the monitors sheet behind, and «opening the LG 27US500-W» was said over a car. Both
calls are lenses, so nothing irreversible is at stake; at ≥ 0.95 the verdict's own view runs instead. A write on
either side, an unsure verdict or the same card keep CRIT-K2 as it was.
"""
from __future__ import annotations

import pytest

from nucleo.flash import verdict_card as VC


@pytest.fixture
def world(monkeypatch):
    from nucleo.flash import data_ops as _do, direct_action as _da
    st = {"verdict": ("imagenes", "select"), "conf": 0.97, "views": {("imagenes", "select"), ("results", "detail")},
          "completed": []}
    monkeypatch.setattr(_da, "from_brief", lambda _b: st["verdict"])
    monkeypatch.setattr(_da, "_action_sure", lambda _b, floor=0.8: st["conf"] >= floor)
    monkeypatch.setattr(_do, "is_view_op", lambda w, a: (w.split("::")[0], a) in st["views"])

    def complete(_b, *, widget_id="", instead_of="", **_kw):
        st["completed"].append((widget_id, instead_of))
        return st["verdict"][1]
    monkeypatch.setattr(_da, "complete", complete)
    return st


def _run():
    seen = []
    got = VC.takes_the_view(object(), "results::ab12-ls1", "detail", operator_text="open the second one",
                            emit=lambda *a, **k: seen.append(a), present=lambda *a, **k: None,
                            apply_widget_data=lambda *a: None)
    return got, seen


def test_the_card_in_front_takes_the_view(world):
    got, seen = _run()
    assert got == "select" and world["completed"] == [("imagenes", "detail")], world
    assert seen, "the override is on the timeline"


def test_under_the_bar_or_on_the_same_card_the_model_runs(world):
    world["conf"] = 0.9
    assert _run()[0] == "" and not world["completed"]
    world["conf"], world["verdict"] = 0.99, ("results", "layout")
    assert _run()[0] == "" and not world["completed"]


def test_a_write_on_either_side_keeps_the_model(world):
    world["views"] = {("results", "detail")}           # the verdict's action is not a lens
    assert _run()[0] == "" and not world["completed"]
    world["views"] = {("imagenes", "select")}           # the model's call is not a lens
    assert _run()[0] == "" and not world["completed"]


def test_both_channels_ask_the_rule():
    calls = open("nucleo/flash/tool_executor_widget_calls.py", encoding="utf-8").read()
    turn = open("nucleo/flash/widget_data_turn.py", encoding="utf-8").read()
    assert calls.index("_txw._vcard.takes_the_view(") < calls.index("_txw._direct_action.completes(_brief, _cd["), \
        "before the same-card disagreement rule"
    assert "_vcard.retarget(" in turn and "_other_view(" in open("nucleo/flash/verdict_card.py").read()
