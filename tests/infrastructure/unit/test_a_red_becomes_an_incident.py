"""V2-780 — tests diagnose, a developer fixes: every red is written as ONE task in ONE initiative.

Operator, 2026-10-02: «los tests están ahí para diagnosticar y evaluar» — mark it, keep the incident, and a
developer drains them one by one. These pin the inbox's contract: one task per key, a repeat appends instead
of duplicating, a red after `done` is a NEW task (a regression), and the sweep files without ever fixing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from tests import incidents  # noqa: E402
from tests import watchdog as W  # noqa: E402


@pytest.fixture(autouse=True)
def inbox(tmp_path, monkeypatch):
    modules = tmp_path / "modules"
    monkeypatch.setattr(incidents, "MODULES", modules)
    monkeypatch.setattr(incidents, "TASKS", modules / "tester" / "tasks")
    (modules / "nucleo" / "tasks").mkdir(parents=True)
    (modules / "nucleo" / "tasks" / "T600-someone-elses.md").write_text("---\nid: T600\n---\n")
    return modules / "tester" / "tasks"


def _file(key="test:tests/x/test_a.py::test_b", symptom="AssertionError: 2 != 3"):
    return incidents.file(key, title="Red: test_b", kind="unknown", symptom=symptom,
                          reproduce="pytest tests/x/test_a.py::test_b", evidence="sweep at abc")


def test_the_first_red_opens_one_task_in_the_inbox_initiative(inbox):
    res = _file()
    assert res["created"] and res["task"].parent == inbox
    text = res["task"].read_text()
    assert res["task"].name.startswith("T601-"), "numbering is GLOBAL across modules"
    for must in ("initiative: V2-780", "status: next", "key: test:tests/x/test_a.py::test_b",
                 "## Symptom", "## Reproduce", "## Evidence", "## Diagnosis", "## Kind", "## Done when"):
        assert must in text, must


def test_the_same_red_again_is_an_occurrence_not_a_duplicate(inbox):
    first = _file()["task"]
    again = _file(symptom="AssertionError: 2 != 4")
    assert not again["created"] and again["task"] == first
    assert len(list(inbox.glob("T*.md"))) == 1
    assert "## Occurrences" in first.read_text() and "2 != 4" in first.read_text()


def test_a_red_after_the_fix_is_a_NEW_regression_task(inbox):
    first = _file()["task"]
    first.write_text(first.read_text().replace("status: next", "status: done"))
    second = _file()
    assert second["created"] and second["task"] != first
    assert "Regression" in second["task"].read_text() and first.name in second["task"].read_text()


def test_the_sweep_files_reds_and_hangs_and_never_touches_anything_else(inbox, tmp_path):
    results = [
        {"target": "tests/x", "verdict": "failed", "failures": [{"node": "tests/x/test_a.py::test_b",
                                                                  "why": "test_a.py:3: AssertionError"}]},
        {"target": "tests/y", "verdict": "hung", "hung_at": "tests/y/test_c.py::test_d", "stack": ["File …"]},
        {"target": "tests/z", "verdict": "ok", "failures": []},
    ]
    filed = W.file_incidents(results, tmp_path / "report.json")
    assert [f["node"] for f in filed] == ["tests/x/test_a.py::test_b", "tests/y/test_c.py::test_d"]
    names = sorted(p.name for p in inbox.glob("T*.md"))
    assert len(names) == 2 and any("hangs" in n for n in names)


def test_the_chunk_names_each_red_test_and_why():
    tail = ["/abs/engine/tests/x/test_a.py:12: AssertionError: 2 != 3",
            "=========================== short test summary info ============================",
            "FAILED tests/x/test_a.py::test_b - AssertionError: 2 != 3",
            "ERROR tests/x/test_e.py",
            "1 failed, 1 error, 4 passed in 0.2s"]
    got = W.Chunk._failures(tail)
    assert [g["node"] for g in got] == ["tests/x/test_a.py::test_b", "tests/x/test_e.py"]
    assert "2 != 3" in got[0]["why"]
