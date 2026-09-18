"""fix08 · a consumed one-shot note does not live in the dialog window.

Measured live, session 6d19df41: a worker's interim web lead («Scarborough — 2.5 h,
book on Expedia… NÓMBRALO EN ESTE TURNO») was drained into one turn's prompt, and that
turn answered the operator's question first. Four turns later («Vale, ¿qué más?»), with
the worker at 0/5 and 0%, the brain said «meanwhile, on the Scarborough search…» — the
Expedia detail could only come from the note, still sitting in the window of the old
turn. A one-shot note had become permanent context, and every later turn re-read it as
pending news.

`brain_notes.drain()` already says it: ONE-SHOT notes for the NEXT turn. The leak was
one door over: the voice provider stored the COMPOSED turn (his words + the notes) in
`brain._window`, so the consumed note rode along forever. The store must keep his words
(`operator_text`, captured before the notes are composed); the model still SEES the notes
this turn, and the reply still records what was said. The barge-in path is untouched: a
cancelled turn never answered, so its notes are unconsumed and stay visible.
"""
from __future__ import annotations

import re
from pathlib import Path

from nucleo.flash import dialog as _dialog
from voice import brain_notes

_OP = "Have a look at my messages to see if there's anything about the car."
_NOTE = ("[SISTEMA] Brain worker · HALLAZGO WEB INTERINO (díselo con tus palabras, NÓMBRALO "
         "EN ESTE TURNO): Scarborough — de 2.5 h, se reserva en Expedia.")


def _code(rel: str) -> str:
    src = Path(rel).read_text(encoding="utf-8")
    return re.sub(r"(?m)^\s*#.*$", "", src)


def test_the_operator_half_survives_the_round_trip():
    composed = brain_notes.compose_turn(_OP, [_NOTE])
    assert _NOTE in composed  # the model sees it this turn
    assert brain_notes.operator_half(composed) == _OP


def test_what_the_window_keeps_has_no_note_in_it():
    """The provider's store step, through the real functions: compose, then keep the
    operator half. A later turn re-reading this window finds no note to re-narrate."""
    composed = brain_notes.compose_turn(_OP, [_NOTE])
    window: list = []
    _dialog.push_user(window, brain_notes.operator_half(composed))
    assert window == [{"role": "user", "content": _OP}]
    assert not any("[SISTEMA]" in m["content"] for m in window)


def test_the_success_path_stores_his_words_not_the_composed_turn():
    code = _code("voice/engine/llm/providers/nucleo.py")
    assert "_dialog.push_user(brain._window, operator_text)" in code
    assert code.count("_dialog.push_user(brain._window, text)") == 1, (
        "only the barge-in path — the turn that never answered — may keep the composed text")
