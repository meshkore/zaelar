"""Speech that keeps coming while nobody answers is him talking to a wall — in BOTH modes (V2-743).

`note_ambient` has written every discard into `_state["unanswered"]` since fix01, and the hatch that reads
it — «nobody judges the third unanswered speech» — was installed inside `evaluate_content`, after its
`always` guard. `evaluate_content` starts by returning `evaluate(text)` for anything that is not `always`,
so in `smart` the streak was recorded on every single discard and read by nobody: live instrumentation
wired to nothing.

`smart` is the operator's mode. Session bcd4aba1, 2026-09-21 — six discards, every one of them him, alone,
talking straight at the agent, every one already carrying `framed: True` in its own event:

    2845.01  «Vale, ¿ahora me escuchas? No.»
    2867.23  «A ver, quiero que me muestres la agenda.»
    2959.64  «Bueno, yo las sigo viendo en el widget»
    2960.13  «Bueno, yo las sigo viendo en el widget de la agenda. ¿Qué le pasa?»
    2970.23  «¿Por qué no transcribes el audio que estoy dictando?»
    2974.64  «¿Hola?»

The last four are consecutive and they land right after the agent claimed a deletion was done and went
quiet — so his complaint about the false «done» was swallowed by the same 5 s timer, and he finished by
asking an empty room whether it could hear him.

WHAT THIS DOES NOT CHANGE, and must not: the 5 s smart window is HIS rule (2026-09-10, «ninguna pausa
puede pasar de 5 segundos») and it is untouched. `wakeword` mode is untouched too — there the whole point
is that only the name opens a turn, and opening it on repetition would delete the mode. What changes is
that expiring one window three times over stops counting as a verdict.

⚠️ REVERSED IN `smart` THE NEXT DAY (V2-749, 2026-09-22) — and the argument that reversed it is the one
written three lines above about `wakeword`. The 🤖 button on the orb is labelled «Modo palabra de
activación» and it sets `smart`, so from where the operator stands `smart` IS the wake-word mode, and
«opening it on repetition would delete the mode» applies to it word for word. Measured in session
48394dd0: with the 🤖 on, the agent asked «¿Cómo te llamas?», he answered «Me llamo Paco.» three times,
and the third was handled as `unanswered_repeat` with no wake word anywhere in the session — «se ha
puesto a escuchar pero sin que sonara la palabra de activación… hay que ser estrictos».

The hatch is NOT deleted: it stays exactly where it was measured to be needed, in `always`, which is the
mode where he has no word to come back with and repeating himself is the only signal left. The two
sections below hold both halves, and the incident this file was written for is kept verbatim — it is
still the thing that has to be weighed if anyone reverses this back. Gate:
`attention._has_wake_recovery()`; the new file is `test_the_word_is_the_only_way_in.py` (node 8.15).
"""
from __future__ import annotations

import pytest

from voice import attention


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    attention.reset()
    attention.set_directed_judge(None)
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    yield
    attention.reset()
    attention.set_directed_judge(None)   # V2-749: an injected judge that outlives its test judges the next one


#: His four consecutive discards, verbatim from the session.
HIS_STREAK = [
    "Bueno, yo las sigo viendo en el widget",
    "Bueno, yo las sigo viendo en el widget de la agenda. ¿Qué le pasa?",
    "¿Por qué no transcribes el audio que estoy dictando?",
    "¿Hola?",
]


def test_the_first_cold_turn_is_still_ambient():
    """Nothing is opened on one sentence — a single line out of the window really can be the room."""
    assert attention.evaluate(HIS_STREAK[0], now=1000.0).directed is False


def test_the_streak_is_COUNTED_in_smart_mode():
    attention.note_ambient(HIS_STREAK[0], now=1000.0)
    attention.note_ambient(HIS_STREAK[1], now=1001.0)
    assert attention.unanswered_streak(now=1002.0) == 2


async def _deaf_judge(_text, _context):
    """The coin-flip that kept saying «room noise» to a man talking straight at it. Injected so the replay
    measures the HATCH and never the network — and so a missing API key cannot fail-open this green."""
    return False


def test_the_THIRD_speech_in_a_row_is_answered_in_ALWAYS(monkeypatch):
    """The line of the defect, in the mode that kept it (V2-749). `always` has no wake word, so repeating
    himself is the only way he can insist and the hatch is the only thing that hears it."""
    import asyncio
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")
    attention.set_directed_judge(_deaf_judge)
    attention.note_ambient(HIS_STREAK[0], now=1000.0)
    attention.note_ambient(HIS_STREAK[1], now=1001.0)
    v = asyncio.run(attention.evaluate_content(HIS_STREAK[2], context="Zaelar dijo algo", now=1002.0))
    assert v.directed is True
    assert v.reason == "unanswered_repeat"


