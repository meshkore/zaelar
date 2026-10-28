"""A round is not measured while the engine is mid-edit.

Measured on 2026-08-20: round 1 ran on a clean `0b89510` and reported 0 self-contradicting prompts;
round 2 booted eleven minutes later with two engine files uncommitted and reported 6 of 10. Both numbers
were about different code and neither could be attributed, so the whole second round was thrown away.
The stamp had recorded `n_dirty: 2` all along — recording a confound does not stop you paying for it.
"""
from tests.use_cases.e2e.agent.run import dirty_tree_refusal


def test_a_dirty_engine_stops_the_round():
    msg = dirty_tree_refusal({"n_dirty": 2, "dirty": ["nucleo/dispatch/__init__.py", "nucleo/workers/brief.py"]})
    assert msg and "nucleo/dispatch/__init__.py" in msg


def test_a_clean_tree_goes_ahead():
    assert dirty_tree_refusal({"sha": "0b89510", "n_dirty": 0, "dirty": []}) == ""


def test_the_fixing_agent_can_measure_their_own_work_on_purpose():
    assert dirty_tree_refusal({"n_dirty": 1, "dirty": ["nucleo/workers/brief.py"]}, allow_dirty=True) == ""


def test_an_empty_stamp_never_costs_a_round():
    """`code_stamp` fails soft; not knowing the sha must not become a refusal to measure."""
    assert dirty_tree_refusal({}) == ""


