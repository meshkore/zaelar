"""A typed line is complete by construction (V2-825 F2, refactor2710-01 T-01).

Measured in a real session: a typed line of two sentences, the second without a closing stop, went through the VOICE
phrase accumulator. `dangling_tail` peeled the second sentence, held it `MAX_GAP_S`, dropped it and the drop notice
asked him to repeat into a text chat. The class: the accumulator is an STT instrument. The door is
`nucleo.input.of_turn` — the typed door's stamp makes the utterance complete — read by `hold_a_fragment`, so a typed
line is ONE turn with every word, and the same words SPOKEN still wait for the rest.

Disarm: drop `not _input.of_turn(text).complete` from `hold_a_fragment` → the typed case is held.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo import input as inp
from nucleo.input import stt as acc
from voice import attention
from voice.engine.llm.providers import turn_fragment

LINE = {"es": "Búscalo en los correos de antes de 2025. En cualquier caso, ábreme el documento que ya tienes",
        "en": "Look for it in the emails from before 2025. Either way, open the document you already have"}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(attention, "_state", dict(attention._state))
    acc.set_predicate(lambda t: (t.rstrip().endswith((".", "?", "!")), ""))
    yield
    acc.set_predicate(None)


def _brain():
    return SimpleNamespace(_acc=None, _acc_gen=0, _acc_trace_id="", _chain_grace=("", 0.0))


def _hold(brain, text):
    return asyncio.run(turn_fragment.hold_a_fragment(brain=brain, emit=lambda *a, **k: None, first_turn=False,
                                                     text=text))


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_typed_line_runs_whole_with_both_sentences(lang):
    attention.note_typed(text=LINE[lang])
    assert inp.of_turn(LINE[lang]).channel == inp.TYPED
    out = _hold(_brain(), LINE[lang])
    assert not out.get("__return__"), "a typed line was held for a continuation that cannot come"
    assert out.get("text", LINE[lang]) == LINE[lang], "a typed line lost words to the phrase accumulator"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_same_words_spoken_still_wait_for_the_rest(lang):
    assert inp.of_turn(LINE[lang]).channel == inp.VOICE
    brain = _brain()
    out = _hold(brain, LINE[lang])
    held = bool(out.get("__return__")) or out.get("text") != LINE[lang]
    assert held and brain._acc is not None, "speech without a closing stop must still reach the accumulator"
