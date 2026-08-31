"""V2-292 — a WRITTEN and never-opened box is not seen by the operator, and until today this report did not see it either.

`sheet_instances` counted only the `show`s, and that was the whole question until it stopped being so. Measured in the batch
from 2026-08-24 13:11, `search-buy-guitar__es`: THREE boxes for that case remained on disk —19, 45, and 12 rows, the
last two titled with phrases from the CONVERSATION («Ah, bien. ¿Y sabes si están cerca…», «Sí, porfa. Yo estoy
en Madrid…»)— and only the first had `show`. The report said **«18 candidatos»** out of **76 that existed**.

These are TWO distinct facts, and what matters is the GAP between them:

  · OPEN  → the operator has it in front of them.
  · WRITTEN  → its rows exist and belong to this task.

Adding them without saying anything would turn the defect into a higher number, which is how it gets hidden. That is why the
sheet reader reads ALL the written ones —«entregó 18» and «entregó 76 repartidas en tres cajas, dos invisibles»
are two different verdicts about the same case— and the judge receives the NAMED gap, with the warning that it
belongs to the MECHANISM: if zaelar named a candidate that is in an invisible box, it had it and said so correctly.
"""
from tests.use_cases.e2e.agent import judge, verify


def _ev(label, wid, src="worker:1"):
    return {"cat": "widget", "label": label, "id": wid, "src": src}


def test_a_box_written_without_being_shown_is_reported_apart():
    """THE MEASURED CASE: three written boxes, only one open."""
    out = verify.sheet_instances([
        _ev("show", "results::a-1"), _ev("data", "results::a-1"),
        _ev("data", "results::a-4"), _ev("data", "results::a-6"),
    ])
    assert out["ids"] == ["results::a-1"]                       # the OPEN one does not change
    assert out["n_unseen"] == 2
    assert out["unseen_ids"] == ["results::a-4", "results::a-6"]
    assert out["written_ids"] == ["results::a-1", "results::a-4", "results::a-6"]


def test_the_two_facts_do_not_get_mixed():
    """`n_sheets` continues to count OPEN BOXES. Inflating it with the invisible ones would erase the question it answers."""
    out = verify.sheet_instances([_ev("show", "results::a-1"), _ev("data", "results::a-4")])
    assert out["n_sheets"] == 1
    assert out["n_unseen"] == 1


def test_a_box_both_written_and_shown_is_not_invisible():
    """The converse, without which «hay cajas invisibles» would hold for any writing."""
    out = verify.sheet_instances([_ev("show", "results::a-1"), _ev("data", "results::a-1")])
    assert out["n_unseen"] == 0
    assert out["unseen_ids"] == []


def test_a_clean_round_says_nothing_about_invisible_boxes():
    """A warning that always appears stops being a warning."""
    mech = {"sheet_instances": verify.sheet_instances([_ev("show", "results::a-1"), _ev("data", "results::a-1")])}
    assert "NADIE LAS ABRIÓ" not in judge.mechanism_facts(mech)


def test_the_judge_is_told_and_told_whose_fault_it_is():
    """The gap is NAMED, with its ids, and is identified as belonging to the MECHANISM: without that half, the judge points to zaelar's
    answers for rows that it did have (the `the instrument accuses the product` family)."""
    mech = {"sheet_instances": verify.sheet_instances([
        _ev("show", "results::a-1"), _ev("data", "results::a-4"), _ev("data", "results::a-6")])}
    txt = judge.mechanism_facts(mech)
    assert "NADIE LAS ABRIÓ" in txt
    assert "results::a-4" in txt and "results::a-6" in txt
    assert "MECANISMO" in txt
    assert "los tenía y los dijo bien" in txt
