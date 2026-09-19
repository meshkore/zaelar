#
# test_a_stop_keeps_the_rest_of_the_order.py — a hard stop ends the turn but must not eat the REST of
# the sentence (voice-session-fixes #T-fix05; session 6d19df41).
#
# Measured live: «No. So no. Stop it. Okay. Show me the the WhatsApp messages.» produced
# `✋ interrupción dura atendida` and nothing else — the WhatsApp order died in silence, the operator
# repeated it («Why didn't you get this in the first place?»), and the model blamed the Carwow email
# instead. V2-688 fixed the same hole for the close branch; the stop branch is its twin.
#
import asyncio

from nucleo.flash import hard_turn
from voice import attention


def _run(text, hard):
    seen = []

    def emit(kind, label, *args, **kwargs):
        seen.append((kind, label, kwargs.get("text", "")))

    return asyncio.run(hard_turn.handle(text, hard, emit)), seen


def test_session_replay_stop_keeps_the_whatsapp_order():
    rest, seen = _run("No. So no. Stop it. Okay. Show me the the WhatsApp messages.", "stop")
    assert rest == "Show me the the WhatsApp messages"
    assert seen[0][1] == "✋ interrupción dura atendida"   # the stop itself is still honoured first
    assert any("sigue el resto" in label for _, label, _ in seen)


def test_bare_stop_still_ends_the_turn():
    for txt in ("stop", "Stop it.", "para ya", "stop, please", "No. Stop it. Okay."):
        rest, _ = _run(txt, "stop")
        assert rest is None, txt


def test_stop_with_an_object_never_reaches_here():
    # «para el vídeo» names a thing: hard_interrupt says None, so handle() is never called with it.
    assert attention.hard_interrupt("para el vídeo") is None
    assert attention.stop_remainder("para el vídeo") == ""


def test_stop_remainder_needs_a_real_order():
    assert attention.stop_remainder("stop it") == ""
    assert attention.stop_remainder("No. So no. Stop it. Okay.") == ""
    assert attention.stop_remainder("Stop it. Open my WhatsApp.") == "Open my WhatsApp"
