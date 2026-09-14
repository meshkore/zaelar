# V2-688 — «close all, open agenda, connect to my google calendar» cleared the canvas and did nothing else.
#
# Measured live on the operator's engine, 2026-09-14, flow `T10·c053`. The WHOLE event chain of that turn:
#
#     trace   turno
#     ambient ✋ interrupción dura atendida
#     widget  close
#     arbiter ⛔ vetaría · close-drag
#     flow    end
#
# No tool, no model call, no reply. Two thirds of one sentence discarded in silence — and the canvas DID
# clear, which looks enough like obedience to hide the two orders that were thrown away. He asked the same
# question a normal person would: «why is this order not followed?»
#
# ── Why the mechanism was right and the outcome wrong ────────────────────────────────────────────────
#
# `attention.hard_interrupt()` exists because a close order once got buried in a 14k-char turn and truncated
# away (T136). Its guarantee — a canvas close is executed DETERMINISTICALLY, before any model, always — is
# worth keeping and is not weakened here. What was never examined is the `return` that follows it: it treats
# «close» as the whole of what the operator said, which is true of «cierra todo» and false of every compound
# order. Speech is full of compound orders; that is how people clear a desk before starting something.
#
# So the close keeps its guarantee and the REST of the sentence keeps its turn.
#
# ⚠️ The closing clause is REMOVED from what the model reads, not left in. A model handed «close all» against
# an already-empty canvas re-emits it — the context-bleed shape V2-635 catalogued across four classes — and
# that second close would land on whatever the same sentence had just asked to open. Leaving the clause in
# would have turned one silent failure into an intermittent one, which is worse.
#
# ⚠️ NOT mirrored into the probe channel, deliberately, and the last test says why: the probe never had this
# defect. It calls the model with the full text and only LABELS the action afterwards
# (`probe.py`, «sin este espejo el probe daba veredictos FALSOS»), so the remainder always reached the model
# there. V2-252's rule is that a behaviour fixed in one channel is fixed in both — there is nothing to fix in
# the one that always worked, and stripping text before its model call would be a change with no defect
# behind it.
from __future__ import annotations

import pytest

from voice import attention


# ── The incident, and the shapes around it ───────────────────────────────────────────────────────────

def test_the_operators_own_sentence_keeps_its_other_two_orders():
    """Verbatim from flow T10·c053. The close is still detected — that guarantee is untouched — and what
    comes back is exactly the part that used to disappear."""
    said = "close all, open agenda, connect to my google calendar"
    assert attention.hard_interrupt(said) == "close", "the deterministic close must still fire"
    assert attention.close_all_remainder(said) == "open agenda, connect to my google calendar"


@pytest.mark.parametrize("said, rest", [
    # Spanish, joined by «y» — the other way a person chains two orders out loud.
    ("cierra todo, abre la agenda y conecta mi google calendar",
     "abre la agenda, conecta mi google calendar"),
    ("close all and play some music", "play some music"),
    ("quita todo, pon el temporizador a 5 minutos", "pon el temporizador a 5 minutos"),
])
def test_a_compound_close_keeps_what_follows_it_in_either_language(said, rest):
    """The standing constraint on every fix in this engine: valid for Spanish, for English, and never one at
    the other's cost. Both languages reach this through the same clause splitter, not through two tables."""
    assert attention.hard_interrupt(said) == "close"
    assert attention.close_all_remainder(said) == rest


# ── The counterweights: what must keep behaving exactly as it did ────────────────────────────────────

@pytest.mark.parametrize("said", [
    "cierra todo", "close everything", "cierra los widgets", "quita todo",
])
def test_a_bare_close_still_answers_NOTHING_and_the_turn_still_ends_there(said):
    """The half that matters most. An empty remainder is what tells the caller to behave exactly as before —
    execute the close and return — so a plain close must never grow a model turn it never had."""
    assert attention.hard_interrupt(said) == "close"
    assert attention.close_all_remainder(said) == ""


