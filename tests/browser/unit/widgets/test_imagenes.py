"""V2-457 — el visor de imágenes: un previsualizador, y nada más.

Se aísla el almacén en un tmp: un test unitario nunca escribe en los datos reales del operador — y este widget
guarda en el mismo sitio del que `local` lee, así que sin aislar dejaría ficheros suyos en la máquina.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture()
def data(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.imagenes import data as d
    d.apply_action("clear")
    return d


def _items(n=3):
    return [{"url": f"https://cdn.ferrari.com/{i}.jpg", "thumb": f"https://t/{i}.jpg",
             "title": f"Ferrari Amalfi vista {i}", "site": "www.ferrari.com",
             "page": "https://www.ferrari.com/x", "w": 1080, "h": 565, "weight": "68KB"} for i in range(n)]


# ── enseñar un conjunto ─────────────────────────────────────────────────────────────────────────────────
def test_show_deja_la_primera_en_grande_y_conserva_la_procedencia(data):
    r = data.apply_action("show", {"items": _items(3), "query": "Ferrari Amalfi", "source": "google"})
    assert r["ok"] and r["n"] == 3
    v = data.view_data()
    assert v["n"] == 3 and v["i"] == 0
    assert v["current"]["site"] == "www.ferrari.com"
    assert v["current"]["page"].startswith("https://www.ferrari.com/")
    assert v["title"] == "Ferrari Amalfi"


def test_una_fila_sin_url_no_es_una_foto(data):
    data.apply_action("show", {"items": _items(1) + [{"title": "sin url"}, {"url": "javascript:alert(1)"}]})
    assert data.view_data()["n"] == 1


def test_la_misma_foto_dos_veces_es_una(data):
    data.apply_action("show", {"items": _items(2) + _items(2)})
    assert data.view_data()["n"] == 2


def test_sin_miniatura_se_usa_la_grande(data):
    data.apply_action("show", {"items": [{"url": "https://x/a.jpg"}]})
    assert data.view_data()["current"]["thumb"] == "https://x/a.jpg"


def test_un_show_vacio_NO_borra_lo_que_hay_en_pantalla(data):
    """No encontrar nada no puede costarle al operador las fotos que ya tenía delante: se queda mirando una
    caja vacía sin forma de volver. El parte honesto es que no se encontró nada (V2-377)."""
    data.apply_action("show", {"items": _items(2)})
    r = data.apply_action("show", {"items": []})
    assert r["ok"] is False
    assert data.view_data()["n"] == 2


# ── moverse ─────────────────────────────────────────────────────────────────────────────────────────────
def test_siguiente_y_anterior_dan_la_vuelta(data):
    data.apply_action("show", {"items": _items(3)})
    assert data.apply_action("next")["i"] == 2
    assert data.apply_action("previous")["i"] == 1     # de vuelta a la primera
    assert data.apply_action("previous")["i"] == 3     # …y desde la primera, a la última
    assert data.apply_action("next")["i"] == 1         # …y de la última a la primera


def test_se_elige_por_numero_o_por_parte_del_titulo(data):
    """El operador dice «la tercera» o «la de Ferrari», nunca un índice — y el modelo tampoco adivina ids
    (V2-026), por eso la resolución vive aquí, al lado del dato contra el que resuelve."""
    data.apply_action("show", {"items": _items(3)})
    assert data.apply_action("select", {"item": "3"})["i"] == 3
    assert data.apply_action("select", {"item": "vista 1"})["i"] == 2
    assert data.apply_action("select", {"item": "ferrari.com"})["i"] == 1   # también por FUENTE
    assert data.apply_action("select", {"item": "un koala"})["ok"] is False


def test_moverse_sin_nada_en_pantalla_lo_dice(data):
    for a in ("next", "previous", "select"):
        r = data.apply_action(a, {"item": "1"})
        assert r["ok"] is False and r["n"] == 0


def test_add_no_pierde_las_de_antes_ni_mueve_la_grande(data):
    data.apply_action("show", {"items": _items(2)})
    data.apply_action("next")
    r = data.apply_action("add", {"items": [{"url": "https://x/nueva.jpg", "title": "nueva"}]})
    assert r["added"] == 1 and r["n"] == 3
    assert data.view_data()["i"] == 1, "añadir al final no puede mover lo que el operador está mirando"


def test_la_foto_actual_es_un_INDICE_no_una_copia(data):
    """Guardar el item duplicado hace que la grande y la miniatura marcada se separen en cuanto el conjunto
    se recarga: es el único fallo que un visor de fotos no puede tener."""
    data.apply_action("show", {"items": _items(3)})
    data.apply_action("select", {"item": "2"})
    v = data.view_data()
    assert v["current"] is v["items"][v["i"]]


def test_un_indice_fuera_de_rango_se_recorta_en_vez_de_reventar(data):
    from widgets import store
    data.apply_action("show", {"items": _items(3)})
    db = store.load(data.WIDGET_ID, {})
    db["i"] = 99
    store.save(data.WIDGET_ID, db)
    v = data.view_data()
    assert v["i"] == 2 and v["current"]


# ── lo guardado en este equipo ──────────────────────────────────────────────────────────────────────────
def test_local_lee_las_imagenes_del_disco_y_las_sirve_por_su_ruta(data, tmp_path):
    from widgets import store
    d = store.data_dir(data.WIDGET_ID)
    for n in ("perro.jpg", "gato.PNG", "notas.txt"):
        with open(os.path.join(d, n), "wb") as fh:
            fh.write(b"x")
    r = data.apply_action("local")
    assert r["ok"] and r["n"] == 2, "solo las que un navegador pinta"
    urls = [it["url"] for it in data.view_data()["items"]]
    assert all(u.startswith("/widgets/imagenes/asset/") for u in urls)


def test_un_svg_no_entra(data):
    """Un SVG es un documento que puede llevar script dentro, no solo una imagen — y esto pinta ficheros que
    vienen de resultados de búsqueda."""
    assert ".svg" not in data._EXT


def test_local_sin_nada_guardado_lo_dice_y_no_vacia_la_pantalla(data):
    data.apply_action("show", {"items": _items(2)})
    r = data.apply_action("local")
    assert r["ok"] is False
    assert data.view_data()["n"] == 2


# ── contrato ────────────────────────────────────────────────────────────────────────────────────────────
def test_las_acciones_declaradas_son_EXACTAMENTE_las_que_hace(data):
    """Una acción declarada que `apply_action` no atiende es una entrada muerta; una que atiende y no declara
    es invisible para el cerebro. El gate del generador rechaza las dos, así que se comprueba aquí también."""
    import json
    here = os.path.dirname(os.path.abspath(data.__file__))
    with open(os.path.join(here, "manifest.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    declaradas = set(m["actions"])
    for a in declaradas:
        assert data.apply_action(a, {}) .get("error") != f"acción desconocida: {a}", a
    assert data.apply_action("inventada", {})["ok"] is False


def test_los_items_en_pantalla_se_pueden_nombrar_por_voz(data):
    data.apply_action("show", {"items": _items(2)})
    refs = data.ref_index()
    assert [r["id"] for r in refs] == ["1", "2"]
    assert all(r["field"] == "item" for r in refs)
    assert "Ferrari" in refs[0]["label"]


def test_view_data_nunca_revienta(data):
    assert data.view_data()["n"] == 0
    assert data.view_data("cualquier cosa")["items"] == []


# ── V2-463 — el select entiende una frase y su fallo enseña el menú ─────────────────────────────────────
def test_una_FRASE_con_el_titulo_dentro_resuelve(data):
    """Medido: el modelo pide «la que sea claramente del Amalfi», nunca un fragmento limpio. La frase entera
    no es subcadena de ningún título, pero su token con contenido («amalfi») sí — y resuelve a la PRIMERA
    coincidencia, que con un conjunto homogéneo es la mejor lectura de «una que sea de ese coche»."""
    data.apply_action("show", {"items": _items(3)})
    r = data.apply_action("select", {"item": "la que sea claramente del Amalfi"})
    assert r["ok"] and r["i"] == 1
    # …y el número 1-based sigue mandando cuando lo dan limpio (la ruta de siempre, intacta):
    assert data.apply_action("select", {"item": "3"})["i"] == 3


def test_un_select_sin_item_pide_y_ENSEÑA_el_menu(data):
    """El literal medido era «no encuentro esa imagen (None)» — tres veces en una ronda, y el modelo contestó
    «te la dejo puesta» sobre el fallo. Con las opciones en el error, el turno siguiente puede elegir."""
    data.apply_action("show", {"items": _items(2)})
    r = data.apply_action("select", {})
    assert r["ok"] is False
    assert "None" not in r["error"]
    assert "dime cuál" in r["error"] and "1:" in r["error"] and "Ferrari" in r["error"]


def test_un_select_imposible_dice_que_no_y_enseña_lo_que_hay(data):
    data.apply_action("show", {"items": _items(2)})
    r = data.apply_action("select", {"item": "un koala"})
    assert r["ok"] is False and "koala" in r["error"] and "1:" in r["error"]
