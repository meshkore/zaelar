"""V2-752 — the assistant's name is not written on the small model's signature alone.

THE INCIDENT (live session fce3eff3, 2026-09-22, +154.9 s). The operator corrected a mangled video search:
«He dicho, Apollo once.» The memory processor distilled an atom `slot: assistant.name`, `value: "Apollo 11"`, and it
was WRITTEN: the prompt told the model «Tú te llamas Apollo 11» and the wake word moved with it, across sessions.

V2-747 excused this slot from two guards (correctly), so it needs an answer of its own to «does this utterance give
the assistant a name?». V2-752 asked Jev that question again, after the reply (`rename_decision`, 19 re-runs in 14
days). V2-851 F5 reads the answer the turn already paid for: the brief's SURE `identity_change = rename` verdict,
kept by `nucleo.turn.identity` (`rename_heard`). No verdict, an old one, or another name → the atom is dropped.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import slots
from nucleo.turn import identity


@pytest.fixture(autouse=True)
def clean():
    identity._HEARD.update(name="", at=0.0)
    yield
    identity._HEARD.update(name="", at=0.0)


def _sure(name="", conf=0.95):
    import threading
    ev = threading.Event()
    ev.set()
    brief = {"event": ev, "turn_id": "t", "result": {identity.KEY: {"choice": identity.RENAME, "confidence": conf}}}
    asyncio.run(identity.settle(brief, name, lambda *a, **k: None, ingest=False))


def test_a_corrected_search_term_is_not_a_new_name():
    """No rename verdict this session: «Apollo 11» from the distiller is dropped."""
    assert not identity.rename_heard("Apollo 11")


def test_a_real_rename_still_lands(monkeypatch):
    monkeypatch.setattr(identity, "apply_rename_now", lambda n: None)
    _sure("Johnny")
    assert identity.rename_heard("Johnny") and identity.rename_heard("johnny")
    assert not identity.rename_heard("Apollo 11"), "another name than the one the turn gave is not his rename"


def test_an_unsure_or_old_verdict_renames_nothing(monkeypatch):
    monkeypatch.setattr(identity, "apply_rename_now", lambda n: None)
    _sure("Johnny", conf=0.6)
    assert not identity.rename_heard("Johnny"), "below SURE nothing is heard"
    _sure("Johnny")
    import time
    assert not identity.rename_heard("Johnny", now=time.time() + identity.HEARD_S + 1)


def test_the_slot_keeps_both_V2_747_exemptions():
    spec = slots.SLOTS["assistant.name"]
    assert spec.about_operator is False, "a rename never talks about the operator — V2-747"
    assert spec.garble_guard is False, "a rename contradicts the old value on purpose — V2-747"
    assert spec.state_field == "assistant_name"


def test_the_write_path_reads_the_turns_verdict_and_asks_nothing():
    """The seam, and the disarm of V2-851 F5: the atom path consults `rename_heard`, drops the atom on a no, and
    makes no Jev call of its own."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[3] / "nucleo/memory_agent/ingest.py"
    from tests import voice_turn_source as _vts
    body = _vts.read(src)
    i = body.index('if a.get("slot") == "assistant.name"')
    guard = body[i:i + 300]
    assert "rename_heard" in guard and "continue" in guard
    assert not (pathlib.Path(__file__).resolve().parents[3] / "nucleo/memory_agent/rename_decision.py").exists()
