"""The errand STARTING, or just FINISHED, is an errand his sentence names — another errand's rows never answer it
(node 2.550).

three-tasks-at-once (EN, 2026-10-11 11:34, sandbox 113340-en). The game was parked on «want me to build it?». His
«yeah go ahead, and for the game make the jump feel higher, more floaty maybe» resolved it — the gate popped the ask
and re-escalated it, and the session registered about a second later. The delivery backstop ran in between: the game
was neither live nor parked, his sentence named no errand, and the reply came out «Alright, give me a moment to look
into that. Actually, there are already candidates on the results sheet: «MONITOR PC ORDENADOR 19"…». He had to
correct it: «no no, I mean the game… The monitor's separate.»

`nucleo/turn/errand_pool.starting` reads the escalation registry, which holds every asked escalation from the moment
it is asked: the gap between the ask and its session is exactly what it covers.
"""
from __future__ import annotations

import time
import types

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as dc
from nucleo.flash import delivery, escalate, live_blocks
from nucleo.turn import errand_pool, errands_of_a_turn as E, named_errand
from nucleo.workers import ended

REPORT = {"id": "4", "request": "Write a report on electric cars for city driving: which models suit urban use, range, "
                                "charging, running costs", "phase": "", "waiting_on": "", "surface": "informe", "sheet": ""}
MONITOR = {"id": "5", "request": E.listing_errand({"query": "used computer monitor cheap", "condition": "usado"}),
           "phase": "", "waiting_on": "", "surface": "lista", "sheet": "results::24fdf1-3"}
GAME = ("Build a new widget: a small side-scrolling platform game in Super Mario style (retro platformer): a character "
        "that runs and jumps across platforms. The jump should feel higher and more floaty")
ROWS = ['MONITOR PC ORDENADOR 19" MARCA — 30', "Monitor de computadora LCD AOC — 47", "Lote de 3X Monitor de PC LCD HP — 59.9"]
HEARD = "yeah go ahead, and for the game make the jump feel higher, more floaty maybe"
WAIT = "Alright, give me a moment to look into that."


@pytest.fixture
def between(monkeypatch):
    """The instant the measured backstop ran: the game's ask resolved, its session not registered yet."""
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(REPORT), dict(MONITOR)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(escalate, "_tasks", {9: {"request": GAME[:200], "started_at": time.time() - 1, "done": False,
                                                 "summary": ""}})
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (MONITOR["request"], list(ROWS)))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: True)
    delivery.forget_announced()


def test_a_sentence_about_the_game_being_launched_gets_no_monitor_rows(between):
    out = delivery.apply_to_reply(WAIT, [], heard_now=HEARD)
    assert out == WAIT, f"the monitor's rows answered a sentence about the game: {out!r}"


def test_the_starting_errand_is_named_and_is_not_an_injection_target(between):
    hits = named_errand.named(HEARD)
    assert [e.get("starting") for e in hits] == [True], hits
    assert E.promised_refinement(HEARD, "Passing the higher jump to the game build, I'll make it floatier.") == "", \
        "a starting errand has no session yet: its id would resolve to whatever else is live"


def test_once_its_session_registers_it_is_not_counted_twice(between, monkeypatch):
    live = dict(MONITOR, id="6", request=GAME)
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(REPORT), dict(MONITOR), live])
    assert not errand_pool.starting(named_errand.known()[:3]), "the live session IS the errand now"
    assert [e["id"] for e in named_errand.known()] == ["4", "5", "6"]


def test_an_old_or_finished_escalation_is_not_starting(between, monkeypatch):
    monkeypatch.setattr(escalate, "_tasks", {9: {"request": GAME[:200], "started_at": time.time() - 600,
                                                 "done": False, "summary": ""}})
    assert not any(e.get("starting") for e in named_errand.known())
    out = delivery.apply_to_reply(WAIT, [], heard_now="any news?")
    assert "MONITOR PC" in out, "with no errand named, the first delivery is unchanged"


def test_a_sentence_about_the_game_that_just_finished_gets_no_monitor_rows(between, monkeypatch):
    """EN, same round, turn 11: «how's the game coming?» got two monitor tails. Once the game is DONE it is neither
    live nor starting — it is in the ended snapshots, and his sentence still names it."""
    monkeypatch.setattr(escalate, "_tasks", {})
    monkeypatch.setattr(ended, "_ENDED_SESSIONS", {"6": {
        "id": "6", "goal": GAME, "status": "done", "ok": True, "summary": "", "at": time.time() - 20, "told": 0,
        "sheet": "", "title": "", "kind": "code", "error_class": ""}})
    monkeypatch.setattr(ended, "_live_goals", lambda: set())
    out = delivery.apply_to_reply(WAIT, [], heard_now="nice, and the mario game, is it playable now? did the jump get higher?")
    assert out == WAIT, f"the monitor's rows answered a sentence about the finished game: {out!r}"
