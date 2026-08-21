"""La MARCA DE AGUA: se marca dónde acabó la frase, se actúa con lo de antes, y el resto sigue vivo.

Encargo del operador, 2026-08-21, textual: «si de esas últimas tres palabras una era para concluir la frase
anterior y otras dos para empezar una nueva, no pasa nada: seteamos un punto en el tiempo y le pasamos ese texto
a partir de ahí al modelo». Delegó el mecanismo y fijó la propiedad: nada de lo que dice se pierde, y se sabe en
qué punto de la línea temporal se consumió una frase completa.

CÓMO SE MIDE, que no es un detalle. El encargo llegó como «si el fragmento cierra la frase A y trae el principio
de la B, B SE PIERDE». Medido, eso no es lo que pasaba:

    offer("pon música de jazz y")                         -> hold
    offer("luego apágala. Y después")                     -> act("pon música de jazz y luego apágala. Y después")

B no se borraba: VIAJABA DENTRO de la petición de A, y solo A se contestaba. La diferencia importa aquí porque un
test que afirme «B no se perdió» pasa en verde sobre el código ROTO —B está en el texto entregado— y solo el que
afirma «B no viajó en la petición de A y sigue en el buffer» distingue las dos cosas.

SOLO SE PELA UNA COLA COLGANDO, y esa restricción es toda la seguridad de la función: se exige que el resto esté
INCOMPLETO según la capa 1. Dos frases completas dichas de un tirón («pon música. sube el volumen») son UNA
petición de dos intenciones y tienen que viajar juntas — partirlas contestaría la mitad y dejaría la otra retenida
para siempre, porque no viene nada más que la complete. Se pelan comienzos, nunca instrucciones.
"""
import asyncio

import pytest

from nucleo.flash import accumulator as acc


@pytest.fixture(autouse=True)
def _sin_juez(monkeypatch):
    """La capa 2 es un LLM. Aquí se anula para medir la capa 1 y el corte, que es lo que este fichero afirma."""
    async def _incompleto(_t):
        return "incomplete", ""
    acc.set_judge(_incompleto)
    yield
    acc.set_judge(None)


def _ofrecer(a, texto, t):
    return asyncio.run(a.offer(texto, now=t))


# ── la propiedad ─────────────────────────────────────────────────────────────────────────────────────────────

def test_the_next_sentence_does_NOT_travel_inside_this_ones_request():
    a = acc.Accumulator()
    assert _ofrecer(a, "pon música de jazz y", 0.0)[0] == "hold"
    action, entregado, _why, _drop = _ofrecer(a, "luego apágala. Y después", 2.0)

    assert action == "act"
    assert entregado == "pon música de jazz y luego apágala."
    assert "Y después" not in entregado, "el principio de la frase siguiente viajó dentro de esta petición"
    assert a.text() == "Y después", "y además tiene que seguir VIVO, no solo fuera de la petición"


def test_the_surviving_tail_is_continued_by_what_comes_next():
    """La cola no es un resto guardado por si acaso: es el principio de la frase siguiente y se completa sola.

    OJO al montaje, que me costó tres tests mal escritos: el corte solo ocurre en el camino de ACTUAR. Un
    fragmento suelto que ya acaba colgando («cierra la ventana. Y») es INCOMPLETO en conjunto, así que se
    RETIENE entero — y eso es lo correcto, se está esperando su continuación. El corte hace falta justo cuando
    el conjunto SÍ cierra y aun así arrastra un principio detrás."""
    a = acc.Accumulator()
    _ofrecer(a, "pon música de jazz y", 0.0)
    _ofrecer(a, "luego apágala. Y después", 2.0)
    assert a.text() == "Y después"
    action, entregado, _w, _d = _ofrecer(a, "sube el volumen.", 4.0)
    assert action == "act"
    assert entregado == "Y después sube el volumen."


def test_the_watermark_marks_WHEN_a_complete_sentence_was_consumed():
    a = acc.Accumulator()
    assert a.consumed_at == 0.0
    _ofrecer(a, "pon música de jazz y", 0.0)
    _ofrecer(a, "luego apágala. Y después", 7.5)
    assert a.consumed_at == 7.5, "sin marca no se puede decir «lo de antes de aquí ya está contestado»"


def test_the_tails_clock_restarts_at_the_cut():
    """La cola se dijo AHORA, no cuando empezó la frase que arrastraba. Si conservara el reloj viejo, la válvula
    de hueco la mediría desde un instante que ya no significa nada y la descartaría antes de tiempo."""
    a = acc.Accumulator()
    _ofrecer(a, "pon música de jazz y", 3.0)
    _ofrecer(a, "luego apágala. Y después", 100.0)
    assert a.first_at == a.last_at == 100.0


# ── la restricción que la hace segura ────────────────────────────────────────────────────────────────────────

def test_two_complete_sentences_ship_TOGETHER():
    a = acc.Accumulator()
    action, entregado, _w, _d = _ofrecer(a, "pon música. sube el volumen", 0.0)
    assert action == "act"
    assert entregado == "pon música. sube el volumen", "partir dos instrucciones deja media petición sin contestar"
    assert not a.pending()


