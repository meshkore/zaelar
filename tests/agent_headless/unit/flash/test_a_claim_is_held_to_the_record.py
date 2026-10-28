"""What the reply CLAIMS is held to what the turn did and what the record says (demo, 2026-10-22).

Three shapes from one session:
  · «…to make it happen. I need the plan of five days.» — the brief named a Brain Worker's sheet as the end state,
    the LATE catalogue guessed `agenda` from the words alone, and the promise repair wrote the sentence into his
    agenda as a task (and opened it).
  · «Sorry — I haven't actually looked at that yet, and nothing is running» — said with two workers live.
  · «Nothing left running — I've cleared it» / «it's stopped» — said with the monitor search live, nothing called.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from nucleo.flash import answer_guards as _ag, card_commission as _cc, second_pass as _sp
from nucleo.turn import brief as _tb
from nucleo.circuit import spec as _spec


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {k: {"choice": v, "confidence": 0.95} for k, v in verdicts.items()}}


# ── the late catalogue may not contradict the end state the brief named ─────────────────────────────────────

def _late(monkeypatch, card: str, brief) -> str:
    from nucleo import jev
    monkeypatch.setattr(jev, "choose_sync", lambda *a, **k: {"choice": card, "confidence": 0.77})
    return _cc.named_or_catalogue(brief, "happen. I need the plan of five days.")


def test_a_late_guess_against_the_named_end_state_names_no_card(monkeypatch):
    b = _brief(**{_tb.TARGET_KEY: "none", _spec.END_KEY: "results:empty"})
    assert _late(monkeypatch, "agenda", b) == ""


def test_without_an_end_state_the_late_catalogue_still_names_its_card(monkeypatch):
    b = _brief(**{_tb.TARGET_KEY: "none"})
    assert _late(monkeypatch, "agenda", b) == "agenda"


def test_a_card_that_attests_the_end_state_is_never_contradicted():
    b = _brief(**{_spec.END_KEY: "results:empty"})
    assert _spec.card_contradicts(b, "results::48ac70-3") == ""
    assert "agenda" in _spec.card_contradicts(b, "agenda")
    assert _spec.card_contradicts(_brief(), "agenda") == ""


def test_the_retraction_does_not_say_nothing_runs_while_something_does(monkeypatch):
    from nucleo import dispatch

    async def _no_look(*a, **k):
        return ""
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(_sp, "promise_repair", _no_look)
    monkeypatch.setattr(_ag, "a_promise_left_hanging", lambda *a, **k: True)
    said: list = []
    out = asyncio.run(_sp.hollow_repairs("okay. It's done.", "Checking… let me see all five sections.", [], None,
                                         did_act=False, covered=False, speak=said.append, emit=lambda *a, **k: None))
    assert said and "nothing is running" not in out.lower() and "no hay nada en marcha" not in out.lower()


def _live(monkeypatch, rows):
    from nucleo.circuit import ledger as tasks
    monkeypatch.setattr(tasks, "board", lambda scope="live", **k: rows if scope == "live" else [])


