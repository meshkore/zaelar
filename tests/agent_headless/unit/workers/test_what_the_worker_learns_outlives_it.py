"""Lo que un worker averigua tiene que sobrevivir a que lo maten (V2-344, 2026-08-26).

Medido por el arnés en `search-buy-used-car` (sesión 7575e81a): worker 1 llegó a milanuncios y capturó, muerto
a los 2 min; worker 2 muerto a los 8; el 3 entregó. En la BD del plató, la ÚNICA fila con `source=worker:*` en
toda la ventana 13:33-13:54 es la del que entregó — **los 21 minutos de los dos primeros no dejaron rastro**, y
cada relanzamiento renavegó, rebuscó y refiltró desde cero.

La capacidad estaba entera (el puente `mem_cli` viaja en el prompt, la ruta exige token por tarea y el gate de
precisión PASA hallazgos). Lo que faltaba era PEDIRLO — y la orden existía: decía literalmente «aunque el flujo
se reinicie», o sea la protección anti-relanzamiento, pero vivía dentro del punto 3, acotado en su encabezado a
«para una GESTIÓN: reservar, pedir cita, rellenar un formulario, tramitar». Una búsqueda cae en la otra rama.
**Misma forma que V2-257 y que V2-277: la instrucción correcta, en la rama equivocada.**

Por eso el guarda mira el prompt RENDERIZADO y no el fichero: que la orden exista en `dispatch_prompts.py` es
justo lo que ya pasaba el día del fallo. Lo que hay que afirmar es que LLEGA, y que llega UNA vez.
"""
import re

from nucleo import dispatch_prompts as dp

ORDEN = "LO QUE AVERIGUAS SE GUARDA"
OBJETIVO = "Busca un coche de segunda mano diésel por menos de 12.000 €"


def _render(brief=None):
    return dp._web_prompt(OBJETIVO, "", brief)


def test_la_orden_de_guardar_LLEGA_al_prompt_renderizado():
    """Las dos rutas reales del builder: con brief de investigación y sin él."""
    for brief in (None, {"baremo": "precio y km"}):
        txt = _render(brief)
        assert ORDEN in txt, f"el worker no recibe la orden de guardar (brief={bool(brief)})"
        assert "mem_cli remember" in txt


def test_la_orden_NO_vive_dentro_de_la_rama_de_GESTION():
    """El defecto exacto. El punto 3 se abre con «para una GESTIÓN: …» y ahí dentro estaba la única orden de
    guardar; una BÚSQUEDA nunca la leía como suya. Se mide por POSICIÓN, que es lo que el fallo tenía de malo."""
    txt = _render()
    abre_gestion = txt.index("para una GESTIÓN")
    cierra = txt.index("BUSCAR/COMPARAR", abre_gestion)
    pos = txt.index(ORDEN)
    assert not (abre_gestion < pos < cierra), (
        "la orden de guardar volvió a quedar ENCERRADA en la rama de gestión: una búsqueda no la lee como suya")


def test_es_UNA_instruccion_con_la_bifurcacion_dentro_y_no_una_por_rama():
    """Norma de la casa (V2-226, y ya costó V2-224): dos órdenes en dos sitios salen a cara o cruz y se separan
    la una de la otra sin avisar. La bifurcación va DENTRO del imperativo."""
    txt = _render()
    assert txt.count(ORDEN) == 1, "la orden aparece más de una vez: se duplicó en vez de bifurcarse dentro"
    imperativos = len(re.findall(r"GUARDA cada dato que reúnas", txt))
    assert imperativos == 0, "volvió el imperativo viejo de la rama de gestión, en paralelo al nuevo"
    bloque = txt[txt.index(ORDEN):txt.index(ORDEN) + 1200]
    assert "en una GESTIÓN" in bloque and "en una BÚSQUEDA" in bloque, (
        "el imperativo no lleva su bifurcación dentro: sin las dos ramas nombradas, cada worker adivina")


def test_la_orden_dice_tambien_lo_que_NO_se_guarda():
    """Sin techo, «guarda lo que averigües» son las 40 filas de un listado y la memoria se vuelve ruido para
    todos. El límite viaja DENTRO del mismo imperativo, no como una segunda regla que se pueda perder."""
    txt = _render()
    bloque = txt[txt.index(ORDEN):txt.index(ORDEN) + 1200]
    assert "NO se guarda" in bloque, "la orden no pone techo: invita a volcar el listado entero"
    assert "he abierto" in bloque, "sin un ejemplo de lo que NO es un hallazgo, el techo es abstracto"


def test_el_catalogo_de_puentes_no_lleva_una_SEGUNDA_media_orden():
    """La línea del catálogo describe la capacidad; el porqué y el qué viven UNA vez, en el imperativo. Dos
    mitades en dos sitios es exactamente cómo una decisión se separa de sí misma."""
    txt = _render()
    catalogo = [l for l in txt.splitlines() if l.strip().startswith("• GUARDAR un dato")]
    assert len(catalogo) == 1, f"la entrada de catálogo se duplicó o desapareció: {catalogo}"
    assert "para no volver a pedirlo" not in catalogo[0], (
        "la entrada de catálogo volvió a llevar su propio motivo: media instrucción suelta lejos de la otra mitad")
