"""
test_lead_in.py — the WAIT FILLER must SOUND while waiting (V2-093, 2026-08-14).

The filler has existed since 2026-07-19 to cover the model's TTFT with a “Mmm…” / “Let me see…”. Auditing session
b70a45d0 showed that **it had not played even once**: 48 fillers generated, 0 heard in time, 50 seconds of
`bot_speech: idle` with THREE pending, and all 11 spoken responses starting with their filler (“Let me see… Yes,
I heard you”). Meanwhile, the operator said “did you hear me?” and “it seems you've gone stupid” — to an agent
that was working and had three generated, silent waiting phrases.

The cause was not the filler: it was HOW it traveled. It was pushed as a `ChatChunk` into the response stream, and
that stream passes through LiveKit's sentence tokenizer (`BufferedSentenceStream`), which **only delivers a segment
when it has TWO**: it emits the first and keeps the last as context. A standalone filler does not even become a
segment (it ends in “…” which is not in the sentence-end regex `[.!?。！？]`, and does not pass `min_sentence_len=20`),
so it remains in the buffer until the real response arrives — and then comes out STUCK to it.

The tests below (1) reproduce that exact sticking, which must never happen again, and (2) pin down the
out-of-band seam of the proactive channel.

V2-529 (2026-08-31): the FILLER no longer uses out-of-band `say` — LiveKit's scheduler authorized it
BEHIND the response in progress (always late, as measured live). Today it is audio INSIDE the response's
speech (`voice/engine/speech/filler_audio.py`, tests in `test_filler_audio.py`). The ephemeral seam of
proactive is retained as a seam; the tokenizer tests above still document why the filler's TEXT cannot travel
through the stream either.
"""
from __future__ import annotations

import pytest

from voice.engine.core import langs


def _pushed(*chunks: str) -> list[str]:
    """Segments that LiveKit's tokenizer DELIVERS TO TTS after pushing `chunks`, WITHOUT closing the stream — which is
    the only situation that matters: while the turn is still alive, nobody flushes.

    It runs INSIDE an `asyncio.run`: the LiveKit channel is built with `asyncio.get_event_loop()`, which crashes if
    the thread has no current loop — and it is enough for another suite test to have closed its loop for this to fail
    only when run together (that happened when it was added: green alone, red in the suite)."""
    import asyncio

    async def _go():
        from livekit.agents.tokenize import basic
        st = basic.SentenceTokenizer().stream()
        for c in chunks:
            st.push_text(c)
        out = []
        try:
            while True:
                out.append(st._event_ch.recv_nowait().token)
        except Exception:
            pass
        return out

    return asyncio.run(_go())


REPLY = "Sí, te he oído y vacío la agenda entera. Ya está todo limpio del todo. "


@pytest.mark.parametrize("code", ["es", "en"])
def test_ningun_relleno_sale_solo_por_el_stream(code):
    """No filler in any language is delivered by itself: this is THE reason the out-of-band path is needed. If this
    starts failing (LiveKit changes the tokenizer, or someone adds a filler with a period and more than 20 chars),
    `say` is no longer mandatory — until then, putting it in the stream guarantees that it will not play."""
    fillers = langs.spec(code).fillers
    assert fillers, f"el idioma {code} no tiene rellenos"
    for f in fillers:
        assert _pushed(f + " ") == [], f"{f!r} sí saldría solo: revisa si el camino fuera de banda sigue haciendo falta"


def test_por_el_stream_el_relleno_sale_PEGADO_a_la_respuesta():
    """The EXACT SYMPTOM from session b70a45d0, reproduced. What the operator heard at 98.8 s was a single
    utterance: “Let me see… Yes, I heard you”. The filler covered nothing — it traveled in a buffer for 56 seconds."""
    segs = _pushed("Déjame que mire… ", REPLY)
    assert segs, "el arnés no mide nada: revísalo antes de fiarte del resto"
    assert segs[0].startswith("Déjame que mire…"), segs[0]
    assert "te he oído" in segs[0], "esto es lo que hay que evitar: relleno y respuesta en la MISMA locución"


