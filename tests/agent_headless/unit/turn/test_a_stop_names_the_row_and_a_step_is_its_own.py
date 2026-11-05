"""One identity per task (V2-852 T03, invariant I1): a line about a worker's step names the ROW, and the stop of a
step stops the step.

Measured in session c8a307fd: the browser tab driving the car search numbered itself «2» and asked «Task 2 needs your
OK to click «Eliminar Toyota 4Runner»». He answered «yes, close task 2»; the stop verdict read `stop`, the backstop
resolved it against the only live errand, and the whole search row was cancelled while the reply said «I've stopped
task 2 — the Toyota job». Two numberings of one work, and a stop of a step that ended the task.

Now (1) every line a step says is named by its row's title and keyed by its row's uid (`tasks.row_of`), so there is
no second number to say; (2) while a step waits for his OK the stop question offers `decline_step`, and a sure one
answers that step NO and cancels nothing. The variants are another domain (a flat, a booking) and another language.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.request import stop as sd
from nucleo.request import stop_row as sr
from nucleo.turn import brief as _tb


@pytest.fixture
def nav(monkeypatch):
    from widgets.navegador import tasks
    made: list = []

    def tab(goal: str, row_title: str | None, row_id: str = "7"):
        tid = tasks.create(goal, goal[:40])
        made.append(tid)
        rec = None if row_title is None else SimpleNamespace(task_id=row_id, title=row_title, goal=goal)
        from nucleo import dispatch
        monkeypatch.setattr(dispatch, "record_by_nav_task", lambda t, _tid=tid, _rec=rec: _rec if str(t) == _tid else None)
        return tid
    yield tasks, tab
    with tasks._lock:
        for t in made:
            tasks._tasks.pop(t, None)


def _brief(choice: str | None, confidence: float = 0.9):
    ev = threading.Event()
    ev.set()
    result = {_tb.REQUEST_KEY: {"choice": "order", "confidence": 0.9}}
    if choice is not None:
        result[sd.KEY] = {"choice": choice, "confidence": confidence}
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": result}


@pytest.mark.parametrize("goal,row", [("Find a flat to rent in Lisbon under 1200", "Lisbon flat under 1200"),
                                      ("Reserva mesa para cuatro en Sevilla el viernes", "Mesa en Sevilla")])
def test_a_line_about_a_step_carries_the_rows_identity(nav, goal, row):
    from nucleo.circuit import ledger
    tasks, tab = nav
    tid = tab(goal, row)
    who = tasks.row_of(tid)
    assert who["title"] == row, "the step was named by its own registry, not by the task he commissioned"
    assert who["uid"] == ledger.task_uid("7") and who["step"] == tid
    from widgets.navegador import click_reason
    line = click_reason.needs_ok(who["title"], "Remove filter")
    assert row in line and f" {tid} " not in f" {line} ", f"the tab's own number reached the line: {line!r}"


def test_a_tab_he_drives_himself_is_its_own_task(nav):
    tasks, tab = nav
    tid = tab("compare two phone plans", None)
    who = tasks.row_of(tid)
    assert who["uid"] == "" and who["title"] == "compare two phone plans"


def test_the_stop_question_offers_the_step_only_while_one_waits(nav):
    tasks, tab = nav
    assert sr.DECLINE_STEP not in sd.question("", ["the flat search"])["criteria"]
    tid = tab("Find a flat to rent in Lisbon", "Lisbon flat")
    tasks.ask(tid, "I'm about to click «Clear all filters». Shall I go ahead?")
    q = sd.question("«Lisbon flat» needs your OK to click «Clear all filters». Shall I?", ["Lisbon flat"])
    assert sr.DECLINE_STEP in q["criteria"] and "Clear all filters" in q["instructions"]


@pytest.mark.parametrize("said", ["no, close that step", "no, cierra ese paso"])
def test_the_stop_of_a_step_declines_the_step_and_cancels_no_row(nav, monkeypatch, said):
    tasks, tab = nav
    from nucleo import dispatch
    killed: list = []
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: killed.append(w) or ["7"])
    tid = tab("Find a flat to rent in Lisbon", "Lisbon flat")
    tasks.ask(tid, "I'm about to click «Clear all filters». Shall I go ahead?")
    acted: dict = {}
    assert sd.repair(_brief(sr.DECLINE_STEP), said, escalating=False, grammar=lambda: True, acted=acted) == []
    assert killed == [], "the stop of a step cancelled the row"
    assert tasks.take_answer(tid) == "no" and acted.get("declined_step") == tid, "the step was not declined"


def test_a_stop_of_the_task_still_stops_the_row(nav, monkeypatch):
    tasks, tab = nav
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: ["7"])
    tid = tab("Find a flat to rent in Lisbon", "Lisbon flat")
    tasks.ask(tid, "I'm about to click «Clear all filters». Shall I go ahead?")
    assert sd.repair(_brief(sd.STOP), "stop the whole flat search", escalating=False, grammar=lambda: True) == ["7"]
