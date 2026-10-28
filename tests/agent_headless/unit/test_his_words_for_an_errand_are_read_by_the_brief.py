"""Which errand his words are for is the brief's `errand_target`, read asymmetrically (refactor2710-06 T-03).

`cluster_send`, `send_to_worker` and `set_cluster_objective` read no verdict before. Now, through the catalogue's own
arms: the verdict naming the arm's target runs it; a sure contrary verdict (≥ VETO) drops it; an unsure one asks which;
and no verdict — an old brief, nothing running — keeps today's route, never a new question.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.acts import errand, tools
from nucleo.turn import brief as tb


def _brief(choice: str | None, conf: float = 0.95) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-et", "open_ids": [],
            "result": ({errand.TARGET_KEY: {"choice": choice, "confidence": conf}} if choice else {})}


@pytest.fixture
def arm(monkeypatch):
    ran = []
    calls = SimpleNamespace(
        _t_cluster_send=lambda **k: ran.append("cluster_send"),
        _t_send_to_worker=lambda **k: ran.append("send_to_worker"),
        _t_set_cluster_objective=lambda **k: ran.append("set_cluster_objective"))
    monkeypatch.setattr(tools, "_calls", lambda: calls)

    def call(tool, brief):
        c = SimpleNamespace(_brief=brief, clarify={"msg": ""}, emit=lambda *a, **k: None, _spawn=None,
                            worker_acted={"v": False}, _tool_fired=set(), _say=lambda: SimpleNamespace(
                                ask_which_item_bare="Which one?"))
        tools.CATALOG[tool]({}, c)
        return ran, c.clarify["msg"]
    return call


def test_the_brief_asks_it_while_an_errand_runs():
    keys = {k if isinstance(k, str) else tb._key(*k) for k, _w, _q in tb.QUESTIONS}
    assert errand.TARGET_KEY in keys
    row = next(r for r in tb.QUESTIONS if not isinstance(r[0], str) and tb._key(*r[0]) == errand.TARGET_KEY)
    assert row[1]({"has_workers": True}) and not row[1]({"has_workers": False})
    assert set(row[2]({})["criteria"]) == {"running_errand", "cluster_peer", "cluster_objective", "none"}


def test_an_agreeing_verdict_runs_and_no_verdict_keeps_todays_route(arm):
    ran, ask = arm("send_to_worker", _brief("running_errand"))
    assert ran == ["send_to_worker"] and not ask
    ran, ask = arm("cluster_send", None)
    assert ran[-1] == "cluster_send" and not ask, "no verdict: today's route, never a new question"


def test_a_sure_contrary_verdict_drops_it_and_an_unsure_one_asks(arm):
    ran, ask = arm("cluster_send", _brief("running_errand", 0.9))
    assert "cluster_send" not in ran and not ask
    ran, ask = arm("set_cluster_objective", _brief("none", 0.6))
    assert "set_cluster_objective" not in ran and ask == "Which one?"