def test_in_SMART_the_third_speech_waits_for_the_name(monkeypatch):
    """V2-749 — the reversal, asserted where it happens rather than left as a deleted test. The mode the
    🤖 button selects promises silence until its name; a hatch that opens a cold turn without one is the
    back door he measured on 2026-09-22. His recovery is two syllables, and the tooltip now says so."""
    attention.note_ambient(HIS_STREAK[0], now=1000.0)
    attention.note_ambient(HIS_STREAK[1], now=1001.0)
    v = attention.evaluate(HIS_STREAK[2], now=1002.0)
    assert v.directed is False and v.reason == "ambient"
    # …and the word still works, which is what makes the strictness liveable rather than deafness.
    assert attention.evaluate("Zaelar, " + HIS_STREAK[2], now=1002.0).reason == "wakeword"


def test_his_whole_session_would_have_been_heard_in_always(monkeypatch):
    """Replayed at the real offsets: the first two are discarded, and from the third on he is answered.
    Kept as the record of what the hatch buys — if anyone ever takes it out of `always` too, this is the
    session that has to be weighed against the saving."""
    import asyncio
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")
    attention.set_directed_judge(_deaf_judge)
    at = {HIS_STREAK[0]: 2959.64, HIS_STREAK[1]: 2960.13,
          HIS_STREAK[2]: 2970.23, HIS_STREAK[3]: 2974.64}
    heard = []
    for line in HIS_STREAK:
        if asyncio.run(attention.evaluate_content(line, context="Zaelar dijo algo", now=at[line])).directed:
            heard.append(line)
        else:
            attention.note_ambient(line, now=at[line])
    assert heard == HIS_STREAK[2:], f"he was heard on {heard}"


def test_a_stray_sentence_from_long_ago_opens_NOTHING():
    """Bounded exactly as the `always` copy is: outside `_UNANSWERED_WITHIN_S` the streak is not a streak."""
    attention.note_ambient(HIS_STREAK[0], now=1000.0)
    attention.note_ambient(HIS_STREAK[1], now=1001.0)
    assert attention.evaluate(HIS_STREAK[2], now=1000.0 + attention._UNANSWERED_WITHIN_S + 5).directed is False


def test_an_ANSWERED_turn_clears_the_streak():
    """`note_directed` is what a handled turn calls — being heard once means he is not talking to a wall."""
    attention.note_ambient(HIS_STREAK[0], now=1000.0)
    attention.note_ambient(HIS_STREAK[1], now=1001.0)
    attention.note_directed(now=1001.5)
    assert attention.unanswered_streak(now=1002.0) == 0
    # …and the next cold turn is ambient again, which is what «cleared» has to MEAN: counting zero while
    # the hatch still fires would leave the streak permanently open after one handled turn.
    assert attention.evaluate(HIS_STREAK[2], now=1030.0).directed is False


def test_an_OPEN_window_still_wins_without_consulting_the_streak():
    """The cheap path stays the cheap path: inside the window the turn is directed, full stop (V2-531)."""
    attention.note_directed(now=1000.0)
    v = attention.evaluate("y ahora ponme la agenda", now=1001.0)
    assert v.directed is True and v.reason == "active_window"


def test_WAKEWORD_mode_is_untouched(monkeypatch):
    """There the mode IS «only when you say my name», and a streak hatch would delete it."""
    monkeypatch.setenv("ZAELAR_ATTENTION", "wakeword")
    attention.note_ambient(HIS_STREAK[0], now=1000.0)
    attention.note_ambient(HIS_STREAK[1], now=1001.0)
    assert attention.evaluate(HIS_STREAK[2], now=1002.0).directed is False


def test_PTT_mode_is_untouched(monkeypatch):
    """Push-to-talk means the BUTTON is the verdict; nothing else may stand in for his thumb."""
    monkeypatch.setenv("ZAELAR_ATTENTION", "ptt")
    attention.set_ptt(False)
    attention.note_ambient(HIS_STREAK[0], now=1000.0)
    attention.note_ambient(HIS_STREAK[1], now=1001.0)
    assert attention.evaluate(HIS_STREAK[2], now=1002.0).directed is False


def test_the_smart_window_is_STILL_five_seconds(monkeypatch):
    """His own rule (2026-09-10), and this batch does not widen it — the fix is the streak, never the timer.

    Both constants, not just `window_s()`: the ceiling and the default are separate knobs and raising the
    CEILING alone leaves `window_s()` reading 5.0, so the obvious assertion stayed green over a mutation
    that had re-opened a 30 s window to every stored override. (Caught by its own disarm.)"""
    monkeypatch.delenv("ZAELAR_ATTENTION_WINDOW", raising=False)
    assert attention.window_s() == 5.0
    assert attention._SMART_WINDOW_S == 5.0
    assert attention._SMART_WINDOW_MAX_S == 5.0


def test_evaluate_stays_PURE():
    """Its docstring promises it does not mutate, and the hatch reads state that a caller writes."""
    attention.note_ambient(HIS_STREAK[0], now=1000.0)
    attention.note_ambient(HIS_STREAK[1], now=1001.0)
    before = attention.unanswered_streak(now=1002.0)
    attention.evaluate(HIS_STREAK[2], now=1002.0)
    assert attention.unanswered_streak(now=1002.0) == before
