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
    la única situación que importa: mientras el turno sigue vivo, nadie hace flush."""
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
    i = body.index("async def _lead_in_filler")
    block = body[i:i + 3200]
    assert "proactive.speaker()" in block, "el relleno ya no sale fuera de banda: volvería a no oírse nunca"
    assert "create_task(_spk(" in block, "el say tiene que dispararse sin bloquear el turno"
    # El ChatChunk sigue existiendo, pero SOLO como respaldo: dentro de un `else`.
    j = block.index("ChatChunk", block.index("create_task(_spk("))
    assert "else:" in block[block.index("create_task(_spk("):j], \
        "el ChatChunk tiene que quedar en la rama de respaldo, no en el camino normal"
