#
# test_a_health_notice_never_opens_the_door.py — V2-768. In wake-word mode, nothing the agent says on its own
# about its own health may let the room in — and when something DID let the room in, the agent says what.
#
# THE MEASUREMENT. Session c20ffd8e (2026-09-25), wake-word mode, the operator on the phone with somebody else.
# For seven minutes every sentence was correctly discarded as ambient. Then the LiveKit worker stalled
# (`job executor is unresponsive` ×3), `nucleo/homeostasis.py` could not recycle it with a voice live and SAID
# so aloud — «El motor LiveKit se está atascando… si notas cortes, dime y lo reinicio» — through
# `proactive.notify`, whose deliveries open the reply window (V2-655). His next sentence, «Yo no estoy hablando
# contigo», landed in it and ran as an order; every reply re-opened the window and the chain lasted until he
# pressed ⏻, swallowing the end of his phone call. Asked «¿por qué me has interrumpido?» the agent answered
# «porque oí tu nombre… me activa la palabra clave» — nobody had said the name. His words:
#
#   «estaba activada la word activation… el sistema no tendría que haberse puesto a escuchar nada… yo en
#    ningún momento he dicho la palabra clave».
#
import asyncio
from pathlib import Path

import pytest

from voice import attention, attention_opening

ENGINE = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    attention.reset()
    attention_opening.reset()
    attention.set_directed_judge(None)
    yield
    attention.reset()
    attention_opening.reset()


# ── the notice stays on the screen ────────────────────────────────────────────────────────────────────────
def test_a_health_alert_is_shown_and_never_spoken(monkeypatch):
    from nucleo import homeostasis
    from voice import observer, proactive
    spoken, shown = [], []

    async def _notify(*a, **kw):
        spoken.append((a, kw))
    monkeypatch.setattr(proactive, "notify", _notify)
    monkeypatch.setattr(observer, "emit", lambda kind, label="", **kw: shown.append((kind, label, kw)))
    monkeypatch.setattr(homeostasis, "_alerted", set())
    asyncio.run(homeostasis._alert("lk_degraded", "Motor de voz degradado", "El motor LiveKit se está atascando."))
    assert not spoken, f"a health notice went through the delivery path that speaks and opens the window: {spoken}"
    assert [s for s in shown if s[0] == "homeostasis" and "atascando" in s[2].get("text", "")], (
        f"the notice must still reach the chat and the panel: {shown}")


def test_a_health_alert_opens_no_window(monkeypatch):
    """The whole chain, end to end in the attention module: the alert fires, the agent's mouth moves for some
    other reason, and his next cold sentence is still ambient."""
    from nucleo import homeostasis
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    monkeypatch.setattr(homeostasis, "_alerted", set())
    asyncio.run(homeostasis._alert("lk_degraded", "Motor de voz degradado", "Se está atascando."))
    now = 5000.0
    assert attention.evaluate("Yo no estoy hablando contigo", now=now).directed is False


# ── when a window WAS opened, the agent knows by what ─────────────────────────────────────────────────────
def test_its_own_delivery_is_named_as_the_opener(monkeypatch):
    """Through the real delivery: a proactive message with a live speaker records itself as the opener."""
    from voice import brain_notes, proactive
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    proactive._reset_queue_for_tests()
    said = []

    async def _speaker(text):
        said.append(text)
    proactive.register_speaker(_speaker)
    try:
        asyncio.run(proactive.notify("zaelar", "Tu encargo de la farmacia está listo."))
    finally:
        proactive.clear_speaker()
        brain_notes.drain()
        proactive._reset_queue_for_tests()
    assert said, "the delivery never reached the speaker — the test measured nothing"
    why = attention_opening.why_listening()
    assert "la abriste TÚ" in why and "farmacia" in why and "NO oíste tu nombre" in why, why


def test_the_wake_word_is_named_as_the_opener():
    from voice.engine.llm.providers import attention_turn
    ok, _, _ = asyncio.run(attention_turn.judge("Zaelar, pon música", context="", emit=lambda *a, **k: None))
    assert ok
    assert attention_opening.why_listening().startswith("la abrió él diciendo tu nombre"), attention_opening.why_listening()


def test_a_turn_inside_the_window_does_not_rewrite_the_opener():
    import time
    from voice.engine.llm.providers import attention_turn
    now = time.time()                       # the judge reads the real clock
    attention_opening.note("addressed", "¿Sigo?", now=now)
    attention.note_addressed_speech(now=now)
    attention.note_bot_speech(True, now=now)
    attention.note_bot_speech(False, now=now + 1)
    ok, _, _ = asyncio.run(attention_turn.judge("Yo no estoy hablando contigo", context="",
                                                emit=lambda *a, **k: None))
    assert ok, "inside the reply window the turn is directed — that part is V2-655 and stays"
    assert "la abriste TÚ" in attention_opening.why_listening(), attention_opening.why_listening()


def test_nothing_recent_says_nothing():
    assert attention_opening.why_listening() == ""
    attention_opening.note("wakeword", "Johnny", now=1000.0)
    assert attention_opening.why_listening(now=1000.0 + 3600) == "", "a stale opener must not explain today's turn"


def test_the_prompt_carries_the_opener_in_wake_word_mode(monkeypatch):
    from config import settings
    from nucleo.flash import style_directive
    monkeypatch.setattr(settings, "get", lambda k, d=None: "smart" if k == "attention_mode" else d)
    assert not [ln for ln in style_directive.prompt_lines({}) if "POR QUÉ ESTÁS EN CONVERSACIÓN" in ln]
    attention_opening.note("addressed", "El motor se está atascando.")
    lines = [ln for ln in style_directive.prompt_lines({}) if "POR QUÉ ESTÁS EN CONVERSACIÓN" in ln]
    assert lines and "atascando" in lines[0] and "nunca inventes" in lines[0], lines