@pytest.mark.parametrize("said", [
    "cierra todo, por favor", "cierra todo ya", "cierra todo, gracias",
    "close everything please", "cierra todo ahora mismo",
])
def test_courtesy_and_timing_are_not_a_second_order(said):
    """«por favor» is not an errand. Without this the commonest polite phrasing in the product would spend a
    full model turn answering a word that asks for nothing — a cost paid on every single close."""
    assert attention.close_all_remainder(said) == "", said


def test_a_single_bare_word_is_not_confident_enough_to_be_an_order():
    """Conservative on purpose: the failure mode of answering "" is TODAY's behaviour, which is merely
    incomplete. The failure mode of guessing is a model turn acting on a fragment nobody meant as an order."""
    assert attention.close_all_remainder("cierra todo, agenda") == ""


def test_something_that_is_not_a_canvas_close_gets_no_remainder_at_all():
    """The guard on the entrance. This function may only ever run behind a real «close» verdict; asked about
    anything else it must answer "" rather than shredding a sentence nobody asked to split."""
    for said in ("abre la agenda", "open the agenda and play music", "conecta mi google calendar", ""):
        assert attention.close_all_remainder(said) == "", said


def test_an_enumeration_that_ends_in_a_quantifier_is_still_ONE_closing_clause():
    """`_REST_SPLIT_RE` splits on the comma and `_AND_SPLIT_RE` does not, which is the only difference between
    them and is deliberate. This case pins that the comma-blind one keeps deciding what a CLOSE is: an
    enumeration of things to close must not be read as a close plus two other orders."""
    said = "cierra el vídeo, la música y todo lo demás"
    if attention.hard_interrupt(said) == "close":
        assert attention.close_all_remainder(said) == "", "an enumeration is not a compound order"


# ── The wiring: a remainder nobody consults changes nothing ──────────────────────────────────────────

def _src(*parts: str) -> str:
    """Comment-stripped, because this defect is EXPLAINED in comments right beside the code that fixes it, and
    a scan its own explanation satisfies is a scan that proves nothing (V2-615's trap)."""
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[4].joinpath(*parts)
    return "\n".join(L for L in p.read_text("utf-8").splitlines() if not L.strip().startswith("#"))


def test_the_owner_of_the_decision_consults_the_remainder():
    """Anchored on the module that OWNS the block (V2-555), not on the caller it was extracted from — the
    whole hard-interrupt decision lives in `hard_turn.py` since the architecture ratchet was paid here."""
    body = _src("nucleo", "flash", "hard_turn.py")
    assert "close_all_remainder(text)" in body, "the remainder is never asked for"
    assert "return rest" in body, "the remainder never becomes what the turn goes on with"


def test_the_close_is_still_emitted_BEFORE_the_turn_is_allowed_to_continue():
    """The ordering IS the guarantee. If the remainder were computed first and the close only emitted on the
    way out, a failure in between would lose the one order this whole mechanism exists to never lose."""
    body = _src("nucleo", "flash", "hard_turn.py")
    close_at = body.index('emit("widget", "close"')
    rest_at = body.index("close_all_remainder(text)")
    assert close_at < rest_at, "the deterministic close must be emitted before anything else is decided"


def test_the_voice_turn_actually_CONTINUES_on_what_it_is_handed_back():
    """The caller's half, and the one that decides whether any of this reaches a model: `None` ends the turn
    exactly as the old unconditional `return` did, and anything else becomes the text of the turn."""
    body = _src("voice", "engine", "llm", "providers", "nucleo.py")
    assert "_hard_turn.handle(text, hard, emit)" in body, "the provider no longer delegates the decision"
    assert "if _cont is None:" in body and "text = _cont" in body, (
        "a turn that gets a remainder back has to go on with it")


def test_the_probe_channel_is_left_alone_and_that_is_a_decision():
    """V2-252 says a behaviour fixed in one channel is fixed in both. The probe never had this defect — it
    calls the model with the full text and only labels the action afterwards — so there is nothing to mirror,
    and this test exists so the absence reads as a decision rather than an omission."""
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "flash" / "probe.py"
    src = p.read_text("utf-8")
    assert "hard_interrupt" in src, "the probe still mirrors the DETECTION"
    assert "close_all_remainder" not in src, (
        "if the probe ever short-circuits before its model call, this fix has to travel with it")