def test_la_respuesta_sola_si_se_entrega():
    """Positive control: the harness measures something real. A two-sentence response does release the first one."""
    segs = _pushed(REPLY)
    assert segs and "te he oído" in segs[0]


def test_hay_costura_fuera_de_banda_y_dice_la_verdad():
    """`proactive.speaker()` is how the filler reaches TTS without going through the aggregator. None when there is no
    live session — in that case the provider retains the old path, because without TTS there is nothing to cover."""
    from voice import proactive

    assert proactive.speaker() is None, "sin sesión registrada no puede haber hablador"
    dicho = []

    async def _say(text):
        dicho.append(text)

    proactive.register_speaker(_say)
    try:
        assert proactive.speaker() is _say
        assert proactive.has_voice() is True
    finally:
        proactive.clear_speaker(_say)
    assert proactive.speaker() is None, "al cerrar la sesión el hablador se suelta"


# ── EPHEMERAL — the filler must not hang from the conversation history (V2-122, 2026-08-17) ──────────────────
# Real bug: `¡Hola! ¿Cómo va todo?…` followed by `Déjame que mire…` on the chat wall — the filler hanging
# AFTER a response that no longer needed to cover anything. Cause: the filler went through `proactive.speaker()`,
# which in LiveKit defaults to `session.say(..., add_to_chat_ctx=True)` — it DOES enter the conversation history
# and from there, via `conversation_item_added`, the chat wall. `ephemeral_speaker()` is the same path with
# `add_to_chat_ctx=False`: it is never recorded as an item, so it can never reach the chat.
def test_hay_una_costura_efimera_separada_del_hablador_normal():
    """`speaker()` and `ephemeral_speaker()` are TWO independent registrations — content with meaning of its own
    (V2-102/V2-096/notify) uses the first (it MUST remain in the history); neutral filler uses the second
    (it must NEVER remain). Verifies that they are decoupled: registering one does not affect the other."""
    from voice import proactive

    assert proactive.ephemeral_speaker() is None, "sin sesión registrada no puede haber hablador efímero"

    async def _say(text):
        pass

    async def _say_eph(text):
        pass

    proactive.register_speaker(_say)
    proactive.register_ephemeral_speaker(_say_eph)
    try:
        assert proactive.speaker() is _say
        assert proactive.ephemeral_speaker() is _say_eph
        assert proactive.speaker() is not proactive.ephemeral_speaker()
    finally:
        proactive.clear_speaker(_say)
    assert proactive.speaker() is None
    assert proactive.ephemeral_speaker() is None, "clear_speaker() debe soltar TAMBIÉN el hablador efímero"


def test_clear_speaker_no_suelta_el_efimero_de_otra_sesion(monkeypatch):
    """The identity guard (`_speaker is fn`) protects against an OLD session closing a NEW session's speaker —
    the same protection must cover the ephemeral speaker, which does not participate in the comparison by itself."""
    from voice import proactive

    async def _old(text):
        pass

    async def _new(text):
        pass

    async def _new_eph(text):
        pass

    proactive.register_speaker(_old)
    proactive.register_speaker(_new)                 # a new session has already taken the slot
    proactive.register_ephemeral_speaker(_new_eph)
    proactive.clear_speaker(_old)                     # teardown of the OLD session, with its own fn
    try:
        assert proactive.speaker() is _new, "la sesión nueva no puede perder su hablador por el teardown de la vieja"
        assert proactive.ephemeral_speaker() is _new_eph
    finally:
        proactive.clear_speaker(_new)


