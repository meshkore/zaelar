"""El puente del worker no hablaba el vocabulario de widgets que el resto del sistema ya tiene.

Cada widget lleva su identidad —id, nombre y alias— y `widgets/registry.py` la construye normalizada para los
26. Lo que no existía era nadie USÁNDOLA desde el lado del worker: `paths.dir_for` casa con la carpeta y nada
más, así que el puente contestaba «el widget «music» no existe» a un nombre que el resto del sistema resuelve
sin pestañear.

Medido el 2026-08-28 en `build-a-video-playlist-from-links` (plató 24/7). El worker pidió `music`; la carpeta
es `musica`. **Y no es solo cosa del inglés**: la misma búsqueda rechazaba `reloj`, que es el nombre castellano
del widget cuya carpeta se llama `clock`.

Importa el doble ahora mismo: el plató US conduce todas sus rondas en inglés, y en inglés es como se está
vendiendo el producto.
"""
from __future__ import annotations

from widgets import naming


def test_el_caso_MEDIDO_resuelve():
    assert naming.resolve("music")[0] == "musica"


def test_y_no_era_solo_el_ingles():
    """`reloj` es castellano y también fallaba: el puente no hablaba el vocabulario en NINGÚN idioma."""
    assert naming.resolve("reloj")[0] == "clock"


def test_un_ALIAS_cualquiera_vale():
    assert naming.resolve("playlist")[0] == "musica"


def test_el_id_exacto_gana_sobre_cualquier_alias():
    """Si alguien escribe el id, eso es lo que quiere: un alias de otro widget no puede secuestrarlo."""
    assert naming.resolve("agenda") == ("agenda", [])


def test_lo_que_NO_existe_sigue_sin_existir():
    """La mitad de sensibilidad: un resolutor que encuentra algo siempre es peor que ninguno, porque el
    llamante está a punto de ESCRIBIR en lo que le devuelva."""
    ident, varios = naming.resolve("no-existe-esto-xyz")
    assert ident == "" and varios == []


def test_una_COLISIÓN_es_una_negativa_y_no_una_apuesta():
    """`widgets/aliases.py` garantiza que un alias es de una sola pieza, pero un manifiesto editado a mano
    puede romperlo — y elegir uno de dos widgets donde se va a escribir es peor que decir que no."""
    import widgets.registry as R
    orig = R.registry
    try:
        R.registry = lambda: [{"id": "uno", "name": "Uno", "aliases": ["compartido"]},
                              {"id": "dos", "name": "Dos", "aliases": ["compartido"]}]
        ident, varios = naming.resolve("compartido")
        assert ident == "" and varios == ["dos", "uno"]
        assert "vale para varios" in naming.not_found("compartido", varios)
    finally:
        R.registry = orig


def test_el_no_existe_DICE_los_que_hay():
    """Un nombre rechazado a secas deja al worker adivinando, y lo que hace entonces es reintentar el mismo —
    medido esta misma noche en otras tres puertas del sistema."""
    msg = naming.not_found("calendar")
    assert "no existe" in msg and "los que hay" in msg and "agenda" in msg


def test_un_registro_ILEGIBLE_no_tumba_al_llamante():
    import widgets.registry as R
    orig = R.registry
    try:
        R.registry = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        assert naming.resolve("music") == ("", [])
        assert "no existe" in naming.not_found("music")
    finally:
        R.registry = orig


def test_las_DOS_puertas_del_worker_lo_usan():
    """La fontanería: `read_widget` y la de datos son dos sitios distintos, y arreglar uno solo deja al worker
    resolviendo un nombre para leer y fallando con el mismo para escribir."""
    from pathlib import Path
    src = Path("nucleo/worker_api.py").read_text(encoding="utf-8")
    assert src.count("from widgets import naming as _nm") == 2
    assert "el widget «{wid}» no existe" not in src, "queda una puerta con el mensaje viejo"
