"""V2-747 — his sentence, once and in the order he said it.

## The session

`981dd54c` (2026-09-21). Deepgram finalised a segment early and reopened it, so the seam words arrived in
BOTH finals; LiveKit concatenated its finals faithfully and handed us the whole growing turn each time.
What the accumulator produced, verbatim from the timeline:

    +37.31 s  🧩 «Porque no he dicho no he dicho la palabra Johnny, Pero no deberías escucharme, ¿no?»
    +38.32 s  🧩 «Porque no he dicho no he dicho la palabra Johnny, y tienes activado el modo Pero no
                  deberías escucharme, ¿no? Porque no he dicho no he dicho la palabra Johnny, y tienes
                  activado el modo activation.»

That string went to the prompt, to Jev's turn brief, to the memory processor and to his chat wall. A real
task was born of one and is still in his database titled «Cambiar no en cualquier momento».

## Two independent faults, and both are about the SAME turn arriving bigger

1. **The peeled tail is re-prepended.** `_deliver` answers a head and keeps the dangling tail as the buffer
   — correct — but the next `offer` is the whole growing turn, head included, and `_grows` only recognised
   «incoming STARTS WITH the buffer». The buffer (a SUFFIX of what just arrived) went first, so the half
   already answered landed at the END and got answered a second time.
2. **The seam is doubled.** Nothing collapsed «no he dicho no he dicho».

His own complaint about this family, from the same session: *«lo conviertes en dos frases separadas cuando
es el mismo párrafo»*.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import accumulator as acc


@pytest.fixture
def held(monkeypatch):
    """Layer 2 always says «incomplete», so these measure layer 1 and the assembly, never a model."""
    async def _judge(_t):
        return "incomplete", ""
    monkeypatch.setattr(acc, "_judge", _judge)
    return acc.Accumulator()


def _offer(a, text, t):
    return asyncio.run(a.offer(text, now=t))


# ── the measured turn, step by step ───────────────────────────────────────────────────────────────────

# The three cumulative turns LiveKit handed us, byte for byte.
T1 = "Pero no deberías escucharme, ¿no? Porque no he dicho"
T2 = "Pero no deberías escucharme, ¿no? Porque no he dicho no he dicho la palabra Johnny,"
T3 = ("Pero no deberías escucharme, ¿no? Porque no he dicho no he dicho la palabra Johnny, "
      "y tienes activado el modo activation.")


def test_the_half_already_answered_is_not_answered_again(held):
    assert _offer(held, T1, 100.0)[1] == "Pero no deberías escucharme, ¿no?"
    for t, text in ((102.0, T2), (104.0, T3)):
        action, merged, _why, _d = _offer(held, text, t)
        assert "Pero no deberías escucharme" not in merged, (
            f"the sentence answered at +0 s came back inside the turn at +{t - 100:.0f} s: {merged!r}")


def test_and_what_is_left_is_in_the_order_he_said_it(held):
    _offer(held, T1, 100.0)
    _offer(held, T2, 102.0)
    action, merged, _why, _d = _offer(held, T3, 104.0)
    assert action == "act"
    assert merged == "Porque no he dicho la palabra Johnny, y tienes activado el modo activation.", merged


def test_a_seam_the_STT_restated_is_the_once_he_said_it(held):
    _offer(held, T1, 100.0)
    action, _m, _w, _d = _offer(held, T2, 102.0)
    assert action == "hold", "he is mid-sentence: “…la palabra Johnny,” closes nothing"
    assert held.text() == "Porque no he dicho la palabra Johnny,", held.text()


# ── the repairs, on their own ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,want", [
    ("Porque no he dicho no he dicho la palabra Johnny,", "Porque no he dicho la palabra Johnny,"),
    ("no he dicho la palabra no he dicho la palabra Johnny", "no he dicho la palabra Johnny"),
    ("Sí, sí, claro", "Sí, sí, claro"),                       # two words is a person, not a seam
    ("no, no he dicho eso", "no, no he dicho eso"),
    ("pon música", "pon música"),
    # THE FLOOR, and why it is three. Each of these collapses at two and each collapse changes the meaning:
    # an arithmetic phrase loses a factor, and an emphatic doubling loses the emphasis that IS the message.
    ("dos por dos por dos", "dos por dos por dos"),
    ("que no que no lo entiendo", "que no que no lo entiendo"),
    ("de la de la casa de al lado", "de la de la casa de al lado"),
])
def test_only_a_run_of_three_or_more_counts_as_the_STT_stuttering(raw, want):
    assert acc._deduped(raw) == want


def test_the_comparison_ignores_case_and_accents_because_the_STT_does(held):
    """Across a seam the STT is not consistent about either, and an exact-bytes comparison would miss the
    duplicate that is visibly there."""
    assert acc._deduped("Porque no he dicho Porque No he dichó la palabra") == "Porque no he dicho la palabra"


def test_a_brand_new_turn_keeps_every_one_of_its_words(held):
    """The guard that keeps this from eating a real sentence: the prefix must match EXACTLY, so anything
    that is not the same growing turn is untouched."""
    _offer(held, "Ponme música. Y luego", 10.0)
    assert held.consumed_head == "Ponme música."
    action, merged, _w, _d = _offer(held, "apágala en diez minutos.", 12.0)
    assert action == "act" and merged == "Y luego apágala en diez minutos.", merged


def test_the_watermark_case_V2_096_built_this_for_is_unchanged(held):
    """The measurement in `accumulator.py`'s own header, which must still hold to the word."""
    assert _offer(held, "pon música de jazz y", 1.0)[0] == "hold"
    assert _offer(held, "luego apágala. Oye, qué tiempo hace en", 3.0)[1] == "pon música de jazz y luego apágala."
    assert held.text() == "Oye, qué tiempo hace en"
    assert _offer(held, "Madrid mañana.", 5.0)[1] == "Oye, qué tiempo hace en Madrid mañana."


def test_a_turn_that_adds_nothing_new_is_held_rather_than_re_answered(held):
    """The acoustic layer re-sending a turn it already closed must not run it twice — the same string is
    not a second request."""
    assert _offer(held, "Ponme música.", 20.0)[0] == "act"
    assert _offer(held, "Ponme música.", 21.0)[0] == "hold"
