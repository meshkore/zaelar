"""An agent that said nothing was not measured, whatever the cause.

Measured 2026-08-21 on `compare-broadband-plans__es`: DeepSeek answered HTTP 402 «Insufficient Balance»
and z.ai had been out of quota since the previous day, so every zaelar turn came back empty. The round
was filed 1/1/1/1/1 FAIL — a permanent red row about a case nobody had exercised, and a product verdict
earned by an unpaid invoice.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import status as S


def _row(mute_n, turns, overall=1, mech=1):
    tr = [{"who": "tester", "text": "x"}, {"who": "zaelar", "text": ""}] * turns
    return {"scenario": "s", "tier": 2,
            "verdict": {"overall": overall, "scores": {"mecanismo": mech}, "veredicto": "no"},
            "run": {"transcript": tr, "mechanism_report": {"mute_turns": {"n": mute_n, "turns": []}}}}


def test_an_all_mute_round_is_INFRA_not_FAIL():
    assert S._state(1, _row(mute_n=4, turns=4)) == "INFRA"


def test_half_mute_is_enough():
    assert S._state(1, _row(mute_n=3, turns=6)) == "INFRA"


def test_ONE_mute_turn_is_still_a_real_round():
    """Sensitivity: a single dropped turn is a hiccup inside a conversation that happened, and grading it
    INFRA would hide real failures behind an infrastructure excuse."""
    assert S._state(1, _row(mute_n=1, turns=8)) != "INFRA"


def test_and_a_talkative_round_is_judged_normally():
    row = _row(mute_n=0, turns=8, overall=5, mech=5)
    assert S._state(5, row) == "PASS"

def test_a_mute_round_on_a_CAPPED_case_is_INFRA_too(monkeypatch):
    """Considered making the cap win here and it is WRONG, so the reasoning stays: a mute round measured
    nothing, and a row that says CAPPED claims the case was exercised as far as it can be. The cap is not
    lost — it comes back with the next round that actually runs. `test_capped_state` holds the same rule
    for a crashed harness, and it got there first."""
    from tests.use_cases.e2e.agent import derived as D
    monkeypatch.setattr(D, "data_scope", lambda _id: ("credentials", ["login"]))
    row = _row(mute_n=4, turns=4)
    row["scenario"] = "restaurant-tonight-madrid"
    assert S._state(1, row) == "INFRA"
