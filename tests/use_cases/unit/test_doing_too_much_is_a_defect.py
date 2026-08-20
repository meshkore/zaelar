"""A case can fail by doing TOO MUCH, and that has to be measurable.

`quick-fact-opening-hours` asks for an opening time and a ticket price. The engine answers it by
spawning a browser Brain Worker — minutes of machinery for a question that the light path answers in
seconds — which is the exact defect the case exists to catch. Until now that bar lived only in prose the
judge read, so whether it counted depended on which judge graded the round (and today the same case was
graded by four different ones). A family that must be ABSENT is as measurable as one that must fire.
"""
from tests.use_cases.e2e.agent import verify


def _events(*families):
    return [{"cat": f, "kind": "x", "label": "y", "ts_ms": 1000 + i} for i, f in enumerate(families)]


def test_a_forbidden_family_that_fired_is_reported():
    rep = verify.mechanism_report(_events("flash", "worker"), [], forbidden_signals=["worker"])
    assert rep["overreach_signals"] == ["worker"]


def test_the_light_path_alone_is_clean():
    rep = verify.mechanism_report(_events("flash", "memory"), [], forbidden_signals=["worker"])
    assert rep["overreach_signals"] == []


def test_the_declaration_travels_into_the_report_even_when_clean():
    """The judge has to be able to tell 'not forbidden' from 'forbidden and absent'."""
    rep = verify.mechanism_report(_events("flash"), [], forbidden_signals=["worker"])
    assert rep["forbidden_signals"] == ["worker"]


def test_expected_and_forbidden_are_independent():
    rep = verify.mechanism_report(_events("flash", "worker"), ["widget"], forbidden_signals=["worker"])
    assert rep["missing_signals"] == ["widget"] and rep["overreach_signals"] == ["worker"]


def test_a_case_that_forbids_nothing_is_unaffected():
    rep = verify.mechanism_report(_events("worker"), ["worker"])
    assert rep["overreach_signals"] == [] and rep["missing_signals"] == []
