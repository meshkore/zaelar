"""V2-220 — a proactive delivery died in the panel whenever there was no voice session.

`brain_notes.push` lived INSIDE `if speak and _speaker is not None`, so without a live speaker `notify()` did
exactly one thing: emit to observability. On the TEXT channel — what the use-case harness drives, and what a
chat-only operator uses — that is EVERY proactive delivery there is:

  · the loop's stall notice (`worker.stuck`, V2-073),
  · a worker finishing (`session.py::_finish`),
  · the messaging connector, Architect.

The harness kept measuring `stuck/nudge` firing in the events while the turn went on saying «sigo con ello»,
and reported them as two problems. They were one: the mechanism fired and had nowhere to arrive.

Same shape as V2-215 one layer up — there the browser task recorded a wall on three surfaces the operator has
to be LOOKING at; here the notice reached the panel and stopped. The remedy is the same seam, because it is the
only one that works on both channels.
"""
import asyncio

import pytest

from voice import brain_notes, proactive


@pytest.fixture(autouse=True)
def _clean():
    brain_notes.drain()
    proactive.clear_speaker()
    yield
    brain_notes.drain()
    proactive.clear_speaker()


def _notify(**kw):
    asyncio.run(proactive.notify("Navegador", "La búsqueda lleva 6 minutos sin avanzar.", **kw))
    return brain_notes.drain()


def test_with_NO_voice_session_it_reaches_the_conversation():
    notes = _notify()
    assert len(notes) == 1, "el aviso se quedó en el panel"
    assert "6 minutos" in notes[0]


def test_the_note_is_an_INSTRUCTION_not_the_bare_phrase():
    """V2-214's lesson, applied here: the note's reader is the AGENT at a later moment, so handing it prose
    reads as something to FILE rather than something to say."""
    n = _notify()[0]
    assert n.startswith("[SISTEMA]")
    assert "Díselo" in n and "no lo sabe" in n


def test_with_a_LIVE_voice_session_it_does_NOT_also_push_a_note():
    """Sensitivity, and the one that matters: a note on top of the spoken delivery is the operator hearing the
    same thing twice, which is how a fix for silence becomes a fix for nothing."""
    said = []
    proactive.register_speaker(lambda t: said.append(t))
    notes = _notify()
    assert said, "no llegó a hablarse"
    assert notes == [], "se dijo Y se apuntó: entrega doble"


def test_speak_False_still_reaches_the_conversation():
    """A caller that does not want VOICE has not said it does not want the operator to know. With a speaker
    registered and `speak=False` the old code delivered nowhere at all."""
    proactive.register_speaker(lambda t: None)
    assert len(_notify(speak=False)) == 1


def test_an_empty_message_says_nothing():
    asyncio.run(proactive.notify("Navegador", "   "))
    assert brain_notes.drain() == []


def test_a_broken_mailbox_never_raises_into_the_caller():
    """`notify` is called from the loop and from connectors; its contract is best-effort. A mailbox that blows
    up must not take the pulse down with it."""
    import voice.brain_notes as bn
    real = bn.push
    bn.push = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        asyncio.run(proactive.notify("Navegador", "algo"))   # no debe lanzar
    finally:
        bn.push = real


def test_the_busy_conversation_fallback_is_UNTOUCHED():
    """The OTHER fallback (voice live but no quiet gap) predates this and covers a different case. Verifying it
    still fires stops this change from quietly replacing one delivery path with the other."""
    said = []
    proactive.register_speaker(lambda t: said.append(t))
    real = proactive._wait_for_quiet
    # `timeout=None` since the delivery queue (2026-08-31): notify passes the REMAINING budget explicitly, so a
    # replacement that takes no argument raises TypeError inside the try and the note never gets pushed — this
    # guard would then fail for plumbing reasons while the behaviour it protects (busy → note, never speak over)
    # is intact.
    proactive._wait_for_quiet = lambda timeout=None: asyncio.sleep(0, result=False)
    try:
        notes = _notify()
    finally:
        proactive._wait_for_quiet = real
    assert said == [], "habló encima del operador"
    assert len(notes) == 1 and "Entrega proactiva pendiente" in notes[0]
