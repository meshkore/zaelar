"""V2-780 — a failing use case lands in the ONE incidents inbox, and only a defect does.

Operator, 2026-10-02: the tests diagnose and evaluate; the incident is kept as a task in one initiative and a
developer fixes them one by one. A BLOCKED case (needs the operator's credentials) is not a defect anybody can
fix, so it stays out of the inbox — the same rule `file_failure` already applies to its own work orders.
"""
from __future__ import annotations

import pytest

from tests import incidents
from tests.use_cases.e2e.agent import initiative as I, scenarios as SC, segments as SG


@pytest.fixture(autouse=True)
def _own_inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(incidents, "MODULES", tmp_path / "inbox")
    monkeypatch.setattr(incidents, "TASKS", tmp_path / "inbox" / "tester" / "tasks")


def _result(sid, overall=2):
    return {"scenario": sid, "tier": 1,
            "run": {"transcript": [], "mechanism_report": {}, "watchdog_log": []},
            "verdict": {"overall": overall, "scores": {}, "veredicto": "prometió y no hizo", "findings": [],
                        "improvements": []}}


def _case(completable: bool):
    for sid, s in SC.registry().items():
        if SG.is_completable(sid) == completable and I.GROUPED.get(sid.split("__")[0]) is None \
                and (completable or SG.segment_of(sid) is not None):
            return s
    raise AssertionError("no such case in the catalog")


def test_a_failing_completable_case_opens_its_incident(monkeypatch, tmp_path):
    monkeypatch.setattr(I, "INITIATIVES", tmp_path / "initiatives")
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    s = _case(True)
    I.file_failure(_result(s.id), scenario=s, sandboxed=True)
    tasks = incidents.find(f"uc:{s.id}")
    assert len(tasks) == 1
    text = tasks[0].read_text()
    assert "initiative: V2-780" in text and "overall 2/5" in text and "prometió y no hizo" in text


def test_the_second_round_is_an_occurrence_of_the_same_incident(monkeypatch, tmp_path):
    monkeypatch.setattr(I, "INITIATIVES", tmp_path / "initiatives")
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    s = _case(True)
    I.file_failure(_result(s.id), scenario=s, sandboxed=True)
    I.file_failure(_result(s.id, overall=1), scenario=s, sandboxed=True)
    tasks = incidents.find(f"uc:{s.id}")
    assert len(tasks) == 1 and "overall 1/5" in tasks[0].read_text()


def test_a_blocked_case_is_not_a_defect_and_stays_out(monkeypatch, tmp_path):
    monkeypatch.setattr(I, "INITIATIVES", tmp_path / "initiatives")
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    s = _case(False)
    I.file_failure(_result(s.id), scenario=s, sandboxed=True)
    assert incidents.find(f"uc:{s.id}") == []
