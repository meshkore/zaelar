"""V2-150 (`restaurant-tonight-madrid`) — the task had FINISHED and the turn kept claiming it was ongoing.

The report said `status=done url=` and zaelar said: “the processes are still running — they have been for almost
5 minutes.” This is not the model making things up for no reason: the brain only sees ACTIVE tasks
(`active_summaries`/`active_progress`), so as soon as this one ended it **disappeared from the state**. There was no
fact saying that it had finished, much less that it had finished empty — the one thing that could contradict it had
been removed from view, and the turn filled the gap with what it still had: the worker.

And the same run had DISCOVERED “Casa Lucio only accepts reservations by phone” along with the numbers. The
operator found out in the last turn, when they asked to stop it. The milestone had been in the task from the start;
the brain received a step COUNTER, and a number cannot be spoken aloud.

Same remedy as `silent_s` (V2-131) and the current page (V2-145), one step further: an ENDING is a fact, and a task
that ended without a result is the most useful of the three.
"""
from __future__ import annotations

import pytest

from nucleo.flash import prompt
from widgets.navegador import tasks as nt


def _line(prefix: str) -> str:
    return next((l for l in prompt.live_state().splitlines() if l.startswith(prefix)), "")


@pytest.fixture
def no_live_tasks(monkeypatch):
    monkeypatch.setattr(nt, "active_summaries", lambda limit=3: [])
    monkeypatch.setattr(nt, "active_progress", lambda limit=3: [])


def _finished(**over):
    row = {"id": "t1", "goal": "reservar mesa en Casa Lucio", "status": "done", "url": "",
           "has_results": False, "last_event": "", "ago_s": 30}
    row.update(over)
    return [row]


def test_a_task_that_ended_empty_says_so(no_live_tasks, monkeypatch):
    monkeypatch.setattr(nt, "recently_finished", lambda now=None, limit=3: _finished())
    line = _line("NAVEGADOR — YA TERMINADO")
    assert "terminó SIN traer nada" in line
    assert "Eso YA NO está en marcha" in line


def test_a_task_that_ended_WITH_something_says_that_instead(no_live_tasks, monkeypatch):
    monkeypatch.setattr(nt, "recently_finished", lambda now=None, limit=3: _finished(has_results=True))
    assert "terminó CON resultado" in _line("NAVEGADOR — YA TERMINADO")


def test_what_it_last_saw_travels_with_the_ending(no_live_tasks, monkeypatch):
    """“Only accepts reservations by phone” IS the result of the assignment, even if it is not the expected one."""
    monkeypatch.setattr(nt, "recently_finished",
                        lambda now=None, limit=3: _finished(
                            last_event="Casa Lucio solo acepta reservas por teléfono: 91 365 82 17"))
    line = _line("NAVEGADOR — YA TERMINADO")
    assert "91 365 82 17" in line
    assert "DÁSELO: es el resultado" in line


def test_with_nothing_finished_the_line_does_not_appear(no_live_tasks, monkeypatch):
    """ZERO cost when there is nothing to say — like the other markers in this block."""
    monkeypatch.setattr(nt, "recently_finished", lambda now=None, limit=3: [])
    assert _line("NAVEGADOR — YA TERMINADO") == ""


def test_a_live_task_now_carries_its_last_milestone(monkeypatch):
    monkeypatch.setattr(nt, "active_summaries", lambda limit=3: [("t9", "reservar mesa en Casa Lucio")])
    monkeypatch.setattr(nt, "active_progress",
                        lambda limit=3: [{"id": "t9", "goal": "x", "url": "https://www.thefork.es/casa-lucio",
                                          "phase": "", "steps": 3,
                                          "last_event": "el restaurante solo reserva por teléfono",
                                          "awaiting_login": False}])
    monkeypatch.setattr(nt, "recently_finished", lambda now=None, limit=3: [])
    line = _line("NAVEGADOR — YA EN CURSO")
    assert "solo reserva por teléfono" in line
    assert "3 pasos dados" in line


