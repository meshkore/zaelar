#
# test_the_word_is_the_only_way_in.py — V2-749. In a mode whose whole promise is «I stay quiet until you say
# my name», nothing may open a COLD turn without it.
#
# THE MEASUREMENT. Session 48394dd0 (2026-09-22), the operator's own test with the 🤖 on. The agent greeted
# him and asked «¿Cómo te llamas?»; he answered «Me llamo Paco.» three times. The first two were discarded
# (`reason: ambient`, `mode: smart`) and the third was HANDLED with `reason: unanswered_repeat` — no wake
# word anywhere in the session. His words:
#
#   «está ignorando el Word Activation Mode… no sé por qué se ha puesto a escuchar pero sin que sonara la
#    palabra de activación. Entonces hay que ser estrictos. Si hay palabra de activación, el agente debe
#    quedarse quieto. Otra cosa es que esté haciendo procesos por detrás, pero el sistema de voz está parado.»
#
# WHAT IS NOT BEING UNDONE. The hatch itself is V2-743, from the day before, and it is right where there is
# no way to insist: in `always` the operator cannot re-open attention except by speaking again, which is
# exactly the signal it reads. What changes is that in `smart`/`wakeword` he CAN — two syllables — so the
# back door closes and the front one stays open. Both halves are asserted here; a fix that took the hatch
# out altogether would pass half of this file and fail the other.
#
import asyncio

import pytest

from voice import attention


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    attention.set_directed_judge(None)
    yield
    attention.reset()
    attention.set_directed_judge(None)


def _streak(n: int, now: float) -> None:
    """`n` consecutive discards, the way the real gate records them."""
    for i in range(n):
        attention.note_ambient(f"discarded {i}", now=now - (n - i))


# ── the back door is shut where a word can re-open the front one ───────────────────────────────────────
@pytest.mark.parametrize("mode", ["smart", "wakeword"])
def test_a_streak_of_discards_does_not_open_a_cold_turn_in_a_wake_word_mode(monkeypatch, mode):
    monkeypatch.setenv("ZAELAR_ATTENTION", mode)
    now = 1000.0
    _streak(3, now)
    assert attention.unanswered_streak(now) >= attention._UNANSWERED_OPENS_AT, \
        "the streak must still be RECORDED — the reading is what changes, not the counting"
    v = attention.evaluate("Me llamo Paco.", now=now)
    assert not v.directed, "his own measured case: answered without the word ever being said"
    assert v.reason == "ambient"


def test_the_streak_still_opens_a_cold_turn_in_always(monkeypatch):
    # V2-743 intact where it was measured to be needed: no wake word exists in this mode, so speech that
    # keeps coming while nobody answers is the only signal left that he is talking to a wall.
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")
    now = 1000.0
    _streak(2, now)
    v = asyncio.run(attention.evaluate_content("¿Hola?", context="Zaelar dijo algo", now=now))
    assert v.directed and v.reason == "unanswered_repeat"


@pytest.mark.parametrize("mode,expected", [
    ("smart", True), ("wakeword", True), ("always", False), ("ptt", False),
])
def test_only_a_mode_with_a_word_counts_as_having_a_way_back_in(monkeypatch, mode, expected):
    # `ptt` recovers with a BUTTON, not a word, and its gate is already an explicit act per turn — reading
    # it as "he can talk his way back in" would silence a mode that has no voice route at all.
    monkeypatch.setenv("ZAELAR_ATTENTION", mode)
    assert attention._has_wake_recovery() is expected


# ── …and the front door is untouched ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["smart", "wakeword"])
def test_the_word_still_opens_it_after_a_streak(monkeypatch, mode):
    monkeypatch.setenv("ZAELAR_ATTENTION", mode)
    now = 1000.0
    _streak(4, now)
    v = attention.evaluate("Zaelar, ¿qué hora es?", now=now)
    assert v.directed and v.reason == "wakeword"


def test_an_open_conversation_still_answers_without_the_word(monkeypatch):
    # The window a wake word opened is a conversation he started on purpose. Strictness is about the COLD
    # state; taking the window away would be a different product and he did not ask for one.
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 1000.0
    attention.note_directed(now=now)
    _streak(3, now + 1)
    v = attention.evaluate("y mañana?", now=now + 2)
    assert v.directed and v.reason == "active_window"


