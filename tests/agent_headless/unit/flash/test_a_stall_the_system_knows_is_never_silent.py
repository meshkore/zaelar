"""El sistema sabía que estaba atascada, se lo puso delante, y el turno calló (V2-359).

V2-354 puso el HECHO en el prompt —«SIN AVANZAR: 5 min sin completar un paso»— y su imperativo manda decirlo
«con esas letras la primera vez que salga a colación». Medido DOS VECES el mismo día, con el mismo código:

  · `weekend-adventure-sports-bilbao__es` (2026-08-27) — lo dijo, y bien:
        «La tarea lleva 5 minutos atascada sin completar ni un paso, así que te lo digo claro: va encallada,
         no te la estoy escondiendo. Te ofrezco pararla o dejarla que…»

  · `search-buy-used-car` (2026-08-27, 2/5) — NO lo dijo. Con el mismo aviso delante, el turno narró «la
    búsqueda sigue en marcha» y «el navegador lleva unos minutos dándome alguna página vacía, pero no lo
    paro». El juez, [alta]: «El sistema le puso delante un aviso para que ofreciera pararlo o seguir, y zaelar
    no lo trasladó. El usuario preguntó TRES veces por el estado y nunca recibió la verdad».

Una de cada dos. Y esa variancia es exactamente lo que V2-305 dejó escrito para el backstop de entrega:
**cuando la conducta correcta es DETERMINISTA —hay un atasco medido y la respuesta es una espera— la garantiza
el código, no la temperatura del modelo.** Este es su hermano, para el otro hecho.

UNA SOLA FUENTE del atasco (`live_blocks.any_stalled_task`), los mismos umbrales que la cara: dos copias de
esos números es cómo el operador acaba oyendo una cosa del aviso proactivo y otra del agente al que acaba de
preguntar — la razón está escrita en `dispatch_thresholds`.

Y VA DESPUÉS del backstop de filas, no antes: con resultados delante la cara correcta es entregarlos, no
hablar del atasco.
"""
import pytest

from nucleo.flash import delivery as RG


@pytest.fixture(autouse=True)
def _hablando_en_castellano(monkeypatch):
    """These tests assert the SPANISH wording, so they state the language instead of inheriting it.

    Until V2-475 this family had one wording and the language was invisible; now that the sentence follows
    the operator's language, a test that leaves it ambient is really asserting «whatever the default is»
    (English on a fresh engine) — which is how a Spanish assertion silently starts grading English output.
    """
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es")


ESPERA = "Sigo con ello; te aviso en cuanto tenga algo."


def test_una_espera_sobre_un_atasco_MEDIDO_sale_con_el_hecho():
    out = RG.stalled_task_backstop(ESPERA, "busca un coche de segunda mano", 5, "sin avanzar")
    assert "5 min sin completar un paso" in out
    assert "¿La paro" in out, "el hecho sin una salida concreta deja al operador igual de quieto"


def test_una_tarea_CALLADA_lo_dice_con_sus_palabras():
    out = RG.stalled_task_backstop(ESPERA, "busca un coche", 4, "callada")
    assert "4 min sin dar señal" in out


def test_si_la_respuesta_YA_lo_dice_el_backstop_calla():
    """La ronda de Bilbao: el modelo lo contó él solo y bien. Añadir detrás sería el disco rayado de V2-189."""
    bien = ("La tarea lleva 5 minutos atascada sin completar ni un paso, así que te lo digo claro: va "
            "encallada, no te la estoy escondiendo. Te ofrezco pararla.")
    assert RG.stalled_task_backstop(bien, "busca un coche", 5, "sin avanzar") == ""


def test_una_respuesta_que_YA_ENTREGA_no_se_pisa():
    """No es una espera: está contando algo. Mismo criterio que el backstop hermano."""
    entrega = "¡Ya tengo tres coches! Un Audi Q3 por 11.900 € y un Peugeot 3008 por 10.500 €."
    assert RG.stalled_task_backstop(entrega, "busca un coche", 5, "sin avanzar") == ""


def test_sin_atasco_no_hay_nada_que_anadir():
    assert RG.stalled_task_backstop(ESPERA, "", 0, "") == ""
    assert RG.stalled_task_backstop(ESPERA, "busca un coche", 0, "sin avanzar") == ""


def test_una_pregunta_corta_no_es_una_espera():
    """El operador acaba de recibir una pregunta, no una promesa de aviso: colgarle el atasco detrás cambia
    el turno de tema."""
    assert RG.stalled_task_backstop("¿Prefieres diésel o gasolina?", "busca un coche", 5, "sin avanzar") == ""


