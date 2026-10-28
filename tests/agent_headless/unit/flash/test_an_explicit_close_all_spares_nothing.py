"""«Close all» closes ALL — an explicit total is not a vague close (V2-831 T-02, class 1).

Measured 2026-10-28, typed, EN: «close all» → the hard interrupt closed Messages, Results and Browser and KEPT the
Document (a data-op ran on it four minutes before — the V2-807 T-08 spare). He had to say it twice more.

The grammar that matched «close all» already read that its quantifier governs the canvas; that reading now reaches
the bulk close (`interrupt_grammar.close_scope` → `scope="all"`), which spares nothing. The spare stays for a close
that restricts or names no total («close everything you don't need», V2-807 T-08), and a spare still never empties
the order (V2-812 T-04). The grammar is es + en only; there is no third language to test it in.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import done_ops
from nucleo.flash import bulk_close, dialog, hard_turn
from voice import interrupt_grammar

OPEN = ["documento", "navegador", "mensajeria"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    done_ops.reset()
    bulk_close.reset()
    from nucleo.acts import canvas_turn
    monkeypatch.setattr(canvas_turn, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("close", 0.9)}})
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: list(OPEN))
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)
    done_ops.note("documento", "show", {"body": "draft"})      # the Document is the card in use
    yield
    done_ops.reset()
    bulk_close.reset()


def _collect():
    events: list[tuple] = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, text, dict(extra or {})))
    return events, emit


def _closed(events) -> list:
    return [e[3].get("id", "*ALL*") for e in events if e[0] == "widget" and e[1] == "close"]


class _Brain:
    def __init__(self):
        self._window = [{"role": "user", "content": "continue with my dexter request"},
                        {"role": "assistant", "content": "On it — checking where Season 2 streams."}]
        self._last_reply = "On it — checking where Season 2 streams."
        self._last_spoken = ""
        self._last_spoke_at = 0.0


# ── class 1 ─────────────────────────────────────────────────────────────────────────────────────────────────────
TOTALS = ["close all", "Close all.", "close everything", "close all the widgets",
          "Ciérralo todo.", "cierra todo", "cierra todas las tarjetas"]


@pytest.mark.parametrize("said", TOTALS)
def test_an_explicit_total_closes_the_card_in_use_too(said):
    assert interrupt_grammar.hard_interrupt(said) == "close"
    events, emit = _collect()
    assert asyncio.run(hard_turn.handle(said, "close", emit)) is None
    assert _closed(events) == ["*ALL*"], f"{said!r} spared a card: {_closed(events)}"


@pytest.mark.parametrize("said", ["Close everything you don't need right now", "cierra los widgets"])
def test_a_close_that_names_no_total_still_spares_the_working_card(said):
    """V2-807 T-08 stays: the hard door fires on these too, and the card in use stays."""
    assert interrupt_grammar.hard_interrupt(said) == "close"
    assert interrupt_grammar.close_scope(said) == ""
    events, emit = _collect()
    asyncio.run(hard_turn.handle(said, "close", emit))
    assert sorted(_closed(events)) == ["mensajeria", "navegador"]


def test_the_scope_is_the_grammars_own_reading():
    for said in TOTALS:
        assert interrupt_grammar.close_scope(said) == "all", said
    for said in ["cierra todo lo que no necesites", "Close also the agenda. And reposition all the widgets.",
                 "quita todas esas entradas", "exit fullscreen, close all", "i said all"]:
        assert interrupt_grammar.close_scope(said) == "", said


def test_a_spare_never_empties_the_order_still_holds():
    """V2-812 T-04 stays: one card open and in use, a vague close still closes it."""
    events, emit = _collect()
    assert bulk_close.close_all(emit, src="flash", text="close what you don't need", open_ids=["documento"]) == []
    assert _closed(events) == ["*ALL*"]


def test_disarmed_without_the_scope_close_all_spares_the_draft_again():
    """RED proof: drop the grammar's scope and «close all» is the vague close — the Document stays."""
    real = interrupt_grammar.close_scope
    interrupt_grammar.close_scope = lambda text: ""
    try:
        events, emit = _collect()
        asyncio.run(hard_turn.handle("close all", "close", emit))
        assert sorted(_closed(events)) == ["mensajeria", "navegador"], "the disarm did not land"
    finally:
        interrupt_grammar.close_scope = real
    bulk_close.reset()
    events, emit = _collect()
    asyncio.run(hard_turn.handle("close all", "close", emit))
    assert _closed(events) == ["*ALL*"]                                  # green again
