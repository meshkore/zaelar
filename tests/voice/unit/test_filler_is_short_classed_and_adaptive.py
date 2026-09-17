"""V2-716 — the cover is SHORT, it is CLASSED right, and it stops when it has nothing to cover.

Measured in session 928c8761 (2026-09-17, English, 15 minutes, 53 turns): 21 covers sounded, **20 of them
drawn from the NEUTRAL pool** and **15 with no reply behind them at all**. The operator's words for it:

    «yo le decía algo o una pregunta y él no me contestaba; sin embargo, sí me soltaba la puñetera palabra
     de relleno … te digo que abras una ventana y el sistema dice Good question, lo cual es totalmente
     absurdo … quiero palabras más cortas, en plan one second, yes, checking, ok».

Four defects, one per section below. Each test names the real utterance that produced it, because the
regexes here are only defensible against the sentences that beat them.
"""
from __future__ import annotations

import pytest

from i18n import langs
from voice.engine.speech import filler_audio as fa


@pytest.fixture(autouse=True)
def _clean():
    fa._reset_for_tests()
    yield
    fa._reset_for_tests()


class _Brain:
    """The two attributes `arm()` reads off the brain, and nothing else."""

    def __init__(self, last_reply: str = ""):
        self._last_reply = last_reply
        self._last_filler = ""


# ── 1. SHORT. A cover cannot be cut mid-sentence, so its own length is latency ────────────────────────────

@pytest.mark.parametrize("code", ["es", "en"])
@pytest.mark.parametrize("kind", ["neutral", "action", "social", "ack"])
def test_every_cover_in_every_pool_is_at_most_three_words(code, kind):
    pool = {
        "neutral": "fillers", "action": "fillers_action",
        "social": "fillers_social", "ack": "fillers_ack",
    }[kind]
    phrases = getattr(langs.spec(code), pool)
    assert phrases, f"{code}/{pool} ships no pool"
    for p in phrases:
        words = p.rstrip("…").replace(",", " ").split()
        assert len(words) <= 3, f"{code}/{pool}: {p!r} is {len(words)} words — the operator asked for «vale»"


@pytest.mark.parametrize("code", ["es", "en"])
def test_the_cover_never_calls_the_operators_turn_a_good_question(code):
    """His named absurdity. It is banned by CONTENT, not by pool: a cover that comments on the turn can be
    wrong about it, and «Good question…» answering «the one in Telegram» is how he found out."""
    everything = sum((tuple(getattr(langs.spec(code), f, ()) or ()) for f in
                      ("fillers", "fillers_action", "fillers_social", "fillers_ack")), ())
    for p in everything:
        low = p.lower()
        assert "good question" not in low and "buena pregunta" not in low


# ── 2. CLASSED. The English half of the classifier, measured against the session's own sentences ──────────

@pytest.mark.parametrize("utterance", [
    "Hello? I'm talking to you.",                                    # 740.3 s — got «Good question…»
    "I I didn't tell you to play the music again.",                  # 747.1 s — got «Let me look that up…»
    "The music is playing right now. I did pause it manually, "
    "and you did start it without my request.",                      # 771.4 s
    "Is it done?",                                                   # 283.2 s — got «Let me pull that up…»
    "Is it all correct?",                                            # 336.3 s
    "And it was not working. So is there any problem?",              # 886.5 s
    "Okay. That was correct. This second time.",                     # 387.9 s
])
def test_an_english_complaint_about_us_is_social_not_a_thinking_sound(utterance):
    assert fa.filler_kind(utterance) == "social", utterance


@pytest.mark.parametrize("utterance", [
    "Awesome. Close everything. Please hide the chat. Column.",      # 365.8 s — got «I'll check that now…»
    "I said, hide the left chat. Column.",                           # 376.8 s — a RE-STATED order
    "So what I did say is, please, open the messages.",              # 790.5 s
    "I said I wanna see my WhatsApp.",                               # 801.9 s
    "So I wanna listen to some music soft music to fill the room.",  # 401.9 s
    "I want you to ask him if we can arrange a meeting today.",      # the INDIRECT imperative
    "You need to tell him that you're Johnny, my personal assistant.",
])
def test_an_order_is_an_order_however_it_is_framed(utterance):
    assert fa.filler_kind(utterance) == "action", utterance