def test_las_variantes_de_ya_haberlo_dicho():
    for r in ("Sigo con ello, aunque va lenta: lleva 5 min clavada en el mismo paso.",
              "Te aviso en cuanto tenga algo; parece que se ha quedado parada.",
              "Sigo pendiente, el navegador está bloqueado."):
        assert RG.stalled_task_backstop(r, "busca un coche", 5, "sin avanzar") == "", r


def test_la_FUENTE_del_atasco_es_la_misma_que_la_de_la_cara():
    """Guarda contra la divergencia que este repositorio ya pagó: `any_stalled_task` lee `pending_summaries` y
    los umbrales de `dispatch_thresholds`, igual que `pending_task_lines`. Si un día uno de los dos se copiara
    su propio número, el aviso y el agente dirían cosas distintas del mismo hecho."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/flash/live_blocks.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    i = src.index("def any_stalled_task")
    cuerpo = src[i:src.index("\ndef ", i + 10)]
    assert "pending_summaries()" in cuerpo
    assert "STUCK_SECS" in cuerpo and "NO_STEP_SECS" in cuerpo


def test_el_turno_lo_CABLEA_y_DESPUES_de_las_filas():
    """Guarda de cableado y de ORDEN: con filas que entregar, entregar gana."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/flash/delivery.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "stalled_task_backstop(spoken" in src, "la decisión sin llamante es el arreglo que no existe"
    assert src.index("sheet_delivery_backstop(spoken") < src.index("stalled_task_backstop(spoken")


# ── V2-361: el vocabulario de ESPERA salió de una tanda, y le faltaban formas reales ────────────────────
#
# Medido en `best-rated-rental-car__es` (2026-08-27, ronda del supervisor, 2/5). La cara marcó la tarea SIN
# AVANZAR desde el segundo **188,2**, y la última respuesta que el vocabulario reconoció como espera fue la de
# los **145,3**. Entre medias el turno dijo cosas como «Te informo en cuanto SEPA algo» y «Voy a reunir todo lo
# que llevo» — esperas de manual que la lista no casaba, porque tenía `en cuanto (tenga|salga|encuentre|
# aparezca)` y «sepa» no estaba.
#
# Resultado: el atasco estaba DETECTADO, la cara lo decía, y ningún backstop llegó siquiera a mirarlo. La
# calibración de este vocabulario tiene el mismo defecto que tuvo el umbral de V2-354 — salir de un solo caso.
#
# Y cuesta DOBLE: `_WAITING_REPLY_RE` alimenta a los dos backstops (entrega y atasco), así que cada forma que
# falta son dos silencios sobre el mismo turno.

@pytest.mark.parametrize("reply", [
    "Te informo en cuanto sepa algo.",
    "Voy a reunir todo lo que llevo para cerrar el aviso.",
    "Dame un segundo y te digo.",
    "En cuanto la tenga te la paso.",
    # Aísla «te informo»: sin esta frase, quitar esa entrada del vocabulario no rompía NADA — las demás casaban
    # por «en cuanto…». Un desarme que aplica y no muerde señala una entrada sin probar, no una entrada de más.
    "Te informo luego.",
])
def test_las_formas_de_espera_que_faltaban(reply):
    assert RG.stalled_task_backstop(reply, "alquila un coche", 4, "sin avanzar") != "", reply


@pytest.mark.parametrize("reply", [
    "¡Ya tengo tres coches! Un Audi Q3 por 11.900 € y un Peugeot por 10.500 €.",
    "¿Prefieres automático o manual?",
    "Perfecto, lo dejo así entonces.",
])
def test_ensanchar_no_convierte_en_espera_lo_que_no_lo_es(reply):
    """El lado que un vocabulario más ancho pone en riesgo, y el que importa: una entrega, una pregunta o un
    cierre no pueden llevar un atasco colgado detrás."""
    assert RG.stalled_task_backstop(reply, "alquila un coche", 4, "sin avanzar") == "", reply


def test_el_vocabulario_ancho_tambien_sirve_a_la_ENTREGA():
    """`_WAITING_REPLY_RE` lo comparten los dos backstops: una forma que faltaba costaba dos silencios, y
    arreglarla vale por dos. Aquí se comprueba en el hermano."""
    filas = ["Audi Q3 2.0 TDI — 11.900 €", "Peugeot 3008 BlueHDi — 10.500 €", "SEAT Ateca 1.6 TDI — 11.200 €"]
    out = RG.sheet_delivery_backstop("Te informo en cuanto sepa algo.", filas, "",
                                     errand="alquila un coche para el finde")
    assert "Audi Q3" in out
