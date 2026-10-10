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

from nucleo.flash import delivery
from nucleo.workers import ended
from voice import brain_notes

PROMISE = "Building it in the background — I'll let you know the moment it's ready."


@pytest.fixture
def world(monkeypatch):
    from nucleo.flash import live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("", []))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
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


def test_the_promise_is_corrected_in_english_with_the_reason_and_a_way_out(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _die()
    out = delivery.apply_to_reply(PROMISE, [])
    assert out.startswith(PROMISE)
    tail = out[len(PROMISE):]
    assert "building the widget just failed" in tail and "rate-limiting" in tail and "try again" in tail


def test_it_is_said_once_and_the_queued_notes_are_retracted(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _die()
    first = delivery.apply_to_reply(PROMISE, [])
    assert first != PROMISE
    assert ended._ENDED_SESSIONS["7"]["told"] == 1, "the prompt's counter must know it was said"
    assert brain_notes.drain() == [], "the next turn would announce the same death again"
    assert delivery.apply_to_reply(PROMISE, []) == PROMISE


def test_a_spanish_session_hears_it_in_spanish(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    _die()
    out = delivery.apply_to_reply("Vale, te aviso en cuanto esté.", [])
    assert "la construcción del widget acaba de fallar" in out and "limitando" in out


def test_a_quota_death_does_not_offer_a_retry_that_would_fail_the_same(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _die(error_class="credit")
    out = delivery.apply_to_reply(PROMISE, [])
    assert "out of credit" in out and "try again" not in out and "provider settings" in out


@pytest.mark.parametrize("reply", [
    "Sorry — the widget build failed because the provider is busy. Shall I retry?",     # already says it
    "Your next appointment is at 16:00 with the vet.",                                  # not a waiting reply
])
def test_a_reply_that_is_not_a_blind_promise_is_left_alone(world, monkeypatch, reply):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _die()
    assert delivery.apply_to_reply(reply, []) == reply
    assert ended._ENDED_SESSIONS["7"]["told"] == 0


@pytest.mark.parametrize("status", ["cancelled", "relevada"])
def test_a_stopped_or_relayed_errand_is_not_a_death(world, monkeypatch, status):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _die(status=status)
    assert delivery.apply_to_reply(PROMISE, []) == PROMISE


def test_a_death_the_prompt_already_carried_is_not_repeated(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _die()
    ended.mark_death_reported(["7"])
    assert delivery.apply_to_reply(PROMISE, []) == PROMISE


def test_the_death_note_is_keyed_so_it_can_be_retracted(world):
    _die()
    from nucleo.flash import death_line
    assert any(k == "death:7" for k, _ in brain_notes._pending)
    assert death_line.backstop(PROMISE)
    assert not any(k.endswith(":7") for k, _ in brain_notes._pending)
