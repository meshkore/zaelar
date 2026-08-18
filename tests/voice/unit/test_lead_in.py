"""
test_lead_in.py — el RELLENO DE ESPERA tiene que SONAR mientras se espera (V2-093, 2026-08-14).

El relleno existe desde 2026-07-19 para tapar el TTFT del modelo con un «Mmm…» / «A ver…». Auditando la sesión
b70a45d0 salió que **no había sonado ni una vez**: 48 rellenos generados, 0 oídos a tiempo, 50 segundos de
`bot_speech: idle` con TRES pendientes, y las 11 respuestas habladas empezando TODAS por su relleno («Déjame que
mire… Sí, te he oído»). El operador, mientras, decía «¿me has oído?» y «parece que te has quedado tonto» — a un
agente que estaba trabajando y tenía tres frases de espera generadas y mudas.

La causa no era el relleno: era POR DÓNDE viajaba. Se empujaba como un `ChatChunk` al stream de la respuesta, y ese
stream pasa por el tokenizador de frases de LiveKit (`BufferedSentenceStream`), que **solo entrega un segmento
cuando tiene DOS**: emite el primero y se queda el último como contexto. Un relleno suelto no llega ni a ser
segmento (acaba en «…», que no está en el regex de fin de frase `[.!?。！？]`, y no pasa de `min_sentence_len=20`),
así que se queda en el buffer hasta que llega la respuesta real — y entonces sale PEGADO a ella.

Los tests de abajo (1) reproducen exactamente ese pegado, que es lo que no puede volver a pasar, y (2) fijan la
costura fuera de banda por la que ahora sale.
"""
from __future__ import annotations

import pytest

from voice.engine.core import langs


def _pushed(*chunks: str) -> list[str]:
    """Segmentos que el tokenizador de LiveKit ENTREGA A TTS tras empujar `chunks`, SIN cerrar el stream — que es
    la única situación que importa: mientras el turno sigue vivo, nadie hace flush.

    Va DENTRO de un `asyncio.run`: el canal de LiveKit se construye con `asyncio.get_event_loop()`, que revienta si
    el hilo no tiene loop actual — y basta con que otro test de la suite haya cerrado el suyo para que esto falle
    solo al correr en conjunto (pasó al añadirlo: verde en solitario, rojo en suite)."""
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
    """Ningún relleno de ningún idioma se entrega por sí mismo: es LA razón de que haga falta el camino fuera de
    banda. Si esto empieza a fallar (LiveKit cambia el tokenizador, o alguien añade un relleno con punto y de más
    de 20 chars) el say deja de ser obligatorio — hasta entonces, meterlo en el stream es garantizar que no suene."""
    fillers = langs.spec(code).fillers
    assert fillers, f"el idioma {code} no tiene rellenos"
    for f in fillers:
        assert _pushed(f + " ") == [], f"{f!r} sí saldría solo: revisa si el camino fuera de banda sigue haciendo falta"


def test_por_el_stream_el_relleno_sale_PEGADO_a_la_respuesta():
    """EL SÍNTOMA EXACTO de la sesión b70a45d0, reproducido. Lo que el operador oyó a los 98,8 s fue una sola
    locución: «Déjame que mire… Sí, te he oído». El relleno no tapó nada — viajó 56 segundos en un buffer."""
    segs = _pushed("Déjame que mire… ", REPLY)
    assert segs, "el arnés no mide nada: revísalo antes de fiarte del resto"
    assert segs[0].startswith("Déjame que mire…"), segs[0]
    assert "te he oído" in segs[0], "esto es lo que hay que evitar: relleno y respuesta en la MISMA locución"


def test_la_respuesta_sola_si_se_entrega():
    """Control positivo: el arnés mide algo real. Una respuesta de dos frases sí suelta la primera."""
    segs = _pushed(REPLY)
    assert segs and "te he oído" in segs[0]


def test_hay_costura_fuera_de_banda_y_dice_la_verdad():
    """`proactive.speaker()` es por donde el relleno alcanza el TTS sin pasar por el agregador. None cuando no hay
    sesión viva — ahí el proveedor conserva el camino antiguo, porque sin TTS no hay nada que tapar."""
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


