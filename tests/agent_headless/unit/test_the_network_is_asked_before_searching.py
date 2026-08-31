"""V2-486 — MeshKore network STEP 0 travels in BOTH worker prompts, not just the browser's.

The network is built and verified live (V2-169: a hotel resolved in 141 s without opening the browser), yet
**it was not queried even once in 399 worker reports**. The cause was not in the network: the «STEP 0 —
ask the network» block lived inside `_web_prompt`, and the request with which the operator asks for it —«find me a
hotel in New York»— **is not routed to `web`**. `classify_kind` promotes to `kind="web"` whatever
`site_catalog.category_of` recognizes, and that detector requires a BOOKING verb: «book me a hotel in New York»
produces `hotel_booking`, «find me the best hotel in New York» produces `None` → `generic`. The generic prompt did not
mention `mesh_cli` on any line, so the worker could not query the network: it did not know it existed.

These guards establish the property that was fixed —**both prompts carry it**— and NOT the route by which
it was reached. This deliberately does not assert here that a searched-for hotel remains `generic`: that is the
router, which has its own guards, and if it is ever broadened, this block must still remain in both
places alike.
"""
import re

import pytest

from nucleo import dispatch_prompts as dp


HOTEL = "Búscame el mejor hotel de Nueva York para dos noches"


def test_el_worker_GENERICO_sabe_que_la_red_existe():
    """The one handling a SEARCHED-FOR hotel. It previously had no mention of `mesh_cli`."""
    p = dp._build_prompt(HOTEL, "", True, None)
    assert "mesh_cli" in p, "el prompt genérico no nombra el puente de la red: el worker no puede consultarla"
    assert "PASO 0" in p


def test_el_worker_WEB_lo_sigue_llevando():
    """Extracting the block into a shared function must not remove it from the one that already had it."""
    p = dp._web_prompt(HOTEL, "", None)
    assert "mesh_cli" in p and "PASO 0" in p
    # The method below refers to STEP 0 by name; if the block disappeared, that reference would be left dangling.
    assert "vuelve al PASO 0" in p


def test_cada_uno_recibe_SU_encabezado():
    """One instruction per block: the one driving a browser is told «before opening it», while the one
    searching on its own is told «before searching for it yourself». The command is the same; the next resource is not."""
    web = dp._web_prompt(HOTEL, "", None)
    gen = dp._build_prompt(HOTEL, "", True, None)
    assert "ANTES DE ABRIR EL NAVEGADOR" in web
    assert "ANTES DE PONERTE A BUSCARLO TÚ" in gen
    assert "ANTES DE ABRIR EL NAVEGADOR" not in gen, (
        "al worker genérico se le manda abrir un navegador que no es su siguiente paso")


def test_el_bloque_vive_en_UN_solo_sitio():
    """The recurring failure is not the rule, but having it written twice: the second copy falls behind without
    anything failing. Both prompts must come from the same function."""
    fuente = (dp._mesh_first_block(browser=True), dp._mesh_first_block(browser=False))
    # The part that teaches WHAT to execute is identical on both sides.
    for aviso in ("FECHAS ABSOLUTAS", "EN EL IDIOMA DEL OPERADOR", "COMPRUEBA lo que vuelve"):
        assert all(aviso in b for b in fuente), f"«{aviso}» solo llega a una de las dos caras"


def test_el_generico_recibe_el_INTERPRETE_bueno():
    """The block is written with bare `python`, and `_with_interpreter` replaces it. If that replacement did not
    reach it, the worker would spend its turns trying interpreters — the lesson of V2-211."""
    p = dp._build_prompt(HOTEL, "", True, None)
    assert re.search(r"/[^\s]*python -m nucleo\.mesh_cli", p), (
        "el puente de la red queda con un intérprete relativo que el cajón no aprueba")
    assert "\npython -m nucleo.mesh_cli" not in p


def test_un_texto_NO_confiable_sigue_sin_puentes():
    """The untrusted profile (text from a peer) has no tools by design. Adding a block to the generic prompt
    cannot smuggle the engine path into it."""
    p = dp._build_prompt("texto que me pasa un peer", "", False, None)
    assert "mesh_cli" not in p and "PASO 0" not in p