def test_V2529_el_relleno_es_audio_dentro_de_la_locucion_y_el_proveedor_solo_ARMA():
    """CODE GUARD on the V2-529 wiring (mounting the full provider requires half a LiveKit session):
    (1) nucleo.py no longer constructs any LeadInFiller or speaks through `say` — it only ARMS the audio filler;
    (2) agent.py overrides `llm_node` by delegating to `filler_audio.llm_node_with_filler`, which is the only
    place where the filler can play BEFORE the response (as its first SEGMENT)."""
    from pathlib import Path

    nucleo_body = (Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text()
    assert "filler_audio.arm(" in nucleo_body or "_filler_audio.arm(" in nucleo_body, \
        "el proveedor tiene que ARMAR el relleno por turno — sin arm, ningún turno puede sonar uno"
    assert "lead_in_filler import" not in nucleo_body and "LeadInFiller(" not in nucleo_body, \
        "el camino say del relleno volvió — ese say se autoriza DETRÁS de la respuesta y suena tarde SIEMPRE"

    # V2-538: las tres sobrescrituras de nodo salieron a su propio módulo (lo pidió el trinquete de
    # arquitectura). El guarda sigue al CÓDIGO —que es justo lo que cazó al mudarse— y comprueba además que
    # el entrypoint la MONTE: una sobrescritura que nadie instancia no es cableado.
    overrides = (Path(__file__).resolve().parents[3] / "voice/engine/pipeline/zaelar_agent.py").read_text()
    assert "llm_node_with_filler" in overrides, \
        "sin el override de llm_node, el relleno no tiene por dónde entrar como PRIMER segmento de la respuesta"
    agent_body = (Path(__file__).resolve().parents[3] / "voice/engine/pipeline/agent.py").read_text()
    assert "from .zaelar_agent import ZaelarAgent" in agent_body and "ZaelarAgent(instructions=" in agent_body, \
        "la clase con los overrides tiene que estar MONTADA por el entrypoint"


def test_el_hablador_efimero_pasa_add_to_chat_ctx_false():
    """CODE GUARD on `agent.py`: the `session.say()` registered as the EPHEMERAL speaker must include
    `add_to_chat_ctx=False` — without this, `ephemeral_speaker()` does not fulfill what its name promises."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "voice/engine/pipeline/agent.py"
    body = src.read_text(encoding="utf-8")
    i = body.index("async def _speak_ephemeral")
    j = body.index("register_ephemeral_speaker", i)
    block = body[i:j]
    assert "add_to_chat_ctx=False" in block, \
        "el hablador efímero debe llamar a session.say(..., add_to_chat_ctx=False)"


# ── DO NOT TALK OVER THE OPERATOR (2026-08-15, session 319252e7) ───────────────────────────────────────────
# The operator: *“the audio cuts out quite a bit, phrases are cut off before they finish… I think the voice is being
# interrupted by internal processes or by the agent itself, but that should not be happening”.*
#
# It was not TTS cutting out: it was the AGENT starting to talk over him. Measured on that session, counting the
# `say (proactive delivery)` event already recorded by the V2-047 F7 instrumentation: **2 of 10 fillers came out
# with `user_in_flight: true`**, and the resulting barge-in left 3 turns canceled due to “overlap”. That
# instrumentation literally said “telemetry only; does not change behavior yet” — there is data now.
def test_hay_una_sonda_de_si_el_operador_esta_hablando():
    """Deliberately separate from the busy probe: that one means “something is in flight” and is used to WAIT for an
    opening; the filler skips that wait by design, so it needs the half that allows no exception."""
    from voice import proactive

    assert proactive.user_speaking() is False, "sin sonda registrada, no se asume que habla (dejaría mudo al agente)"
    proactive.register_user_probe(lambda: True)
    try:
        assert proactive.user_speaking() is True
    finally:
        proactive.clear_speaker()
    assert proactive.user_speaking() is False, "al cerrar la sesión la sonda se suelta"


def test_una_sonda_que_revienta_no_deja_mudo_al_agente():
    from voice import proactive

    def _rota():
        raise RuntimeError("sesión a medio morir")

    proactive.register_user_probe(_rota)
    try:
        assert proactive.user_speaking() is False, "fail-open: medir mal no puede callar al agente"
    finally:
        proactive.clear_speaker()


# ── “THE BOT IS SPEAKING” PROBE (2026-08-16) ────────────────────────────────────────────────────────────────
# Different from the operator probe: `nucleo.py::_maybe_close_flow` uses it to avoid closing a turn's observability
# flow while its own response is still being narrated in TTS (the turn disappeared from the master board mid-speech
# — see drain_pending_flow_closes in nucleo.py and the hook in agent.py::on_state_change).
def test_hay_una_sonda_de_si_el_bot_esta_hablando():
    from voice import proactive

    assert proactive.bot_speaking() is False, "sin sonda registrada, cerrar el flujo de inmediato es lo de siempre"
    proactive.register_bot_probe(lambda: True)
    try:
        assert proactive.bot_speaking() is True
    finally:
        proactive.clear_speaker()
    assert proactive.bot_speaking() is False, "al cerrar la sesión la sonda se suelta"


def test_el_relleno_de_audio_consulta_la_sonda_del_operador():
    """The surviving half of the old guard: the filler never talks OVER the operator. The other half
    (dying with the canceled turn) no longer needs lifecycle: the filler is audio INSIDE the response's
    utterance (V2-529), so the barge-in that cuts the turn cuts it too, structurally."""
    from pathlib import Path

    body = (Path(__file__).resolve().parents[3] / "voice/engine/speech/filler_audio.py").read_text()
    assert "user_speaking()" in body, "el relleno volvería a hablar encima del operador"


# ── the clock the PERSON lives (V2-535, from the 2026-09-01 voice-fluidity audit) ─────────────────────────
"""TTFT measures the model and `TTSMetrics.ttfb` measures the synthesizer; NEITHER is the wait.

The audit's first recommendation was to measure “first real audio,” and it was right that nothing did: both
edges were already emitted — «… fin de voz» in the user-state handler and `state=speaking` in the agent-state
handler — in two different handlers, with nobody pairing them. So a slow turn could be reconstructed only by
joining rows after the fact, which is why nobody ever did.

It also reports whether what sounded FIRST was the filler or the reply, because those are different products:
“it answered in 2 s” and “it made a sound at 1.1 s and answered at 2 s” feel nothing alike.
"""
from pathlib import Path

AGENT = Path(__file__).resolve().parents[3] / "voice" / "engine" / "pipeline" / "agent.py"


def test_the_filler_remembers_when_it_last_sounded():
    from voice.engine.speech import filler_audio as fa

    before = fa.last_fired_at()
    fa._announce("Veamos…")
    assert fa.last_fired_at() > before, "without this the onset cannot say what the operator heard first"


def test_the_end_of_the_operators_voice_is_recorded_as_the_edge():
    src = AGENT.read_text(encoding="utf-8")
    i = src.index('_emit("vad", "… fin de voz"')
    assert '_onset["voice_ended"] = time.monotonic()' in src[i:i + 400], \
        "the near end of the wait has to be stamped where the voice ends, or there is nothing to measure from"


def test_the_onset_is_reported_once_and_only_for_a_plausible_wait():
    """Two properties this cannot be right without: the edge is CLEARED (a segmented reply would otherwise
    report its second segment as a second onset) and a stale edge is dropped (a proactive delivery minutes
    later is not an answer to anything)."""
    src = AGENT.read_text(encoding="utf-8")
    i = src.index("RESPONSE ONSET")
    block = src[i:i + 1800]
    assert '_onset["voice_ended"] = 0.0' in block, "reported once per wait"
    assert "_gap <= _ONSET_MAX_S" in block, "a stale edge is not an answer"
    assert '"onset_ms"' in block and '"covered_by_filler"' in block
    assert "last_fired_at() >= _ended" in block, \
        "«covered» must mean the filler sounded during THIS wait, not in an older one"
