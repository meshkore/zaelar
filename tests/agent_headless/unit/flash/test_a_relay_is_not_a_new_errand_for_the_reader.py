"""En un RELEVO, el sello de la pestaña apunta a la caja nueva y los hallazgos siguen en la heredada.

Medido el 2026-08-28 en `compare-flights-madrid-lisboa` (plató 24/7, 04:43):

    caja que MIRÓ el bloque vivo ..  f1743e-2   (vacía, siete veces)
    caja que TENÍA las filas ......  f1743e-1
    fuentes .......................  user · worker:1 · worker:2
    turnos ciegos .................  4

La causa la documenta `nucleo/sheets.py` y tiene nombre: **«A RELAY IS NOT A NEW ERRAND»** (medido a su vez en
`cheapest-monitor` el 2026-08-23, con `-1` vacía y `-2` guardando los trece hallazgos). Cuando el proveedor se
queda sin cuota, el relanzamiento del MISMO objetivo **hereda** la hoja de su predecesor — pero el sello de la
pestaña «se escribe una sola vez, en `tasks.create()`» y el relevo crea pestaña nueva. El sello no está
ausente: está **rancio**, y su docstring solo contemplaba lo primero.

Esto arregla el LADO DEL LECTOR y nada más. Quien escribe resuelve por su cuenta, así que ni una fila cambia
de sitio — y ése era el requisito para tocarlo sin el operador delante: equivocarse en el enrutado de
escritura manda los resultados a una caja que nadie mira, que es justo el defecto que se está arreglando.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def _dos_cajas(monkeypatch):
    """Un relevo real: el sello da la caja NUEVA (vacía) y el registro la HEREDADA (con las filas)."""
    from nucleo.flash import errand_sheet as ES
    import widgets.results.data as _rd
    monkeypatch.setattr(ES, "_sheet_of_tab", lambda *_a, **_k: "results::f1743e-2")
    monkeypatch.setattr(ES, "_registro_de_tab", lambda *_a, **_k: "results::f1743e-1")
    contenido = {"results::f1743e-2": {"items": []},
                 "results::f1743e-1": {"items": [{"title": "Iberia directo 21:50", "price": "148 €"}]}}
    monkeypatch.setattr(_rd, "view_data", lambda c, *_a, **_k: contenido.get(c, {"items": []}))


def test_el_caso_MEDIDO_deja_de_ser_ciego(_dos_cajas):
    from nucleo.flash import live_blocks as LB
    assert LB._sheet_has_rows("f1743e-2") is True, "las filas están en la heredada y el prompt decía que no"


def test_y_las_FILAS_salen_de_la_misma_caja_que_la_señal(_dos_cajas):
    """Si la señal dice que hay algo y las líneas salen de otra caja, el prompt afirma que tiene resultados y
    no puede nombrarlos — peor que las dos cosas por separado."""
    from nucleo.flash import live_blocks as LB
    filas = LB._sheet_top_rows("f1743e-2")
    assert filas and "Iberia directo 21:50" in filas[0]


def test_el_ORDEN_no_se_invierte(monkeypatch):
    """El sello sigue siendo la identidad: solo se mira la segunda caja cuando la primera no tiene lo que se
    busca. Invertirlo cambiaría de quién es la hoja, y eso sí toca a quien escribe."""
    from nucleo.flash import errand_sheet as ES
    monkeypatch.setattr(ES, "_sheet_of_tab", lambda *_a, **_k: "results::sello")
    monkeypatch.setattr(ES, "_registro_de_tab", lambda *_a, **_k: "results::registro")
    assert ES.boxes_of_tab("x") == ["results::sello", "results::registro"]


def test_sin_relevo_no_hay_segunda_caja(monkeypatch):
    """La mitad de sensibilidad: en el caso normal las dos vías dan lo mismo y no se duplica."""
    from nucleo.flash import errand_sheet as ES
    monkeypatch.setattr(ES, "_sheet_of_tab", lambda *_a, **_k: "results::unica")
    monkeypatch.setattr(ES, "_registro_de_tab", lambda *_a, **_k: "results::unica")
    assert ES.boxes_of_tab("x") == ["results::unica"]


def test_una_hoja_vacía_de_VERDAD_sigue_diciendo_que_no(monkeypatch):
    """Y la otra mitad, que es la que evita convertir esto en un «siempre hay algo»."""
    from nucleo.flash import errand_sheet as ES
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(ES, "_sheet_of_tab", lambda *_a, **_k: "results::a")
    monkeypatch.setattr(ES, "_registro_de_tab", lambda *_a, **_k: "results::b")
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: {"items": []})
    assert LB._sheet_has_rows("x") is False


def test_el_LECTOR_y_solo_el_lector():
    """El requisito para tocar esto sin el operador delante: quien ESCRIBE no pasa por aquí."""
    import subprocess
    fuera = subprocess.run(["grep", "-rn", "boxes_of_tab", "--include=*.py", "nucleo/", "widgets/"],
                           capture_output=True, text=True).stdout
    ficheros = {l.split(":")[0] for l in fuera.splitlines() if l.strip()}
    assert ficheros <= {"nucleo/flash/errand_sheet.py", "nucleo/flash/live_blocks.py"}, ficheros
