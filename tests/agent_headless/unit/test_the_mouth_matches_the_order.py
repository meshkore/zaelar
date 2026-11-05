"""What the engine SAYS while acting matches what was ordered (V2-572).

Measured session, 2026-09-03 20:10-20:52, the operator's engine — three shapes of the same incoherence:

  · «Cierra los mensajes» → the fast lane closed the card in 0.08 ms and said NOTHING («executed in
    silence», by design). The operator's words: *«when you tell him to close something or open something,
    he has to say 'ok, done'»*.
  · A close order that reaches the MODEL got covered with «Déjame ver…» — a thinking sound before an order
    to act reads as incomprehension.
  · «¿Tenemos alguna reserva en la agenda a algún restaurante?» → «Hecho.» — twice in one session. The repair that
    re-ran the model over that reply (and its empty-wait, mute-cover and continuity siblings) went in V2-851 F5 with
    every re-run after the main stream; what stays here is what the engine says while it acts.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

from pathlib import Path

import pytest

from voice.engine.core import langs
from voice.engine.speech import filler_audio

ENGINE = Path(__file__).resolve().parents[3]


# ── 1 · the cover phrase knows what kind of turn it covers ───────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "A ver, cierra los mensajes.",        # the literal utterance (leading interjection included)
    "cierra los contactos",
    "Enséñame mi lista de restaurantes favoritos.",
    "quita el temporizador",
    "close the messages",
    "vale, pon el reloj",
])
def test_an_action_order_is_covered_by_motion_not_thought(text):
    assert filler_audio.filler_kind(text) == "action"


@pytest.mark.parametrize("text", [
    "¿Tenemos alguna reserva en la agenda a algún restaurante?",   # a question thinks
    "¿Puedes cerrar los mensajes?",                                # question mark vetoes the action pool
    "Búscame si hay empresas de alquiler de catamaranes",          # a search takes real time — thinking fits
    "Me acabas de mostrar el widget de mensajería.",               # a statement
])
def test_everything_else_keeps_the_thinking_pool(text):
    assert filler_audio.filler_kind(text) == "neutral"


# ── 1b · V2-652: the order may live in the LAST sentence, and a data write is an action ──────────────────
# Measured live (session 7f77e2cc, 2026-09-10): «…Añade en la agenda mañana una cita» was covered with
# «Un momento, que lo busco…» — a searching promise over a write — because the imperative was judged on the
# whole utterance's FIRST word, and the operator's turns open with chatter, a statement, or the wake word.

@pytest.mark.parametrize("text", [
    # the literal measured utterances, verbatim:
    "Certificado para personas jurídicas, es lo que pedí. Johnny. Añade en la agenda mañana una cita",
    "Añade en la agenda mañana una cita a las once treinta en la agencia tributaria, "
    "que ya la he pedido yo a mano.",
    # complaint + explicit order: the ORDER wins the cover — motion, not «Pues…»
    "Pero en ningún caso te he dicho que añadieras nada a las cinco. Quítalo inmediatamente.",
    "Apúntame una reunión el jueves",
    "Anota que mañana como fuera",
    "Recuérdame llamar al fontanero",
    "Add a meeting tomorrow at noon",
])
def test_a_data_write_order_is_an_action_wherever_it_sits_in_the_turn(text):
    assert filler_audio.filler_kind(text) == "action"


@pytest.mark.parametrize("text", [
    # the measured complaints — a thinking cover here reads as not listening (the operator's own words:
    # «¿Qué tienes que buscar? Te he dicho que hagas una acción sobre la agenda.»)
    "¿Qué tienes que buscar? Te he dicho que hagas una acción sobre la agenda.",
    "Te he hecho una pregunta.",
    "Te acabo de pedir que borres la cita.",
])
def test_a_complaint_about_us_never_gets_a_thinking_cover(text):
    assert filler_audio.filler_kind(text) == "social"


def test_the_action_pool_promises_motion_and_each_pool_keeps_phrases_of_its_own():
    """V2-716 relaxed the DISJOINTNESS this asserted, and the reason belongs here rather than in a commit
    message. When the pools were sentences («Voy a mirarlo…» vs «Voy a ello…») no phrase could honestly
    serve two classes. Once the operator ruled them down to «vale», «sí», «un segundo», overlap is not a
    bug but the shape of the vocabulary: «Vale…» is a truthful receipt AND a truthful start of motion.

    What still has to hold is the thing disjointness was protecting — that the CLASS changes what is heard
    at least some of the time. A pool that is a subset of another makes the classifier inaudible, and that
    is what is asserted now."""
    for code in ("es", "en"):
        action = set(getattr(langs.spec(code), "fillers_action", ()) or ())
        thinking = set(getattr(langs.spec(code), "fillers", ()) or ())
        assert action, f"[{code}] no action fillers shipped"
        assert action - thinking, f"[{code}] the action pool says nothing the thinking pool does not"
        assert thinking - action, f"[{code}] the thinking pool says nothing the action pool does not"
        for _ in range(20):
            assert langs.pick_filler(kind="action", code=code) in action


def test_the_ack_exists_in_both_languages_and_varies():
    for code in ("es", "en"):
        pool = set(getattr(langs.spec(code), "acks", ()) or ())
        assert pool, f"[{code}] no acks shipped"
        last = langs.pick_ack(code=code)
        assert last in pool
        if len(pool) > 1:
            assert langs.pick_ack(last, code=code) != last, "anti-repetition: never the same ack twice"


def test_the_voice_arm_carries_the_utterance():
    """`filler_kind` runs at ARM time, so the provider must hand the text over — an arm without it silently
    degrades every action order back to «Déjame ver…»."""
    src = _vts.read(ENGINE / "voice/engine/llm/providers/nucleo.py")
    assert "_filler_audio.arm(brain, text" in src, "the provider arms the filler without the turn's text"


# ── 3 · the fast lane confirms out loud ──────────────────────────────────────────────────────────────────

def test_the_fast_lane_speaks_after_executing():
    """The ack comes AFTER the execute in the voice lane (it may never promise what did not happen)."""
    lane = (ENGINE / "voice/engine/llm/providers/fast_lane.py").read_text(encoding="utf-8")
    assert "pick_ack" in lane and "_speak_ack" in lane
    assert lane.index("execute(") < lane.index("await _speak_ack"), "the ack must follow the mutation"
    provider = _vts.read(ENGINE / "voice/engine/llm/providers/nucleo.py")
    assert "fast_lane.handled" in provider or "_fast_lane.handled" in provider, \
        "the voice provider no longer routes through the extracted fast lane"


def test_the_ack_never_sounds_when_the_lane_declines(monkeypatch):
    """Sensitivity: an executor decline (live work behind the widget, V2-567) falls through WHOLE — no ack,
    no bookkeeping, the model gets the turn."""
    import asyncio

    from voice.engine.llm.providers import fast_lane
    from nucleo import actionmap as _amap

    monkeypatch.setattr(_amap, "enabled", lambda: True)
    monkeypatch.setattr(_amap, "match", lambda text: {"id": 1, "action": {"do": "close_widget", "widget": "x"}})
    monkeypatch.setattr(_amap, "execute", lambda hit, emit, phrase="": False)   # the decline
    spoken: list[str] = []

    async def _spy(brain):
        spoken.append("!")
    monkeypatch.setattr(fast_lane, "_speak_ack", _spy)

    class _Brain:
        _acc = None
        _window: list = []

    handled = asyncio.run(fast_lane.handled(_Brain(), "cierra los resultados", lambda *a, **k: None,
                                            first_turn=False, t_entry=0.0, window_max=10))
    assert handled is False
    assert spoken == [], "the lane spoke an ack for an action that never happened"


def test_the_thinking_pool_is_a_receipt_and_never_a_machine_noise_or_a_verdict():
    """V2-642 banned the bare thinking sounds from OpenAI's realtime guide («Hmm…», «Let me think…», «One
    moment while I process…»), because our pool WAS that list and a sound promising nothing invites «¿a ver
    qué?» back. V2-716 (2026-09-17) found it had overshot in the other direction, and the operator named
    both halves of the correction himself:

        «quiero palabras más cortas, en plan one second, yes, checking, ok … te digo que abras una ventana
         y el sistema dice Good question, lo cual es totalmente absurdo».

    So «One sec…» and «Un segundo…» — banned by the old list — are now the target, and what stays banned is
    the two kinds that survived his complaint unchanged:

      · MACHINE NOISE. A sound that is audibly the machine thinking, with no content at all. «Mmm…»,
        «Hmm…», «Veamos…», «A ver…», «Déjame ver…». This is V2-642's finding and it is untouched: it is
        why the fix was shorter ACKS and not shorter grunts.
      · A VERDICT ON THE TURN. A cover is chosen before any model has read the sentence, so anything it
        says ABOUT that sentence is a guess that can be wrong — and was, out loud: «Good question…»
        answered «the one in Telegram», which was an answer to a question of OURS.
    """
    machine_noise = {"Mmm…", "Hmm…", "A ver…", "Veamos…", "Déjame ver…", "Un momentito…",
                     "Let me think…", "One moment while I process…", "Uhm…", "Eh…"}
    verdicts = {"Buena pregunta…", "Good question…", "Interesting…", "Interesante…",
                "Qué buena pregunta…", "That's a good one…"}
    for code in ("es", "en"):
        for field in ("fillers", "fillers_action", "fillers_social", "fillers_ack"):
            pool = set(getattr(langs.spec(code), field, ()) or ())
            assert pool, f"[{code}] empty {field} pool"
            assert not (pool & machine_noise), f"[{code}/{field}] machine noise returned: {pool & machine_noise}"
            assert not (pool & verdicts), f"[{code}/{field}] a verdict on the turn returned: {pool & verdicts}"
