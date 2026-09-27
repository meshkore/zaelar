"""Every case of the decision bank, one test each (V2-776 A1).

A case marked `open` is a defect the bank has NAMED and nobody has fixed yet: it runs as a strict xfail,
so the day the product decides right the test fails until the mark is removed — a known-red that turns
green in silence would be a regression nobody measured (the trinquete's direction, V2-720).

The operator's rule for what goes here: a new failure of the brain is written as a CASE, never as a guard.
"""
from __future__ import annotations

import pytest

from tests.brain import harness

CASES = harness.load_cases()


def _param(case: dict):
    marks = []
    if case.get("open"):
        marks.append(pytest.mark.xfail(strict=True, reason=case["open"]))
    return pytest.param(case, id=case["id"], marks=marks)


@pytest.mark.parametrize("case", [_param(c) for c in CASES])
def test_the_turn_decides_what_the_case_expects(case):
    out = harness.run_case(case)
    why = out.failures(case)
    assert not why, "\n".join([f"[{case['id']}] «{case['phrase']}»", *why,
                               f"raw action={out.action!r} tools={out.tool_calls} tags={out.tags} reply={out.reply[:120]!r}"])


def test_the_bank_has_at_least_thirty_deterministic_cases():
    """A1's first milestone. The count only ratchets up."""
    assert len(CASES) >= 30
    assert {c["lang"] for c in CASES} == {"es", "en"}, "the bank is bilingual by contract"
