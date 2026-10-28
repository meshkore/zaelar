"""A bank case can seed what the agent already REMEMBERS (`memory.pills`), so a live turn recalls it for real.

A recording that answers «your Tesla insurance renews on March 12, 2027» takes the fact as remembered; run live with no
memory, the real model looked in the agenda, found nothing and said so (refactor2710-99, bank regressions class D).
"""
from __future__ import annotations

import pytest

from tests.brain import harness as H

FACT = "The operator's Tesla insurance renews on March 12, 2027."


def _case(memory: dict | None) -> dict:
    case = {"id": "seed-pills", "lang": "en", "phrase": "When does my Tesla insurance renew?", "source": "test",
            "screen": {"open": []}, "expect": "talk"}
    if memory is not None:
        case["memory"] = memory
    return case


def _recalled(case: dict) -> str:
    with H.Isolated("en") as iso:
        iso.seed(case)
        from nucleo.turn.prompt import recall
        text, _ids = recall.compose_recall(case["phrase"])
        return text


def test_a_seeded_pill_is_recalled_by_the_turn():
    assert FACT in _recalled(_case({"pills": [FACT]}))


def test_the_disarm_without_the_pill_nothing_is_recalled():
    assert FACT not in _recalled(_case(None)), "with no seed the fact is not there — the seed is what the test measures"


@pytest.mark.parametrize("pills", [[""], "one sentence", [3]])
def test_a_malformed_pills_list_is_refused(pills):
    with pytest.raises(ValueError, match="pills"):
        H.validate(_case({"pills": pills}))
