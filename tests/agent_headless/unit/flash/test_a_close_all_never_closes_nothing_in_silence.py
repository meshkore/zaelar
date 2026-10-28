"""A close-all never closes nothing, and never in silence (V2-812 T-04).

Measured in a moving car (phone PWA): «Vale, Johnny, cierra ciérralo todo.» and «¿Me has oído, Johnny? Ciérralo
todo.» each reached the hard interrupt, and each time `bulk_close` spared «the card in use» — the music card, the
ONLY card open — so nothing closed, and the hard turn ended without a word. The order to close everything was a
no-op, and the silence made it indistinguishable from one that had worked.

The class, read from facts and never from words: a spare that would leave nothing to close is no spare (the order
is about those very cards), and every bulk close leaves a receipt — one short line in his language with what it
closed and what is still on screen — which the doors without a model reply of their own speak.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import done_ops
from nucleo.flash import bulk_close


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    done_ops.reset()
    bulk_close.reset()
    from nucleo import canvas_arbiter          # the turn ordered the close: the licence the canvas door reads
    monkeypatch.setattr(canvas_arbiter, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("close", 0.9)}})
    yield
    done_ops.reset()
    bulk_close.reset()


@pytest.fixture
def lang(monkeypatch, request):
    from i18n import langs
    code = getattr(request, "param", "es")
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(code))
    return langs.spec(code)


def _collect():
    events: list[tuple] = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, dict(extra or {})))
    return events, emit


def _closed(events) -> list:
    return [e[2].get("id", "*ALL*") for e in events if e[0] == "widget" and e[1] == "close"]


@pytest.mark.parametrize("said", ["Vale, Johnny, cierra ciérralo todo.", "Okay Johnny, close it all."])
def test_the_only_card_in_use_closes_when_he_says_close_everything(said):
    done_ops.note("musica", "play", {"query": "Burna Boy"})
    events, emit = _collect()
    kept = bulk_close.close_all(emit, src="flash", text=said, open_ids=["musica"])
    assert kept == []
    assert _closed(events) == ["*ALL*"], "sparing the only card turned «close everything» into a no-op"


def test_the_spare_still_keeps_the_draft_among_other_cards():
    """The half that must not move: V2-807 T-08's draft among OTHER cards is still kept."""
    done_ops.note("documento", "show", {})
    events, emit = _collect()
    assert bulk_close.close_all(emit, src="flash", text="cierra lo que no necesites",
                                open_ids=["documento", "navegador"]) == ["documento"]
    assert _closed(events) == ["navegador"]


def test_disarmed_the_only_card_is_spared_again(monkeypatch):
    """RED proof: with the old spare (no «would it close nothing?» reading) the car-session no-op comes back."""
    done_ops.note("musica", "play", {})
    monkeypatch.setattr(bulk_close, "spare_for", lambda opened, text="", **k: bulk_close.in_use(opened, text))
    events, emit = _collect()
    bulk_close.close_all(emit, src="flash", text="Ciérralo todo.", open_ids=["musica"])
    assert _closed(events) == [], "the disarm did not land"
    monkeypatch.undo()
    done_ops.note("musica", "play", {})
    events, emit = _collect()
    bulk_close.close_all(emit, src="flash", text="Ciérralo todo.", open_ids=["musica"])
    assert _closed(events) == ["*ALL*"]                                   # green again


@pytest.mark.parametrize("lang,closed_word,left_word", [
    ("es", "He cerrado", "Sigue en pantalla"),
    ("en", "I've closed", "Still on screen"),
], indirect=["lang"])
def test_the_receipt_says_what_closed_and_what_stayed(lang, closed_word, left_word):
    done_ops.note("documento", "show", {})
    events, emit = _collect()
    bulk_close.close_all(emit, src="flash", text="x", open_ids=["documento", "navegador", "results::4609d2-1"])
    line = bulk_close.take_receipt()
    assert line.startswith(closed_word) and left_word in line, line
    assert "4609d2" not in line and "::" not in line, f"an id reached a spoken line: {line}"
    assert bulk_close.take_receipt() == "", "a receipt is said once"


@pytest.mark.parametrize("lang", ["es", "en"], indirect=True)
def test_closing_everything_says_nothing_is_left(lang):
    done_ops.note("musica", "play", {})
    events, emit = _collect()
    bulk_close.close_all(emit, src="flash", text="x", open_ids=["musica"])
    line = bulk_close.take_receipt()
    assert line.endswith(lang.receipt_left_none) and lang.receipt_closed.split("{")[0].strip() in line, line


def test_a_stale_receipt_is_not_said_on_a_later_turn(monkeypatch):
    events, emit = _collect()
    bulk_close.close_all(emit, src="flash", text="x", open_ids=["navegador"])
    later = bulk_close.time.time() + bulk_close.RECEIPT_S + 1
    monkeypatch.setattr(bulk_close.time, "time", lambda: later)
    assert bulk_close.take_receipt() == ""


@pytest.mark.parametrize("lang,said", [("es", "¿Me has oído, Johnny? Ciérralo todo."),
                                       ("en", "Did you hear me? Close it all.")], indirect=["lang"])
def test_the_hard_interrupt_speaks_its_receipt(lang, said, monkeypatch):
    """The car session's door: the hard close used to end the turn without a word."""
    from nucleo.flash import hard_turn
    from voice import proactive
    spoken: list[str] = []
    monkeypatch.setattr(proactive, "speaker", lambda: spoken.append)
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: ["musica"])
    done_ops.note("musica", "play", {})
    events, emit = _collect()
    asyncio.run(hard_turn.handle(said, "close", emit))
    assert _closed(events) == ["*ALL*"]
    assert spoken and spoken[0].endswith(lang.receipt_left_none), spoken


def test_disarmed_the_hard_interrupt_is_silent_again(monkeypatch):
    """RED proof: without the receipt door the hard close says nothing — the test reads the door, not a constant."""
    from nucleo.flash import hard_turn
    from voice import proactive
    spoken: list[str] = []
    monkeypatch.setattr(proactive, "speaker", lambda: spoken.append)
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: ["musica"])

    async def _mute(emit, brain=None):
        return ""
    monkeypatch.setattr(hard_turn, "say_receipt", _mute)
    events, emit = _collect()
    asyncio.run(hard_turn.handle("Ciérralo todo.", "close", emit))
    assert spoken == [], "the disarm did not land"
    monkeypatch.undo()
    monkeypatch.setattr(proactive, "speaker", lambda: spoken.append)
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: ["musica"])
    asyncio.run(hard_turn.handle("Ciérralo todo.", "close", emit))
    assert spoken, "green again"


def test_the_action_map_close_all_speaks_the_receipt_instead_of_a_bare_ack(monkeypatch):
    from voice.engine.llm.providers import fast_lane
    from voice import proactive
    spoken: list[str] = []
    monkeypatch.setattr(proactive, "speaker", lambda: spoken.append)
    events, emit = _collect()
    bulk_close.close_all(emit, src="actionmap", text="cierra todo", open_ids=["navegador"])

    class _Brain:
        _last_ack = ""
    asyncio.run(fast_lane._speak_ack(_Brain()))
    assert spoken and bulk_close.receipt(["navegador"], []) == spoken[0]