def test_an_answer_to_our_own_question_is_a_receipt_not_a_look():
    """62.7 s. We asked «Which one would you like me to contact?»; «The one in Telegram.» is an ANSWER —
    nothing is being looked up and nothing is being explained."""
    brain = _Brain(last_reply="I have two matches. Which one would you like me to contact?")
    assert fa.filler_kind("The the one in Telegram.", last_reply=brain._last_reply) == "ack"
    assert fa.arm(brain, "The the one in Telegram.") in langs.spec("es").fillers_ack + \
        langs.spec("en").fillers_ack


def test_a_receipt_needs_a_question_of_ours_behind_it():
    """The narrowness is the point: without a question of ours, the same sentence is an ordinary turn."""
    assert fa.filler_kind("The the one in Telegram.", last_reply="Sending it now.") != "ack"
    assert fa.filler_kind("The one in Telegram, and also tell him what time?",
                          last_reply="Which one?") != "ack"     # it asks something itself


# ── 3. ADAPTIVE. «Si las latencias van por debajo del segundo, quizás no haga falta meterlas» ─────────────

def test_a_fast_engine_stops_arming_and_one_slow_turn_brings_the_cover_back():
    brain = _Brain()
    assert fa.arm(brain, "what's on my agenda") != "", "with no evidence it must arm normally"
    for _ in range(fa._FAST_WINDOW):
        fa.note_latency(500)
    assert fa.answering_fast()
    assert fa.arm(brain, "what's on my agenda") == ""
    fa.note_latency(fa.delay_ms() + 400)
    assert not fa.answering_fast(), "one turn over the deadline re-arms — dead air is the worse failure"
    assert fa.arm(brain, "what's on my agenda") != ""


def test_a_turn_that_spoke_nothing_is_not_evidence_of_speed():
    """`ttft_ms` is None on a turn the model never spoke through. Recording it as fast would silence the
    cover on the strength of a turn that produced no words at all."""
    for _ in range(fa._FAST_WINDOW):
        fa.note_latency(500)
    fa.note_latency(None)
    fa.note_latency(0)
    assert fa._RECENT_TTFT == [500] * fa._FAST_WINDOW
    assert fa.answering_fast()


# ── 4. NOT STRANDED. A cover that was the only thing said must not be followed by another ────────────────

def test_a_stranded_cover_silences_exactly_the_next_turn():
    """740-772 s: six covers in 32 seconds with two replies between them. One stumble is a stumble; the run
    is the conversation coming apart, so the turn after a stranded cover stays quiet — and only that one."""
    brain = _Brain()
    fa._note_stranded(True)
    assert fa.arm(brain, "open the messages") == ""
    assert not fa.stranded(), "the suppression is consumed, not sticky"
    assert fa.arm(brain, "open the messages") != ""


def test_the_promise_to_the_model_never_rides_a_turn_that_was_not_armed():
    """`arm()` appends a [SISTEMA] note telling the model which cover may sound. Every path that refuses to
    arm must also leave that note off — a promise of a phrase that cannot sound is prompt noise that steers
    the reply into continuing it."""
    for refuse in ("fast", "stranded", "dangling"):
        fa._reset_for_tests()
        if refuse == "fast":
            for _ in range(fa._FAST_WINDOW):
                fa.note_latency(500)
        elif refuse == "stranded":
            fa._note_stranded(True)
        text = "I want" if refuse == "dangling" else "what's on my agenda"
        messages = [{"role": "user", "content": text}]
        assert fa.arm(_Brain(), text, messages=messages) == ""
        assert "[SISTEMA]" not in messages[-1]["content"], refuse