# ── EFÍMERO — el relleno no puede colgar del historial de conversación (V2-114, 2026-08-17) ──────────────────
# Bug real: `¡Hola! ¿Cómo va todo?…` seguido de `Déjame que mire…` en el muro de chat — el relleno colgando
# DESPUÉS de una respuesta que ya no necesitaba tapar nada. Causa: el relleno salía por `proactive.speaker()`,
# que en LiveKit es `session.say(..., add_to_chat_ctx=True)` por defecto — SÍ entra al historial de conversación
# y de ahí, vía `conversation_item_added`, al muro de chat. `ephemeral_speaker()` es la misma vía con
# `add_to_chat_ctx=False`: nunca se registra como item, así que nunca puede llegar al chat.
def test_hay_una_costura_efimera_separada_del_hablador_normal():
    """`speaker()` y `ephemeral_speaker()` son DOS registros independientes — un contenido con sentido propio
    (V2-102/V2-096/notify) usa el primero (SÍ debe quedar en el historial); el relleno neutro usa el segundo
    (NUNCA debe quedar). Verifica que están desacoplados: registrar uno no afecta al otro."""
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
    """La guarda de identidad (`_speaker is fn`) protege contra una sesión VIEJA cerrando el hablador de una
    NUEVA — el mismo cuidado tiene que cubrir el efímero, que no participa en la comparación por sí mismo."""
    from voice import proactive

    async def _old(text):
        pass

    async def _new(text):
        pass

    async def _new_eph(text):
        pass

    proactive.register_speaker(_old)
    proactive.register_speaker(_new)                 # una sesión nueva ya tomó el slot
    proactive.register_ephemeral_speaker(_new_eph)
    proactive.clear_speaker(_old)                     # teardown de la VIEJA, con su propio fn
    try:
        assert proactive.speaker() is _new, "la sesión nueva no puede perder su hablador por el teardown de la vieja"
        assert proactive.ephemeral_speaker() is _new_eph
    finally:
        proactive.clear_speaker(_new)


def test_el_proveedor_manda_el_relleno_FUERA_DE_BANDA_Y_EFIMERO():
    """Guarda de CÓDIGO sobre el camino elegido: el relleno se habla por `proactive.ephemeral_speaker()` (nunca
    `speaker()`) y el `ChatChunk` queda como respaldo para cuando no hay sesión. Guarda textual a propósito —
    montar el proveedor entero exige media sesión de LiveKit, y lo que de verdad puede regresar aquí es que
    alguien «simplifique» quitando el say o volviendo al hablador que sí deja rastro en el chat."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/lead_in_filler.py"
    body = src.read_text(encoding="utf-8")
    i = body.index("async def _run")
    block = body[i:]
    assert "proactive.ephemeral_speaker()" in block, \
        "el relleno tiene que salir por el hablador EFÍMERO — con el normal volvería a colgar del chat"
    assert "proactive.speaker()" not in block, \
        "el relleno NUNCA usa el hablador normal — eso es justo el bug que reabre el chat colgando"
    assert "create_task(_spk(" in block, "el say tiene que dispararse sin bloquear el turno"
    # El ChatChunk sigue existiendo, pero SOLO como respaldo: dentro de un `else`.
    j = block.index("ChatChunk", block.index("create_task(_spk("))
    assert "else:" in block[block.index("create_task(_spk("):j], \
        "el ChatChunk tiene que quedar en la rama de respaldo, no en el camino normal"


# ── EL RELLENO SÍ VA AL MURO DE CHAT — pero EXPLÍCITO y MARCADO (2026-08-18) ───────────────────────────────
# El relleno «no debe colgar del historial de LiveKit» (arriba) no significa «no debe verse»: sigue siendo una
# frase real que el agente dijo. La fuga original (LiveKit decidiendo el orden) se sustituye por un `emit`
# PROPIO, síncrono, con un `kind` dedicado — así el frontend lo marca como relleno y nunca lo confunde con una
# respuesta generada por el modelo, y el orden queda garantizado (se dispara ANTES de que exista texto real).
def test_leadinfiller_empuja_su_propio_evento_de_chat_marcado():
    import asyncio

    from voice.engine.llm.providers.lead_in_filler import LeadInFiller

    class _Brain:
        _last_filler = ""

    events = []

    def _emit(kind, label, text="", role="", extra=None):
        events.append({"kind": kind, "label": label, "text": text, "role": role, "extra": extra or {}})

    async def _stub_speak(text):
        pass

    import voice.proactive as proactive
    monkeypatch_targets = [
        (proactive, "ephemeral_speaker", lambda: _stub_speak),
        (proactive, "user_speaking", lambda: False),
    ]
    originals = [(obj, name, getattr(obj, name)) for obj, name, _ in monkeypatch_targets]
    for obj, name, fn in monkeypatch_targets:
        setattr(obj, name, fn)
    try:
        f = LeadInFiller(delay_ms=1, brain=_Brain(), superseded=lambda: False, event_ch=None, emit=_emit)
        asyncio.run(f._run())
    finally:
        for obj, name, orig in originals:
            setattr(obj, name, orig)

    filler_events = [e for e in events if e["kind"] == "filler"]
    assert filler_events, "el relleno tiene que empujar su propio evento marcado, dedicado (kind='filler')"
    assert filler_events[0]["role"] == "assistant", "es una frase que el agente DIJO — role=assistant"
    assert filler_events[0]["text"], "tiene que llevar la frase real que se dijo"
    # …y el rastro de depuración de siempre se mantiene intacto, sin duplicar el kind.
    debug_events = [e for e in events if e["kind"] == "brain"]
    assert debug_events, "el rastro de observabilidad/depuración original no puede desaparecer"


def test_el_hablador_efimero_pasa_add_to_chat_ctx_false():
    """Guarda de CÓDIGO sobre `agent.py`: el `session.say()` registrado como hablador EFÍMERO tiene que llevar
    `add_to_chat_ctx=False` — sin esto, `ephemeral_speaker()` no cumple lo que promete su nombre."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "voice/engine/pipeline/agent.py"
    body = src.read_text(encoding="utf-8")
    i = body.index("async def _speak_ephemeral")
    j = body.index("register_ephemeral_speaker", i)
    block = body[i:j]
    assert "add_to_chat_ctx=False" in block, \
        "el hablador efímero debe llamar a session.say(..., add_to_chat_ctx=False)"


