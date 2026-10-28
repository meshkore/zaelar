"""A verdict that CONTRADICTS the model's call needs more certainty than one that completes it (refactor2710-05 T-04,
V2-825 F4 class).

Four branches in `_handle_widget_data_tool`, one per incident and each with its own bar (0.9 for a lens over a state
change, full52 V5; 0.8 for a question over a write, full19 C2 / full51 C2), decided who wins when the verdict names
another action on the same card. Now one rule: `card.vetoes` at `VETO_SURE` (0.85) — the measured incidents read 0.97,
0.91 and 0.86, all above it; under it the model's call runs, logged.
"""
from __future__ import annotations

import inspect

import pytest

from nucleo.acts import card
from tests import widget_data_rig as rig


@pytest.fixture(autouse=True)
def _open(monkeypatch):
    from nucleo.turn import brief as _tb
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)


@pytest.mark.parametrize("wid,model,verdict,label", [
    ("agenda", "add_meeting", "find_free", "❓ la pregunta gana a la escritura — corre el veredicto"),
    ("youtube", "clear_search", "show_tab", "👁 la vista segura gana a un cambio de estado — corre el veredicto"),
])
def test_a_sure_verdict_vetoes_and_an_unsure_one_does_not(wid, model, verdict, label):
    sure = rig.brief(f"{wid}:{verdict}", card.VETO_SURE + 0.01, open_ids=(wid,))
    unsure = rig.brief(f"{wid}:{verdict}", card.VETO_SURE - 0.01, open_ids=(wid,))
    assert card.vetoes(sure, wid, model, verdict) == label
    assert card.vetoes(unsure, wid, model, verdict) == "", "under the veto bar the model's call runs"


def test_a_view_over_a_view_or_a_write_over_an_answer_is_no_veto():
    b = rig.brief("youtube:show_tab", 0.99, open_ids=("youtube",))
    assert card.vetoes(b, "youtube", "show_tab", "show_tab") == ""
    b = rig.brief("agenda:add_meeting", 0.99, open_ids=("agenda",))
    assert card.vetoes(b, "agenda", "find_free", "add_meeting") == "", "a write never vetoes an answer"


def test_the_bar_is_the_disarm(monkeypatch):
    """With the bar dropped to the licence's, the 0.84 verdict would veto — the bar is what the test measures."""
    unsure = rig.brief("agenda:find_free", 0.84, open_ids=("agenda",))
    monkeypatch.setattr(card, "VETO_SURE", 0.5)
    assert card.vetoes(unsure, "agenda", "add_meeting", "find_free")


def test_the_rail_has_one_disagreement_rule():
    from nucleo.flash import tool_executor_widget_calls as calls
    src = inspect.getsource(calls._handle_widget_data_tool)
    i = src.index("_card.vetoes(_brief, _cd[\"card\"], action_name, _dis)")
    veto = src[i:src.index("return", i)]
    assert '_repeat_repair["v"] = (_cd["card"], action_name, _dis)' in veto, "a veto that cannot complete is asked after"
    assert "_action_sure(_brief, floor=" not in src, "no branch keeps its own bar"
    assert src.index("if _looked and _verdict_runs():") < i, "a model that only looked is completed first"