# ── the registry side ───────────────────────────────────────────────────────────────────────────────────────
def test_recently_finished_reports_what_the_task_ended_with():
    tid = nt.create("reservar mesa en Casa Lucio")
    nt.add_event(tid, "Casa Lucio solo acepta reservas por teléfono: 91 365 82 17")
    assert nt.active_progress()[0]["last_event"].startswith("Casa Lucio solo acepta")
    nt.finish(tid, "done")
    rows = [r for r in nt.recently_finished() if r["id"] == tid]
    assert rows and rows[0]["status"] == "done"
    assert rows[0]["has_results"] is False
    assert "91 365 82 17" in rows[0]["last_event"]
    assert not [t for t in nt.active_progress() if t["id"] == tid]   # and it is NO longer among the live ones


def test_an_old_ending_stops_being_reported():
    """Enough to cover the “did you get it?” turn, not to talk about yesterday’s message."""
    import time as _t
    tid = nt.create("un encargo viejo")
    nt.finish(tid, "done")
    assert [r for r in nt.recently_finished() if r["id"] == tid]
    later = _t.time() + nt.JUST_FINISHED_S + 60
    assert not [r for r in nt.recently_finished(now=later) if r["id"] == tid]


# ── V2-299: “WITHOUT bringing anything” was decided by the TASK record, and the sheet is the authority ─────────
#
# Measured on 2026-08-24 (second harness family: 7 rounds with the rows in the sheet 42–209 s before the last
# turn): the task ended, `has_results` was False because nobody got as far as calling `set_results` —dead worker,
# handoff—, and this view said “finished WITHOUT bringing anything” with 21 NAMED rows in the sheet. One step worse
# than the disappearance fixed by V2-150: that was a gap, this is an active lie in the prompt.
#
# These tests assemble the REAL CHAIN (task in the record + rows via `intake.push` + the real
# `recently_finished`) instead of patching `_sheet_top_rows`: the wiring is what is measured, and patching the seam
# under test would leave green a dismantling that removed it.

@pytest.fixture
def _isolated_sheet(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(nt, "_tasks", {})
    store._last_hash.clear()
    yield
    store._last_hash.clear()


def _done_task_with_sheet(rows, status="done", **over):
    import time as _time

    from widgets.results import intake
    t = {"id": "t1", "goal": "una guitarra acústica de segunda mano", "sheet": "hoja-x",
         "url": "https://es.wallapop.com", "status": status, "finished": _time.time() - 30, "events": []}
    t.update(over)
    nt._tasks["t1"] = t
    if rows:
        intake.push(rows, sheet="hoja-x")


def test_rows_in_the_sheet_beat_an_empty_task_record(_isolated_sheet):
    """The measured case: `set_results` never ran; the sheet has the rows. The sheet wins — and since the task has
    already FINISHED, saying “in the sheet” is a fact, not the on-screen claim that V2-278 prohibits in flight."""
    _done_task_with_sheet([{"title": "Fender CD-60", "price": "120 €", "url": "https://x/1"},
                           {"title": "Crafter FX 550", "price": "140 €", "url": "https://x/2"}])
    line = _line("NAVEGADOR — YA TERMINADO")
    assert "terminó SIN traer nada" not in line, \
        "con filas con nombre en la hoja, «SIN traer nada» es una mentira activa en el prompt"
    assert "Fender CD-60" in line and "120 €" in line, \
        "la orden de nombrarlo sin las filas delante es la trampa de V2-298 otra vez"
    assert "en la hoja de resultados" in line


def test_a_task_that_ended_empty_STILL_says_so(_isolated_sheet):
    """The other half of V2-150 is not lost: with no rows and no result, “finished WITHOUT bringing anything” remains
    the most useful fact of the three."""
    _done_task_with_sheet([])
    assert "terminó SIN traer nada" in _line("NAVEGADOR — YA TERMINADO")


def test_a_CANCELLED_task_does_not_get_rows_pinned_on_it(_isolated_sheet):
    """Stopping is not finishing (V2-196): the operator said to stop, and attaching rows to the cancelled task invites
    treating them as an ending that never happened. The fix applies to the FINISHED task, and only to it."""
    _done_task_with_sheet([{"title": "Fender CD-60", "price": "120 €"}], status="cancelled")
    line = _line("NAVEGADOR — YA TERMINADO")
    assert "se PARÓ (cancelada)" in line
    assert "Fender CD-60" not in line
