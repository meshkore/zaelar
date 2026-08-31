"""What a worker finds out has to survive being killed (V2-344, 2026-08-26).

Measured by the harness in `search-buy-used-car` (session 7575e81a): worker 1 reached milanuncios and captured data, then died
after 2 min; worker 2 died at 8; worker 3 delivered. In the studio DB, the ONLY row with `source=worker:*` in
the entire 13:33-13:54 window is the one from the worker that delivered — **the first two workers' 21 minutes left no trace**, and
each restart navigated, searched, and re-filtered from scratch.

The capability was intact (the `mem_cli` bridge travels in the prompt, the route requires a token per task, and the precision
gate PASSES findings). What was missing was ASKING FOR IT — and the instruction existed: it literally said “even if the flow
restarts,” i.e. the anti-restart protection, but it lived inside point 3, narrowed in its heading to
“for a TRANSACTION: make a reservation, request an appointment, fill out a form, process paperwork.” A search falls into the other branch.
**Same pattern as V2-257 and V2-277: the right instruction in the wrong branch.**

That is why the guard checks the RENDERED prompt rather than the file: the instruction existing in `dispatch_prompts.py` is
exactly what was already true on the day of the failure. What must be asserted is that it ARRIVES, and that it arrives ONCE.
"""
import re

from nucleo import dispatch_prompts as dp

ORDEN = "LO QUE AVERIGUAS SE GUARDA"
OBJETIVO = "Busca un coche de segunda mano diésel por menos de 12.000 €"


def _render(brief=None):
    return dp._web_prompt(OBJETIVO, "", brief)


def test_la_orden_de_guardar_LLEGA_al_prompt_renderizado():
    """The builder's two real routes: with and without a research brief."""
    for brief in (None, {"baremo": "precio y km"}):
        txt = _render(brief)
        assert ORDEN in txt, f"el worker no recibe la orden de guardar (brief={bool(brief)})"
        assert "mem_cli remember" in txt


def test_la_orden_NO_vive_dentro_de_la_rama_de_GESTION():
    """The exact defect. Point 3 opens with “for a TRANSACTION: …”, and the only instruction to save data was inside it;
    a SEARCH never read it as applying to itself. This is measured by POSITION, which is what was wrong with the failure."""
    txt = _render()
    abre_gestion = txt.index("para una GESTIÓN")
    cierra = txt.index("BUSCAR/COMPARAR", abre_gestion)
    pos = txt.index(ORDEN)
    assert not (abre_gestion < pos < cierra), (
        "la orden de guardar volvió a quedar ENCERRADA en la rama de gestión: una búsqueda no la lee como suya")


def test_es_UNA_instruccion_con_la_bifurcacion_dentro_y_no_una_por_rama():
    """House rule (V2-226, and V2-224 already cost us): two instructions in two places become a coin toss and separate
    from each other without warning. The branching belongs INSIDE the imperative."""
    txt = _render()
    assert txt.count(ORDEN) == 1, "la orden aparece más de una vez: se duplicó en vez de bifurcarse dentro"
    imperativos = len(re.findall(r"GUARDA cada dato que reúnas", txt))
    assert imperativos == 0, "volvió el imperativo viejo de la rama de gestión, en paralelo al nuevo"
    bloque = txt[txt.index(ORDEN):txt.index(ORDEN) + 1200]
    assert "en una GESTIÓN" in bloque and "en una BÚSQUEDA" in bloque, (
        "el imperativo no lleva su bifurcación dentro: sin las dos ramas nombradas, cada worker adivina")


def test_la_orden_dice_tambien_lo_que_NO_se_guarda():
    """Without a ceiling, “save whatever you find out” means the 40 rows in a listing, and memory becomes noise for
    everyone. The limit travels INSIDE the same imperative, not as a second rule that can be lost."""
    txt = _render()
    bloque = txt[txt.index(ORDEN):txt.index(ORDEN) + 1200]
    assert "NO se guarda" in bloque, "la orden no pone techo: invita a volcar el listado entero"
    assert "he abierto" in bloque, "sin un ejemplo de lo que NO es un hallazgo, el techo es abstracto"


def test_el_catalogo_de_puentes_no_lleva_una_SEGUNDA_media_orden():
    """The catalog line describes the capability; the why and the what live ONCE, in the imperative. Two
    halves in two places are exactly how a decision separates from itself."""
    txt = _render()
    catalogo = [l for l in txt.splitlines() if l.strip().startswith("• GUARDAR un dato")]
    assert len(catalogo) == 1, f"la entrada de catálogo se duplicó o desapareció: {catalogo}"
    assert "para no volver a pedirlo" not in catalogo[0], (
        "la entrada de catálogo volvió a llevar su propio motivo: media instrucción suelta lejos de la otra mitad")
