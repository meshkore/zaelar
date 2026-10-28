"""A waiting reply written blind to a death that just happened says the errand died — once, in his language.

Measured 2026-10-10 20:54 (use case `build-workout-tracker-widget__us`, text channel): the widget build died on a
rate limit while the operator's «no rush» turn was in flight. All three death paths fired — `ended` pushed a
note, `_deliver` pushed one and `proactive.notify` (no live speaker) pushed a third — but notes ride the NEXT
turn, that turn's prompt predated the death, and its reply 0.3 s later was «Building it in the background — I'll
let you know the moment it's ready». No next turn came: quiescence settled with pending_workers=0 and the
operator never heard that the build had failed.
"""
from __future__ import annotations

import pytest

from nucleo.workers import ended
from voice import brain_notes

PROMISE = "Building it in the background — I'll let you know the moment it's ready."


@pytest.fixture
def world(monkeypatch):
    from nucleo.flash import live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("", []))
    monkeypatch.setattr("nucleo.dispatch.pending_summaries", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(ended, "_live_goals", lambda: set())
    ended._ENDED_SESSIONS.clear()
    brain_notes.drain()
    yield
    ended._ENDED_SESSIONS.clear()
    brain_notes.drain()


def _die(task_id="7", kind="code", error_class="rate", status="error"):
    from nucleo.workers.session import SessionRecord
    rec = SessionRecord(task_id=task_id, goal='Build a new widget called "workouts"', kind=kind)
    rec.ok, rec.status, rec.error_class = False, status, error_class
    rec.result_summary = "No pude crear el widget — el proveedor está saturado, prueba en un momento."
    ended._remember_ended(rec)
    # the two other death notes `_deliver` queues for the next turn, under their keys
    brain_notes.push(f"[SISTEMA] Brain worker · Tarea sin completar: {rec.result_summary}", key=f"delivery:{task_id}")
    brain_notes.push("[SISTEMA] Aviso para el operador (zaelar): Couldn't build the workouts widget.",
                     key=f"notice:{task_id}")
    return rec


def test_the_death_note_is_keyed_so_it_can_be_retracted(world):
    _die()
    from nucleo.flash import death_line
    assert any(k == "death:7" for k, _ in brain_notes._pending)
    assert death_line.backstop(PROMISE)
    assert not any(k.endswith(":7") for k, _ in brain_notes._pending)
