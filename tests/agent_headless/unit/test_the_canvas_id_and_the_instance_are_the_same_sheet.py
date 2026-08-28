"""`results::82d86e-2` y `82d86e-2` son la misma hoja dicha de dos maneras, y una devolvía vacío.

El canvas nombra una instancia `results::<corr>`; `view_data` espera la INSTANCIA suelta. Sin tolerar la
primera forma, el saneado se comía los dos puntos y componía la clave `results--results82d86e-2`, que **no
existe** — así que `view_data` devolvía una hoja VACÍA.

La tolerancia vive en `sheet_key` y no en `_safe_sheet`: cabe en la línea que ya había, y `widgets/results/
data.py` es un fichero-dios del trinquete —1030 líneas de techo— que dos intentos anteriores se saltaron.

Y una hoja vacía es indistinguible de «el encargo aún no ha encontrado nada»: el fallo no hace ruido, cambia
la respuesta. Es la misma familia que llevó toda la noche: *el sistema tiene el dato y contesta que no.*

Encontrado el 2026-08-28 persiguiendo por qué el bloque de filas del prompt no ha disparado NI UNA VEZ en 45
rondas medidas. **No está probado que sea la causa de aquello** —el camino que se midió pasaba ya la
instancia suelta— pero es un pie del que cualquiera puede tirar, y callado.
"""
from __future__ import annotations

from widgets.results import data as D


def test_las_dos_formas_son_la_misma_hoja():
    assert D.sheet_key("results::82d86e-2") == D.sheet_key("82d86e-2") == "results--82d86e-2"


def test_la_hoja_SIN_instancia_no_se_mueve():
    """La hoja pelada es la de siempre, byte por byte: tocarla rompería todo lo que ya está guardado."""
    assert D.sheet_key("") == "results"
    assert D.sheet_key(None) == "results"


def test_solo_se_quita_el_prefijo_PROPIO():
    """Quitar cualquier cosa antes de `::` convertiría la hoja de otro widget en la nuestra."""
    assert D.sheet_key("otro::82d86e-2") != "results--82d86e-2"
    assert "otro" in D.sheet_key("otro::82d86e-2")


def test_el_saneado_sigue_apretado():
    """La clave va a disco: solo alfanuméricos, guion y guion bajo, y acotada."""
    k = D.sheet_key("results::../../etc/passwd")
    assert "/" not in k and ".." not in k
    assert len(D.sheet_key("results::" + "x" * 200)) <= len("results--") + 64