def test_a_buffer_with_no_sentence_end_is_not_cut():
    assert acc.dangling_tail("sin puntuación ninguna aquí") == ("", "")


def test_the_cut_takes_the_LAST_split_not_the_first():
    """Con tres frases en el buffer, cortar por la primera entregaría una por turno y le iría goteando al
    cerebro lo que el operador dijo de una vez."""
    cabeza, cola = acc.dangling_tail("abre el correo. borra el spam. Y luego")
    assert cabeza == "abre el correo. borra el spam."
    assert cola == "Y luego"


# ── las válvulas tampoco tiran la cola ───────────────────────────────────────────────────────────────────────

def test_a_valve_firing_is_not_a_reason_to_throw_the_tail():
    """Las cuatro salidas de `act` hacían el mismo `clear()` por su cuenta. Justo en el caso patológico —el que
    hace saltar la válvula— es donde más texto se entregaba de golpe y se vaciaba entero."""
    a = acc.Accumulator()
    assert _ofrecer(a, "esto ya es una frase entera. y", 0.0)[0] == "hold"
    for i in range(acc.MAX_FRAGMENTS - 1):
        act, _t, motivo, _d = _ofrecer(a, f"otra cosa número {i} y", float(i + 1))
        if act == "act":
            break
    assert act == "act" and "válvula" in motivo, f"no saltó la válvula (motivo: {motivo!r})"
    assert a.pending(), "la válvula entregó y vació: la cola colgando se fue con ella"
    assert a.text().startswith("y otra cosa"), a.text()


def test_the_word_valve_is_sized_from_the_operators_own_sessions():
    """El operador pidió 10-15 palabras. Medido replicando sus 129 ficheros de sesión por este acumulador, los
    buffers retenidos van a mediana 10 y p90 31, así que un tope de 15 habría disparado en 21 de 64 retenciones
    legítimas — un tercio— forzando la entrega de frases a medias. A 40 dispara en 3 de 64. Se le reportó con los
    números en vez de aplicarlo al pie de la letra; este test es lo que impide que alguien lo baje sin volver a
    medir."""
    assert acc.MAX_WORDS >= 30, (
        f"MAX_WORDS={acc.MAX_WORDS} dispara sobre retenciones legítimas (p90 medido: 31 palabras)")


# ── y lo DESCARTADO por el hueco largo tampoco se pierde ─────────────────────────────────────────────────────
#
# La otra mitad de «nada de lo que dice el operador se pierde». La válvula de hueco (> MAX_GAP_S) descarta el
# buffer viejo para no pegar dos temas distintos, y `_speak_acc_drop` existe para rescatar el contenido: le da al
# juez una última mirada y, si la petición estaba completa, empuja una nota `[SISTEMA]` para que salga en el turno
# siguiente. Solo que TODO eso vivía detrás de `if speak is None or user_speaking(): return`, así que el rescate
# dependía de que hubiera un altavoz vivo y el operador estuviera callado. En el canal de prueba nunca hay
# altavoz; a mitad de frase, tampoco. En los dos casos el texto desaparecía entero — ni nota, ni juez, ni rastro.
# Preservar el CONTENIDO y reconocerlo EN VOZ ALTA son dos trabajos, y solo el segundo necesita boca.

def test_a_discarded_chain_is_rescued_even_with_NO_voice(monkeypatch):
    from nucleo.flash import segmenter
    from voice import brain_notes, proactive
    from voice.engine.llm.providers import nucleo as vp

    notas: list[str] = []
    monkeypatch.setattr(brain_notes, "push", lambda t: notas.append(t))
    monkeypatch.setattr(proactive, "speaker", lambda: None)          # canal de prueba: no hay boca

    async def _juez(_t):
        return "complete", ""
    monkeypatch.setattr(segmenter, "judge", _juez)

    asyncio.run(vp._speak_acc_drop("reserva mesa para cuatro el jueves"))
    assert notas, "sin altavoz el texto del operador se perdió entero"
    assert "reserva mesa para cuatro el jueves" in notas[0]


def test_it_is_rescued_too_while_the_operator_is_still_talking(monkeypatch):
    """El otro guarda del mismo `return`, y es peor que el anterior: aquí SÍ hay altavoz, así que nadie sospecha
    que se esté perdiendo nada — simplemente el operador estaba hablando en ese instante."""
    from nucleo.flash import segmenter
    from voice import brain_notes, proactive
    from voice.engine.llm.providers import nucleo as vp

    notas: list[str] = []
    monkeypatch.setattr(brain_notes, "push", lambda t: notas.append(t))
    monkeypatch.setattr(proactive, "speaker", lambda: (lambda _t: None))
    monkeypatch.setattr(proactive, "user_speaking", lambda: True)

    async def _juez(_t):
        return "complete", ""
    monkeypatch.setattr(segmenter, "judge", _juez)

    asyncio.run(vp._speak_acc_drop("apúntame la ITV del coche para el lunes"))
    assert notas, "hablando encima del agente, lo dicho antes de la pausa se perdía"
