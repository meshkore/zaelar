"""What the engine SAYS while acting matches what was ordered (V2-572).

Measured session, 2026-09-03 20:10-20:52, the operator's engine — three shapes of the same incoherence:

  · «Cierra los mensajes» → the fast lane closed the card in 0.08 ms and said NOTHING («executed in
    silence», by design). The operator's words: *«when you tell him to close something or open something,
    he has to say 'ok, done'»*.
  · A close order that reaches the MODEL got covered with «Déjame ver…» — a thinking sound before an order
    to act reads as incomprehension.
  · «¿Tenemos alguna reserva en la agenda a algún restaurante?» → «Hecho.» — twice in one session, and both
    times the operator had to protest («Te he hecho una pregunta», «Respóndeme a la pregunta») to get the
    actual answer. The guard automates exactly that recovery.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nucleo.flash import answer_guards
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


def test_the_action_pool_promises_motion_and_the_pools_do_not_mix():
    for code in ("es", "en"):
        action = set(getattr(langs.spec(code), "fillers_action", ()) or ())
        thinking = set(getattr(langs.spec(code), "fillers", ()) or ())
        assert action, f"[{code}] no action fillers shipped"
        assert not (action & thinking), f"[{code}] a phrase lives in both pools"
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
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "_filler_audio.arm(brain, text)" in src, "the provider arms the filler without the turn's text"


# ── 2 · a question is never answered with a bare ack ─────────────────────────────────────────────────────

@pytest.mark.parametrize("q,a", [
    ("¿Tenemos alguna reserva en la agenda a algún restaurante?", "Hecho."),          # live, 20:11
    ("Dime si has hecho alguna reserva efectiva. Para comer en un restaurante, en la agenda.", "Hecho."),  # 20:51
    ("¿Hay algo pendiente para mañana?", "Vale."),
    ("Tell me if there is any booking in the agenda", "Done."),
])
def test_the_live_failures_fire_the_guard(q, a):
    assert answer_guards.a_bare_ack_answers_a_question(q, a)


@pytest.mark.parametrize("q,a", [
    ("¿Puedes cerrar los mensajes?", "Hecho."),          # a polite ORDER — «Hecho.» answers it correctly
    ("Cierra los contactos.", "Hecho."),                 # not a question at all
    ("¿Tenemos alguna reserva?", "No, Ricardo, no tienes ninguna reserva."),   # a real answer
    ("¿Tenemos reservas?", "Hecho, no tienes ninguna."), # ack + content answers
    ("", "Hecho."),
])
def test_and_stays_out_of_turns_that_were_fine(q, a):
    assert not answer_guards.a_bare_ack_answers_a_question(q, a)


def test_both_channels_wire_the_repair():
    """V2-539's lesson yet again: a rule applied in one channel silently stops existing in the other. Both
    must consult the guard and compose the missing answer through `second_pass.bare_ack_repair`."""
    voice = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    for name, src in (("voice", voice), ("probe", probe)):
        assert "a_bare_ack_answers_a_question" in src, f"the {name} channel dropped the bare-ack guard"
        assert "bare_ack_repair" in src, f"the {name} channel detects but never repairs"


# ── 2b · V2-587: a question is not answered with an EMPTY WAIT ───────────────────────────────────────────
# Session 0e3a42d6 (2026-09-05): «¿Cuántos correos hay en mi bandeja?» → «Sigo con ello; te aviso en cuanto
# lo tenga.» with ZERO tools and ZERO tasks. Two reminders later a whisper repair finally spawned a worker;
# the session ended before any answer. «Sigo con ello» is honest WHEN something runs — which is why the
# guard takes the two liveness facts and stays out whenever either is true.

def test_the_measured_empty_wait_fires_the_guard():
    assert answer_guards.an_empty_wait_answers_a_question(
        "¿Cuántos correos hay en mi bandeja?", "Sigo con ello; te aviso en cuanto lo tenga.",
        acted=False, anything_running=False)


@pytest.mark.parametrize("acted,running", [(True, False), (False, True), (True, True)])
def test_an_honest_wait_over_real_work_stays_out(acted, running):
    """The counterweight: with a task alive (or this very turn having acted), the wait may be TRUE and
    repairing over it would contradict the state — the direction V2-531 paid for."""
    assert not answer_guards.an_empty_wait_answers_a_question(
        "¿Cuántos correos hay en mi bandeja?", "Sigo con ello; te aviso en cuanto lo tenga.",
        acted=acted, anything_running=running)


@pytest.mark.parametrize("q,a", [
    ("¿Cuántos correos hay?", "¿Los de hoy o todos los de la bandeja?"),   # a clarifying question ANSWERS
    ("¿Puedes cerrar los mensajes?", "Un momento."),                       # action verb → polite order
    ("¿Cuántos correos hay?", "Tienes 12 correos, 3 sin leer."),           # a real answer
    ("Ponme música tranquila", "Dame un momento."),                        # not an information question
    ("", "Sigo con ello."),
])
def test_and_the_empty_wait_guard_stays_out_of_fine_turns(q, a):
    assert not answer_guards.an_empty_wait_answers_a_question(q, a, acted=False, anything_running=False)


def test_both_channels_wire_the_empty_wait_repair():
    """Same wiring rule as its sibling above — and the liveness read must fail SAFE (unreadable counts as
    running), which both call sites write as `_running = True` in their except branch."""
    voice = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    for name, src in (("voice", voice), ("probe", probe)):
        assert "an_empty_wait_answers_a_question" in src, f"the {name} channel dropped the empty-wait guard"
        assert "empty_wait_repair" in src, f"the {name} channel detects but never repairs"
        assert "_running = True" in src, f"the {name} channel's liveness read no longer fails safe"


# ── 3 · the fast lane confirms out loud ──────────────────────────────────────────────────────────────────

def test_the_fast_lane_speaks_after_executing_and_the_probe_reply_carries_it():
    """The ack comes AFTER the execute in the voice lane (it may never promise what did not happen), and the
    probe's fast-lane reply carries the same ack for parity — a headless audit must see the confirmation the
    operator hears."""
    lane = (ENGINE / "voice/engine/llm/providers/fast_lane.py").read_text(encoding="utf-8")
    assert "pick_ack" in lane and "_speak_ack" in lane
    assert lane.index("execute(") < lane.index("await _speak_ack"), "the ack must follow the mutation"
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "pick_ack" in probe, "the probe's fast lane answers silently again"
    provider = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
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
