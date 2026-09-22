"""V2-752 — a held fragment is glued to the next one only if the next one CONTINUES it.

THE INCIDENT (live session fce3eff3, 2026-09-22, +241.4 s). The operator said:

    «quita este vídeo y vamos otra vez al [inicio]»

Deepgram never delivered «inicio», so the fragment dangled on «al» and the accumulator held it —
correctly. A beat later he said something that was NOT the rest of it: «No me estás oyendo.» The
accumulator glued them by time adjacency alone and the turn was built from:

    «quita este vídeo y vamos otra vez al No me estás oyendo.»

Jev read that and answered `canvas=close`, `screen_action=youtube:close` at 0.93. The video card was
closed. He had not asked for it to be closed, and spent the next ninety seconds saying so.

Neither existing layer could catch it: layer 1 asks whether the MERGED text dangles (it ends in a full
stop, so «complete»), and layer 2 is only consulted when layer 1 says incomplete, so it never ran. Both
judge the merge after it has happened.

THE SECOND DEFECT, same module, same session, +182.3 s — structural and free to fix. The buffer held
two fragments and the acoustic layer returned the SECOND one longer. `_grows` compares the incoming
text against `text()`, the WHOLE buffer, saw no growth, and appended, so a clause he said once reached
the prompt, Jev, the memory processor and his chat wall twice:

    «y no son los que yo quería, Te acabo de decir lo que estaba pensando, Te acabo de decir lo que
     estaba pensando, que no lo has entendido.»

Row 19 of his real `memories` table still holds that sentence.

Run: .venv/bin/pytest tests/voice/unit/test_a_fragment_is_not_glued_to_whatever_comes_next.py
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import accumulator as acc
from nucleo.flash import continuation


def _offer(a: acc.Accumulator, text: str, *, now: float | None = None):
    return asyncio.run(a.offer(text, now=now))


@pytest.fixture(autouse=True)
def _no_judge():
    """Layer 2 out of the way: these cases are about the SEAM, and a live judge would answer a different
    question. Layer 1 (lexical, free) is left exactly as the product has it."""
    acc.set_judge(lambda t: ("incomplete", ""))
    yield
    acc.set_judge(None)


@pytest.fixture
def separate(monkeypatch):
    """The continuation verdict says these two lines are NOT one sentence."""
    monkeypatch.setattr(continuation, "continues", lambda held, incoming: (False, "continues_previous=separate (0.91)"))


@pytest.fixture
def one_sentence(monkeypatch):
    monkeypatch.setattr(continuation, "continues", lambda held, incoming: (True, "continues_previous=continues (0.88)"))


# ── 1 · THE INCIDENT ──────────────────────────────────────────────────────────────────────────────────
def test_a_complaint_is_not_the_end_of_his_previous_sentence(separate):
    """«quita este vídeo y vamos otra vez al» + «No me estás oyendo.» are two turns, not one."""
    a = acc.Accumulator()
    action, text, _why, _dropped = _offer(a, "quita este vídeo y vamos otra vez al")
    assert action == "hold", "a sentence dangling on «al» is held — that half was always right"

    action, text, _why, dropped = _offer(a, "No me estás oyendo.")
    assert "vamos otra vez al No me estás oyendo" not in text, (
        "THE BUG: the two fragments were glued by time adjacency and the turn was built from nonsense, "
        "which Jev then read as an order to CLOSE the video card (0.93)")
    assert "No me estás oyendo" in (text or "") or "No me estás oyendo" in (a.text() or ""), (
        "…and his new sentence must survive as its own turn — splitting may not lose it")


def test_the_half_he_never_finished_is_reported_not_silently_dropped(separate):
    """«…vamos otra vez al» cannot be answered on its own, so it goes out as DISCARDED — which is spoken.

    Losing his words in silence is the one outcome this module exists to prevent, and a split that
    quietly swallowed the held half would be a new way to do exactly that.
    """
    a = acc.Accumulator()
    _offer(a, "quita este vídeo y vamos otra vez al")
    _action, _text, _why, dropped = _offer(a, "No me estás oyendo.")
    assert "vamos otra vez al" in (dropped or ""), (
        "the unfinishable half must be reported as dropped, never swallowed")


def test_the_new_sentence_starts_its_own_chain_and_is_answered(separate):
    """Splitting must not cost the turn that caused it: the new fragment becomes the chain, and when it is
    a whole request it is answered NOW.

    (There is deliberately no branch for «but what if the held half was complete?». A complete fragment is
    delivered on arrival by layer 1 and never reaches a seam, so such a branch would be dead code — and a
    dead path through this function is one more place the watermark can be forgotten. What rescues a held
    half that really did carry a request is `_speak_acc_drop`, which hands it to the judge.)
    """
    a = acc.Accumulator()
    _offer(a, "pon música de jazz y")
    action, text, _why, dropped = _offer(a, "Oye, ¿qué hora es?")
    assert action == "act" and "qué hora es" in text, "the new sentence is this turn"
    assert "jazz" not in text, "…and the abandoned half does not ride along inside it"
    assert "jazz" in (dropped or ""), "…it is reported as dropped, which is spoken and handed to the judge"


# ── 2 · AND THE ORDINARY CASE IS UNTOUCHED ────────────────────────────────────────────────────────────
def test_a_sentence_said_in_two_halves_is_still_one_request(one_sentence):
    """The whole reason this module exists (V2-096). A verdict saying «continues» changes nothing."""
    a = acc.Accumulator()
    assert _offer(a, "Busca también en todas las")[0] == "hold"
    action, text, _why, _dropped = _offer(a, "páginas que puedas, ¿vale?")
    assert action == "act" and text == "Busca también en todas las páginas que puedas, ¿vale?"


def test_an_absent_verdict_keeps_todays_behaviour_bit_for_bit(monkeypatch):
    """Jev disabled, unreachable or unsure → glue, exactly as before. An absent classifier may never
    change behaviour on its own; the failure has to be in the safe direction, and the safe direction
    here is the one that was already shipping."""
    monkeypatch.setattr(continuation.jev if hasattr(continuation, "jev") else continuation,
                        "continues", continuation.continues, raising=False)
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: False)
    a = acc.Accumulator()
    _offer(a, "Busca también en todas las")
    action, text, _why, _dropped = _offer(a, "páginas que puedas, ¿vale?")
    assert action == "act" and text == "Busca también en todas las páginas que puedas, ¿vale?"


def test_the_verdict_is_only_asked_at_a_SEAM(monkeypatch):
    """The price is one round trip and it is paid only where two fragments are about to be joined.

    Measured over session fce3eff3: 10 turns of 28 reached that state. The other 18 must not pay, and a
    regression that asked on every turn would put ~780 ms in front of every sentence he says.
    """
    asked: list[tuple[str, str]] = []

    def _spy(held, incoming):
        asked.append((held, incoming))
        return True, ""

    monkeypatch.setattr(continuation, "continues", _spy)
    a = acc.Accumulator()
    _offer(a, "¿Qué hora es?")                     # complete on arrival, nothing buffered
    assert asked == [], "a turn that arrives whole must not pay for a question about a seam that is not there"
    _offer(a, "Busca también en todas las")        # held: still no seam, nothing to join it to
    assert asked == [], "holding a first fragment is not a seam either"
    _offer(a, "páginas que puedas, ¿vale?")        # NOW there is one
    assert len(asked) == 1 and asked[0][0] == "Busca también en todas las"


# ── 3 · THE SEAM THE ACOUSTIC LAYER RESTATED ──────────────────────────────────────────────────────────
def test_a_second_fragment_handed_back_longer_replaces_it_instead_of_doubling_it(one_sentence):
    """The +182.3 s case, verbatim. `_grows` used to compare only against the WHOLE buffer."""
    a = acc.Accumulator()
    _offer(a, "y no son los que yo quería,")
    _offer(a, "Te acabo de decir lo que estaba pensando,")
    # LiveKit's ChatContext hands the SECOND fragment back, grown — not a fresh delta.
    _action, text, _why, _dropped = _offer(a, "Te acabo de decir lo que estaba pensando, que no lo has entendido.")
    said = (text or a.text() or "")
    assert said.count("Te acabo de decir lo que estaba pensando") == 1, (
        f"a clause he said ONCE reached the prompt, Jev, the memory processor and his chat wall twice: {said!r}")
    assert "y no son los que yo quería," in said, "…and the fragment before it is not lost in the repair"


def test_a_repetition_across_the_seam_is_NOT_edited_out(one_sentence):
    """The repair deliberately stops at `_grows`. Collapsing a run repeated across the JOIN was tried and
    retired the same day: it cannot tell the acoustic layer restating itself from a person repeating
    themselves, and editing his words is the expensive direction. V2-747's seam case arrives as ONE
    incoming string, which `_deduped(incoming)` already covers; this asserts we did not quietly widen it."""
    a = acc.Accumulator()
    _offer(a, "Pero no deberías escucharme, ¿no? Porque no he dicho")
    _offer(a, "no he dicho la palabra Johnny,")
    assert a.text().count("no he dicho") == 2, (
        "a run repeated across two separate fragments is left exactly as he said it")
