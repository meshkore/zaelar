"""Two rounds are only a pair if both halves ran the same commit.

Rounds are run in twos on purpose: this case produced the same grade three times with three different
mechanisms underneath, so one round proves nothing. But on 2026-08-20 a shell loop launched a pair across
a commit boundary — the fixing agent committed between them, correctly — and the two halves measured
different code. The clean-tree guard cannot see this: the tree is clean on both sides of a commit.
"""
from tests.use_cases.e2e.agent.run import tree_moved_refusal


def test_the_same_head_is_a_pair():
    assert tree_moved_refusal({"sha": "6966dd3"}, "6966dd3") == ""


def test_a_commit_between_rounds_stops_the_batch():
    msg = tree_moved_refusal({"sha": "6966dd3"}, "39e4b1a")
    assert "6966dd3" in msg and "39e4b1a" in msg


def test_not_knowing_the_sha_never_costs_a_round():
    """`code_stamp` fails soft to an empty sha; that must not become a refusal to measure."""
    assert tree_moved_refusal({"sha": ""}, "39e4b1a") == ""
    assert tree_moved_refusal({"sha": "6966dd3"}, "") == ""
    assert tree_moved_refusal({}, "39e4b1a") == ""
