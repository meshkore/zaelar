"""V2-655 — the deafness: if the agent talks TO you, it listens to you.

Measured 2026-09-10, session 85eec898. The window opened at 16:31:55 sized 15 s and expired at 16:32:10
while the agent was still working. It then spoke for 90 seconds — a worker delivery ending in «¿Sigo?» —
and the operator's answer, two seconds after its last word, was classified `🙉 ambiente`. Sixteen of his
turns went that way in a row, including «¿Qué te ha pasado? ¿Te has colgado?» and «Hola otra vez ×3».

The cause was structural, not a classifier miss: `note_bot_speech` could only HOLD a window somebody else
had opened, so the agent's own mouth could never grant attention and the silence clock ran down during its
own monologue.

The operator's rule, verbatim: «el sonido ambiente no interrumpe para nada los contadores». These cases
pin both halves of it — what the agent's speech does to the window, and what the room's noise must not.
"""
import pytest

from voice import attention


@pytest.fixture(autouse=True)
def _fresh():
    attention.reset()
    yield
    attention.reset()


def _smart(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    monkeypatch.delenv("ZAELAR_ATTENTION_WINDOW", raising=False)


# ── the measured incident, replayed ───────────────────────────────────────────────────────────────────────

def test_the_window_does_not_run_down_while_the_agent_itself_is_talking(monkeypatch):
    """THE incident. A 90-second delivery over a window that had already closed, and the answer two seconds
    after its last word. Before this, that answer was room noise."""
    _smart(monkeypatch)
    t = 1000.0
    attention.note_directed(now=t)                       # 16:31:55 — the wake word
    assert not attention.evaluate("y esto?", now=t + 60).directed, "the window really had expired"

    attention.note_addressed_speech(now=t + 54)          # 16:32:49 — the worker delivery is about to speak
    attention.note_bot_speech(True, now=t + 54)
    attention.note_bot_speech(False, now=t + 144)        # 16:33:18 — 90 seconds later, its last word
    v = attention.evaluate("Escúchame, en primer lugar yo tenía el micrófono apagado", now=t + 146)
    assert v.directed and v.reason == "active_window", (
        "the agent asked him a question and then refused to hear the answer")


def test_the_clock_starts_at_the_LAST_word_not_the_first(monkeypatch):
    """Anchoring when the delivery STARTS is the bug wearing a fix's clothes: a long delivery would eat its
    own window all over again."""
    _smart(monkeypatch)
    t = 1000.0
    attention.note_addressed_speech(now=t)
    attention.note_bot_speech(True, now=t)
    attention.note_bot_speech(False, now=t + 90)
    assert attention.evaluate("vale, sigue", now=t + 92).directed
    assert not attention.evaluate("vale, sigue", now=t + 90 + 40).directed, (
        "…and it is a window, not an open door: real operator silence still closes it")


def test_the_agent_is_heard_while_it_is_still_speaking(monkeypatch):
    """A barge-in over an addressed delivery: the hold is live from the first word, so cutting it off works
    without a wake word."""
    _smart(monkeypatch)
    t = 1000.0
    attention.note_addressed_speech(now=t)
    attention.note_bot_speech(True, now=t)
    assert attention.evaluate("no, para, eso no", now=t + 45).directed


# ── the counterweight: the kickoff, and the arm's own limits ──────────────────────────────────────────────

def test_the_KICKOFF_still_opens_nothing(monkeypatch):
    """The written decision (the gate call site in the voice provider) is about the GREETING: a session
    starting mid-meeting must not open with a free window. Unarmed speech still only holds."""
    _smart(monkeypatch)
    t = 1000.0
    attention.note_bot_speech(True, now=t)
    attention.note_bot_speech(False, now=t + 5)
    v = attention.evaluate("qué frío hace hoy", now=t + 6)
    assert not v.directed and v.reason == "ambient"


def test_an_arm_licenses_ONE_utterance_and_then_is_gone(monkeypatch):
    """Otherwise the next thing the agent says — a kickoff after a reconnect, a filler — inherits a window
    it was never granted."""
    _smart(monkeypatch)
    t = 1000.0
    attention.note_addressed_speech(now=t)
    attention.note_bot_speech(True, now=t)
    attention.note_bot_speech(False, now=t + 3)
    attention.reset()
    attention.note_bot_speech(True, now=t + 100)
    attention.note_bot_speech(False, now=t + 103)
    assert not attention.evaluate("y ahora qué", now=t + 104).directed


def test_an_arm_that_never_became_speech_expires(monkeypatch):
    """A delivery that degraded to a written note (no live speaker) must not leave a loaded window behind for
    whatever speaks next."""
    _smart(monkeypatch)
    t = 1000.0
    attention.note_addressed_speech(now=t)
    attention.note_bot_speech(True, now=t + attention._ADDRESSED_ARM_TTL_S + 5)
    attention.note_bot_speech(False, now=t + attention._ADDRESSED_ARM_TTL_S + 8)
    assert not attention.evaluate("hola?", now=t + attention._ADDRESSED_ARM_TTL_S + 9).directed


def test_reset_clears_the_arm(monkeypatch):
    _smart(monkeypatch)
    attention.note_addressed_speech(now=1000.0)
    attention.reset()
    attention.note_bot_speech(True, now=1001.0)
    attention.note_bot_speech(False, now=1002.0)
    assert not attention.evaluate("sigo hablando", now=1003.0).directed


# ── window_open(): what the client paints the «te escucho» ring from ──────────────────────────────────────

def test_window_open_reports_the_engines_own_truth(monkeypatch):
    _smart(monkeypatch)
    t = 1000.0
    assert attention.window_open(now=t) is False
    attention.note_directed(now=t)
    assert attention.window_open(now=t + 1) is True
    assert attention.window_open(now=t + 100) is False
    attention.note_addressed_speech(now=t + 100)
    attention.note_bot_speech(True, now=t + 100)
    assert attention.window_open(now=t + 160) is True, "a live hold IS an open window, however long it runs"


def test_window_open_answers_each_mode_in_its_own_terms(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")
    assert attention.window_open() is True
    monkeypatch.setenv("ZAELAR_ATTENTION", "wakeword")
    attention.note_directed()
    assert attention.window_open() is False, "wakeword mode grants no window, ever"
    monkeypatch.setenv("ZAELAR_ATTENTION", "ptt")
    attention.set_ptt(False)
    assert attention.window_open() is False
    attention.set_ptt(True)
    assert attention.window_open() is True


# ── the wiring, structural (comment-stripped: a comment about the fix is not the fix) ────────────────────

def test_a_proactive_delivery_arms_the_window_around_its_own_playout():
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "voice/proactive.py"
    text = re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))
    assert "opens_window: bool = True" in text, (
        "a proactive delivery is addressed to the operator BY DEFAULT — that is what it is")
    arm, say = text.find("note_addressed_speech()"), text.find("_speaker(spoken)")
    assert arm >= 0 and say > arm, "the arm has to be set before the first word is spoken"


def test_the_ambient_verdict_carries_the_window_so_the_client_can_keep_the_ring_honest():
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/attention_turn.py"
    text = re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))
    assert 'window = {"window_s": attention.window_s(), "window_open": attention.window_open()}' in text, (
        "without `window_open` the client cannot tell «the window closed» from «somebody coughed», and it "
        "darkened the ring for both — ambient sound must not touch the counters")
    for face in ('"🙉 ambiente', '"👂 dirigido'):
        i = text.find(face)
        assert i >= 0 and "**window" in text[i:i + 300], (
            f"{face} has to carry it too: BOTH verdicts feed the same ring, and one of them lying is what "
            f"made the ring contradict the engine")


def test_the_relay_no_longer_opens_the_window_before_its_own_TTS():
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "nucleo/loop.py"
    text = re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))
    assert "attention.note_directed()" not in text, (
        "anchoring before a 10-20s relayed question let it consume its own window; the delivery path arms "
        "and anchors at the last word now")
