"""«¿Sigues ahí?» is a knock on the door, not a task (V2-640).

Born from the 19:27 live session (sid 1674ee35): the presence check went to a 3-5 s model turn, armed a
thinking filler («Déjame ver…»), and the operator spent the rest of the session asking what we wanted to
see. The lane answers the knock instantly and without a model — but only a WHOLE utterance that is nothing
but the knock: anything with content falls through untouched, because a canned phrase over a real request
erases it (the V2-605 lesson). Since refactor2710-07 what a knock IS is a `presence` row of the active language's
action map, not a regex.

Disarm: make `is_presence_check` compare against another row kind and the knock tests go red.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

import asyncio

import pytest

from voice.engine.llm.providers import fast_lane as fl


@pytest.fixture
def rows(monkeypatch, tmp_path):
    """The knock and the bare call are action-map ROWS of the active language (refactor2710-07): a fresh map, in `es`."""
    from memory import db as memdb
    from nucleo.actionmap import store
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()

    def _use(code):
        monkeypatch.setattr(store, "active_lang", lambda: code)
        store.invalidate()
    _use("es")
    yield _use
    store.invalidate()
    memdb.reset_db()


def test_a_presence_knock_is_recognized_in_both_languages(rows):
    for utt in ("¿Sigues ahí?", "¿Estás ahí?", "¿Me oyes?", "¿me escuchas bien?", "¿Hay alguien ahí?",
                "¿Estás disponible?", "¿estás operativo o no?", "sigues ahí o qué"):
        assert fl.is_presence_check(utt), f"{utt!r} must be a presence knock"
    rows("en")
    for utt in ("are you there?", "Are you still there?", "can you hear me?", "still there?"):
        assert fl.is_presence_check(utt), f"{utt!r} must be a presence knock"


def test_a_leading_vocative_does_not_hide_the_knock(rows):
    """V2-635's lesson applied here: «Johnny, ¿sigues ahí?» is the same knock."""
    assert fl.is_presence_check("Johnny, ¿sigues ahí?", assistant_name="Johnny")
    assert fl.is_presence_check("Oye, ¿me oyes?")


def test_content_is_never_swallowed_by_the_lane(rows):
    """Any utterance that carries a REQUEST must reach the model — a knock with cargo is not a knock."""
    for utt in ("¿Sigues ahí? Búscame un hotel", "¿Me oyes? cierra los mensajes",
                "¿Estás ahí para reservar la cena?", "¿Me puedes poner una imagen de fondo?",
                "¿Qué hora es?", "para", "Johnny"):
        assert not fl.is_presence_check(utt, assistant_name="Johnny"), f"{utt!r} must fall through"


def test_a_bare_call_by_name_is_a_summons_not_a_knock(rows):
    assert not fl.is_presence_check("Johnny.", assistant_name="Johnny")


class _Brain:
    def __init__(self):
        self._window = []


def _run_presence(monkeypatch, text, busy=False, speaker_available=True):
    spoken, events = [], []
    import voice.proactive as proactive
    monkeypatch.setattr(proactive, "speaker",
                        lambda: (lambda ph: spoken.append(ph)) if speaker_available else None)
    monkeypatch.setattr(proactive, "user_speaking", lambda: False)
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: busy)
    brain = _Brain()
    emit = lambda kind, label, text="", role="", extra=None, **kw: events.append(
        {"kind": kind, "extra": extra or {}})
    handled = asyncio.run(fl.presence(brain, text, emit, first_turn=False, window_max=24))
    return handled, spoken, events, brain


def test_the_knock_is_answered_instantly_and_lands_in_the_window(monkeypatch, rows):
    handled, spoken, events, brain = _run_presence(monkeypatch, "¿Sigues ahí?")
    assert handled and len(spoken) == 1 and spoken[0], "one spoken answer, no model"
    # The canned-line lesson (V2-605): a phrase of ours that skips the history erases its own story.
    roles = [m["role"] for m in brain._window]
    assert roles == ["user", "assistant"], f"the exchange must exist for the next turn: {roles}"
    assert brain._window[-1]["content"] == spoken[0]
    pres = [e for e in events if e["kind"] == "presence"]
    assert pres and pres[0]["extra"].get("engine") == "presence", \
        "observability must say no model resolved this turn"


def test_a_busy_agent_says_it_is_still_on_the_task(monkeypatch, rows):
    """Mid-task, «¿sigues ahí?» really asks about the TASK — the busy pool answers that."""
    from voice.engine.core import langs
    handled, spoken, _, _ = _run_presence(monkeypatch, "¿Sigues ahí?", busy=True)
    # The answer comes in the ACTIVE language (whatever the harness runs in) — the pool, not the words.
    assert handled and spoken[0] in langs.spec().presence_busy


def test_no_mouth_means_the_model_answers(monkeypatch, rows):
    """The chat channel has no speaker() — the lane must step aside, never eat the turn silently."""
    handled, spoken, _, brain = _run_presence(monkeypatch, "¿Sigues ahí?", speaker_available=False)
    assert not handled and not spoken and not brain._window


def test_the_first_turn_always_greets_through_the_brain(monkeypatch):
    import voice.proactive as proactive
    monkeypatch.setattr(proactive, "speaker", lambda: lambda ph: None)
    handled = asyncio.run(fl.presence(_Brain(), "¿estás ahí?", lambda *a, **k: None,
                                      first_turn=True, window_max=24))
    assert not handled, "the kickoff owns the first turn (memory-aware greeting)"


def test_the_voice_turn_actually_wires_the_lane():
    """A lane that exists only as a function is dead code: the VOICE provider (the turn the typed channel runs too)
    must call it, through the ONE detector."""
    import os
    eng = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    prov = _vts.read(os.path.join(eng, "voice/engine/llm/providers/nucleo.py"))
    assert "_fast_lane.presence(" in prov, "the voice provider no longer calls the presence lane"
    lane = open(os.path.join(eng, "voice/engine/llm/providers/fast_lane.py")).read()
    assert "from nucleo.flash.presence import is_presence_check" in lane, \
        "the lane must read ONE detector (nucleo/flash/presence.py)"
