"""V2-776 L0 · the first circuit cases, written before the circuit exists (the house rule: cases before code).

A circuit case carries a `spec` (the `done_when` grammar), `beats` (recorded model outputs and world states per
beat) and an `expect` on the END STATE and on honesty (`false_done`, `says_missing`), not on the chosen action.
`tests/brain/harness.py` cannot run them yet: it is single-turn, `execute=False`, and judges only the decision.
L5 gives the bank beats and a spec judge; until then these are strict xfails, so the day the runner exists and
one of them passes, this file says so.
"""
import json
import pathlib

import pytest

CASES = pathlib.Path(__file__).resolve().parents[1] / "circuit" / "cases.json"
REQUIRED = {"id", "lang", "phrase", "source", "screen", "spec", "beats", "expect"}


def _cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def test_the_circuit_cases_have_the_shape_l5_will_run():
    cases = _cases()
    assert len(cases) >= 5
    for c in cases:
        assert REQUIRED <= set(c), c.get("id")
        assert isinstance(c["beats"], list) and c["beats"], c["id"]
        assert "end" in c["expect"] and c["expect"]["end"] in ("met", "gave_up", "unverifiable"), c["id"]
        assert c["expect"].get("false_done", 0) == 0, "no circuit case may accept a false «done»"


@pytest.mark.xfail(strict=True, reason="V2-776 L5: the bank has no beats and no spec judge yet")
@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_a_circuit_case_runs_to_its_end_state(case):
    from tests.brain import circuit_runner  # noqa: F401 — does not exist until L5
    raise AssertionError("unreachable")
