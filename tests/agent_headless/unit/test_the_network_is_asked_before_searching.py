"""V2-486 — el PASO 0 de la red MeshKore viaja en LOS DOS prompts de worker, no solo en el del navegador.

La red está construida y verificada en vivo (V2-169: un hotel resuelto en 141 s sin abrir el navegador) y aun
así **no se consultó ni una vez en 399 informes de worker**. La causa no estaba en la red: el bloque «PASO 0 —
pregunta a la red» vivía dentro de `_web_prompt`, y el encargo con el que el operador lo pide —«búscame un
hotel en Nueva York»— **no se enruta a `web`**. `classify_kind` promociona a `kind="web"` lo que
`site_catalog.category_of` reconoce, y ese detector pide un verbo de RESERVA: «resérvame hotel en Nueva York»
sale `hotel_booking`, «búscame el mejor hotel de Nueva York» sale `None` → `generic`. El prompt genérico no
nombraba `mesh_cli` en ninguna línea, así que el worker no podía descartar la red: no sabía que existía.

Estos guardas fijan la propiedad por la que se arregló —**los dos prompts la llevan**— y NO la ruta por la que
se llegó a ella. Deliberadamente no se afirma aquí que un hotel buscado siga siendo `generic`: eso es el
enrutador, tiene sus propios guardas, y si algún día se ensancha, este bloque debe seguir estando en los dos
sitios igual.
"""
import re

import pytest

from nucleo import dispatch_prompts as dp


HOTEL = "Búscame el mejor hotel de Nueva York para dos noches"


def test_el_worker_GENERICO_sabe_que_la_red_existe():
    """El que atiende un hotel BUSCADO. Iba sin una sola mención de `mesh_cli`."""
    p = dp._build_prompt(HOTEL, "", True, None)
    assert "mesh_cli" in p, "el prompt genérico no nombra el puente de la red: el worker no puede consultarla"
    assert "PASO 0" in p


def test_el_worker_WEB_lo_sigue_llevando():
    """Extraer el bloque a una función compartida no puede quitárselo a quien ya lo tenía."""
    p = dp._web_prompt(HOTEL, "", None)
    assert "mesh_cli" in p and "PASO 0" in p
    # El método de abajo se refiere al PASO 0 por su nombre; si el bloque se fuera, esa referencia quedaría coja.
    assert "vuelve al PASO 0" in p


def test_cada_uno_recibe_SU_encabezado():
    """Una sola instrucción por bloque: al que conduce un navegador se le dice «antes de abrirlo», y al que
    busca por su cuenta «antes de buscarlo tú». La orden es la misma; el siguiente recurso, no."""
    web = dp._web_prompt(HOTEL, "", None)
    gen = dp._build_prompt(HOTEL, "", True, None)
    assert "ANTES DE ABRIR EL NAVEGADOR" in web
    assert "ANTES DE PONERTE A BUSCARLO TÚ" in gen
    assert "ANTES DE ABRIR EL NAVEGADOR" not in gen, (
        "al worker genérico se le manda abrir un navegador que no es su siguiente paso")


def test_el_bloque_vive_en_UN_solo_sitio():
    """El fallo que se repite no es la regla, es tenerla escrita dos veces: la segunda copia se queda atrás sin
    que nada falle. Los dos prompts han de salir de la misma función."""
    fuente = (dp._mesh_first_block(browser=True), dp._mesh_first_block(browser=False))
    # La parte que enseña QUÉ ejecutar es idéntica entre las dos caras.
    for aviso in ("FECHAS ABSOLUTAS", "EN EL IDIOMA DEL OPERADOR", "COMPRUEBA lo que vuelve"):
        assert all(aviso in b for b in fuente), f"«{aviso}» solo llega a una de las dos caras"


def test_el_generico_recibe_el_INTERPRETE_bueno():
    """El bloque se escribe con `python` a secas y `_with_interpreter` lo sustituye. Si esa sustitución no
    alcanzara, el worker se pasaría los turnos probando intérpretes — la lección de V2-211."""
    p = dp._build_prompt(HOTEL, "", True, None)
    assert re.search(r"/[^\s]*python -m nucleo\.mesh_cli", p), (
        "el puente de la red queda con un intérprete relativo que el cajón no aprueba")
    assert "\npython -m nucleo.mesh_cli" not in p


def test_un_texto_NO_confiable_sigue_sin_puentes():
    """El perfil untrusted (texto de un peer) va sin herramientas por construcción. Añadir un bloque al prompt
    genérico no puede colarle la ruta del engine."""
    p = dp._build_prompt("texto que me pasa un peer", "", False, None)
    assert "mesh_cli" not in p and "PASO 0" not in p