# ── AL OPERADOR NO SE LE HABLA ENCIMA (2026-08-15, sesión 319252e7) ───────────────────────────────────────────
# El operador: *«el audio se corta bastante, se cortan las frases antes de terminarse… creo que aquí se está
# interrumpiendo la voz por procesos internos o por el propio agente, pero eso no debería ser así»*.
#
# No era el TTS cortándose: era el AGENTE arrancando a hablar encima de él. Medido sobre esa sesión, contando el
# evento `say (entrega proactiva)` que la instrumentación de V2-047 F7 ya registraba: **2 de 10 rellenos salieron
# con `user_in_flight: true`**, y el barge-in resultante dejó 3 turnos cancelados por «overlap». Aquella
# instrumentación decía literalmente «solo telemetría; no cambia el comportamiento todavía» — ya hay datos.
def test_hay_una_sonda_de_si_el_operador_esta_hablando():
    """Separada del busy-probe a propósito: aquél es «hay algo en vuelo» y sirve para ESPERAR hueco; el relleno se
    salta esa espera por diseño, así que necesita la mitad que no admite excepción."""
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


# ── Sonda de "el BOT está hablando" (2026-08-16) ────────────────────────────────────────────────────────────────
# Distinta de la del operador: `nucleo.py::_maybe_close_flow` la usa para no cerrar el flujo de observabilidad de
# un turno mientras su propia respuesta todavía se está narrando en TTS (el turno desaparecía del master board en
# pleno habla — ver drain_pending_flow_closes en nucleo.py y el hook en agent.py::on_state_change).
def test_hay_una_sonda_de_si_el_bot_esta_hablando():
    from voice import proactive

    assert proactive.bot_speaking() is False, "sin sonda registrada, cerrar el flujo de inmediato es lo de siempre"
    proactive.register_bot_probe(lambda: True)
    try:
        assert proactive.bot_speaking() is True
    finally:
        proactive.clear_speaker()
    assert proactive.bot_speaking() is False, "al cerrar la sesión la sonda se suelta"


def test_el_relleno_consulta_la_sonda_y_muere_con_su_turno():
    """Guarda de CÓDIGO, por el mismo motivo que la de arriba (montar el proveedor exige media sesión LiveKit).
    Vigila las dos mitades del arreglo: (1) no arrancar si el operador habla, y (2) que la locución ya lanzada se
    cancele con el turno — era fire-and-forget, así que cancelar el TEMPORIZADOR no paraba nada y el relleno de un
    turno muerto seguía sonando DESPUÉS de que el operador hubiera dicho otra cosa. V2-114: el mecanismo vive en
    `lead_in_filler.py`; nucleo.py solo tiene que LLAMAR a `cancel_for_barge_in()` en el barge-in."""
    from pathlib import Path

    filler_src = Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/lead_in_filler.py"
    body = filler_src.read_text(encoding="utf-8")
    i = body.index("async def _run")
    block = body[i:]
    assert "user_speaking()" in block, "el relleno volvería a hablar encima del operador"
    assert "self._superseded()" in block, "un turno superado no puede soltar su relleno"
    assert 'self._say_task = asyncio.create_task(_spk(' in block, \
        "sin guardar el handle, la locución sobrevive a la cancelación del turno"
    assert "def cancel_for_barge_in" in body and "_say_task.cancel()" in body, \
        "el relleno de un turno cancelado por barge-in tiene que poder morir con él"

    nucleo_src = Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py"
    nucleo_body = nucleo_src.read_text(encoding="utf-8")
    cancel = nucleo_body.index("✂️ turno cancelado (barge-in/overlap)")
    assert "_filler.cancel_for_barge_in()" in nucleo_body[cancel - 400:cancel], \
        "el turno manager tiene que avisar al relleno en el barge-in, no solo tenerlo definido"
