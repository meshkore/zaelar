"""Filler text must never become the context fed to attention.evaluate_content() (V2-108 cont., 2026-08-17).

Bug found while auditing a live session (`memory/_data/zaelar.db`, sid 0db9bf42-...): `_last_spoken` is set to a
filler word ("Pues…", "Mmm…") whenever the lead-in filler speaks (V2-093), and `evaluate_content()`'s `context`
argument was reading that SAME field — so a real follow-up question asked right after a filler ("¿Cuántos
coches tengo?", and even the operator's own complaint "te acabo de hacer preguntas ahora") was judged with
"Se estaba haciendo: Pues…" as its only context and misclassified as ambient. Four turns were dropped in one live
session this way. `_last_reply` is the fix: it mirrors `_last_spoken` but is written ONLY from `send()`
(real model output), never from the filler path — this file locks that source-level invariant statically,
since exercising the full streaming turn requires the live LiveKit session machinery that this suite does not build.
"""
import re

from pathlib import Path

_SRC = Path(__file__).resolve().parents[4] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


def _text() -> str:
    return _SRC.read_text(encoding="utf-8")


def test_evaluate_content_reads_last_reply_not_last_spoken():
    src = _text()
    m = re.search(r"attention\.evaluate_content\(text, context=([\w.]+)\)", src)
    assert m, "evaluate_content(...) call site not found — did it move/change shape?"
    assert m.group(1) == "brain._last_reply", (
        "the directed-content judge must be given the last REAL reply, never `brain._last_spoken` "
        "(which a filler word overwrites and empties of topic)"
    )


def test_filler_path_never_writes_last_reply():
    # V2-122 (2026-08-17): the lead-in filler moved to its own module; V2-529 (2026-08-31) moved it again,
    # to the audio-in-the-reply-speech mechanism — the invariant travels with it.
    filler_src = Path(__file__).resolve().parents[4] / "voice" / "engine" / "speech" / "filler_audio.py"
    filler_body = filler_src.read_text(encoding="utf-8")
    assert "brain._last_spoken = phrase" in filler_body, "sanity: filler still updates anti-echo as designed"
    assert "_last_reply" not in filler_body, (
        "the filler must never touch `_last_reply` — it carries no topic, and evaluate_content() relies on "
        "`_last_reply` staying real-content-only"
    )


def test_a_real_reply_refreshes_the_conversation_window_and_kickoff_does_not():
    """2026-09-01 (session 701fcc1b): a narration longer than `window_s()` let the window expire mid-dialogue,
    landing the operator's answer on the cold-turn judge. `send()` — real model output only, on a turn that
    already passed the gate — refreshes the window per chunk; the kickoff is excluded for the same reason the
    gate call site writes down (a session starting mid-meeting must not open an initial gap)."""
    src = _text()
    i = src.find('brain._last_reply = "".join(spoken)')
    assert i > 0, "send()'s _last_reply write not found — did it move?"
    after = src[i:i + 800]
    assert "attention.note_directed()" in after, (
        "a real reply must refresh the attention window, or a long narration leaves the next answer cold"
    )
    guard = after[:after.index("attention.note_directed()")]
    assert "if not first_turn" in guard, "the kickoff must NOT open the window — deliberate, see the gate site"
