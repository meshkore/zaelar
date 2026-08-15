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


def test_el_proveedor_manda_el_relleno_FUERA_DE_BANDA():
    """Guarda de CÓDIGO sobre el camino elegido: el relleno se habla por `proactive.speaker()` y el `ChatChunk`
    queda como respaldo para cuando no hay sesión. Guarda textual a propósito — montar el proveedor entero exige
    media sesión de LiveKit, y lo que de verdad puede regresar aquí es que alguien «simplifique» quitando el say."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py"
    body = src.read_text(encoding="utf-8")
    # El bloque se acota por su FINAL real, no por un número de caracteres. Antes cortaba a 3.200 y el test se
    # rompía en cuanto la función crecía —le pasó el 2026-08-15 al añadirle la guarda de «no hablar encima del
    # operador»—, o sea que fallaba por el tamaño del comentario y no por lo que dice vigilar.
    i = body.index("async def _lead_in_filler")
    block = body[i:body.index("# NO en el kickoff", i)]
    assert "proactive.speaker()" in block, "el relleno ya no sale fuera de banda: volvería a no oírse nunca"
    assert "create_task(_spk(" in block, "el say tiene que dispararse sin bloquear el turno"
    # El ChatChunk sigue existiendo, pero SOLO como respaldo: dentro de un `else`.
    j = block.index("ChatChunk", block.index("create_task(_spk("))
    assert "else:" in block[block.index("create_task(_spk("):j], \
        "el ChatChunk tiene que quedar en la rama de respaldo, no en el camino normal"


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


def test_el_relleno_consulta_la_sonda_y_muere_con_su_turno():
    """Guarda de CÓDIGO, por el mismo motivo que la de arriba (montar el proveedor exige media sesión LiveKit).
    Vigila las dos mitades del arreglo: (1) no arrancar si el operador habla, y (2) que la locución ya lanzada se
    cancele con el turno — era fire-and-forget, así que cancelar el TEMPORIZADOR no paraba nada y el relleno de un
    turno muerto seguía sonando DESPUÉS de que el operador hubiera dicho otra cosa."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py"
    body = src.read_text(encoding="utf-8")
    i = body.index("async def _lead_in_filler")
    block = body[i:body.index("# NO en el kickoff", i)]
    assert "user_speaking()" in block, "el relleno volvería a hablar encima del operador"
    assert "_superseded()" in block, "un turno superado no puede soltar su relleno"
    assert '_filler_say["task"] = asyncio.create_task(_spk(' in block, \
        "sin guardar el handle, la locución sobrevive a la cancelación del turno"
    # …y alguien tiene que cancelarlo en el barge-in.
    cancel = body.index("✂️ turno cancelado (barge-in/overlap)")
    assert "_say_t.cancel()" in body[cancel - 1200:cancel], \
        "el relleno de un turno cancelado por barge-in tiene que morir con él"