# ── the pre-roll: the words before the name reach the turn, and cost nothing else ──────────────────────
def test_the_words_before_the_name_are_glued_in_front_of_the_turn():
    # «muéstrame el tiempo» arrives from the browser's free recogniser while the paid tap is parked, and
    # the wake-word turn behind it reclaims the sentence whole.
    now = 2000.0
    attention.note_preroll("muéstrame el tiempo", now=now)
    assert attention.reclaim_ambient_tail("Johnny", now=now + 1) == "muéstrame el tiempo Johnny"


def test_a_preroll_is_not_an_unanswered_speech():
    # The distinction this function exists for. `note_ambient` counts one because a discard means nobody
    # answered him; a pre-roll is the first half of a turn that is ABOUT to be answered, and counting it
    # would let a spotted wake word inflate the very streak that opens a cold turn without one.
    now = 2000.0
    attention.note_preroll("muéstrame el tiempo", now=now)
    attention.note_preroll("y el tráfico", now=now)
    assert attention.unanswered_streak(now) == 0


def test_a_real_discard_still_counts_one():
    # The guard against "fixing" the line above by making `note_ambient` stop counting too.
    now = 2000.0
    attention.note_ambient("alguien hablando en la sala", now=now)
    assert attention.unanswered_streak(now) == 1


def test_an_empty_preroll_leaves_the_tail_alone():
    now = 2000.0
    attention.note_ambient("para la música", now=now)
    attention.note_preroll("   ", now=now)
    assert attention.reclaim_ambient_tail("Johnny", now=now + 1) == "para la música Johnny"


# ── an agent that ASKS has to say so, or its own question goes unheard ─────────────────────────────────
def _emits(fn) -> list:
    """Capture what `voice.observer.emit` is called with while `fn` runs."""
    from voice import observer
    seen, real = [], observer.emit

    def _spy(kind, label, **kw):
        seen.append((kind, label, kw.get("extra") or {}))
        return None

    observer.emit = _spy
    try:
        fn()
    finally:
        observer.emit = real
    return seen


def test_a_question_the_agent_asked_announces_its_own_window(monkeypatch):
    # THE DEADLOCK THIS CLOSES (V2-749). With the tap parked, the client learns a window is open from the
    # verdict on the next thing it HEARS — which needs audio, which needs the tap, which is closed. An
    # agent-initiated question («¿Sigo?») would therefore be asked into a microphone nobody opens. Same
    # family as 2026-09-10, where the agent asked and then refused to hear the answer.
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 3000.0
    attention.note_addressed_speech(now=now)
    attention.note_bot_speech(True, now=now)
    seen = _emits(lambda: attention.note_bot_speech(False, now=now + 4))
    directed = [e for e in seen if e[0] == "ambient" and e[2].get("reason") == "addressed_reply"]
    assert len(directed) == 1, f"the window has to be announced exactly once: {seen}"
    assert directed[0][2]["directed"] is True


def test_a_reply_inside_a_conversation_he_started_announces_nothing(monkeypatch):
    # The ring is already lit there. Re-announcing on every utterance would let the agent's own mouth hold
    # the tap open for as long as it keeps talking.
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 3000.0
    attention.note_directed(now=now)
    attention.note_bot_speech(True, now=now + 1)
    seen = _emits(lambda: attention.note_bot_speech(False, now=now + 3))
    assert not [e for e in seen if e[2].get("reason") == "addressed_reply"], seen


def test_the_arm_is_consumed_so_the_next_utterance_announces_nothing(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 3000.0
    attention.note_addressed_speech(now=now)
    attention.note_bot_speech(True, now=now)
    _emits(lambda: attention.note_bot_speech(False, now=now + 2))
    attention.note_bot_speech(True, now=now + 3)
    seen = _emits(lambda: attention.note_bot_speech(False, now=now + 5))
    assert not [e for e in seen if e[2].get("reason") == "addressed_reply"], seen
