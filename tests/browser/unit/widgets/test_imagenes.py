"""V2-457 — the image viewer: a previewer, and nothing more.

The store is isolated in a tmp directory: a unit test never writes to the operator's real data — and this widget
saves in the same place from which `local` reads, so without isolation it would leave its files on the machine.
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


# ── show a set ───────────────────────────────────────────────────────────────────────────────────────────
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
    """Finding nothing must not cost the operator the photos that were already in front of them: they would be left looking at an
    empty box with no way back. The honest report is that nothing was found (V2-377)."""
    data.apply_action("show", {"items": _items(2)})
    r = data.apply_action("show", {"items": []})
    assert r["ok"] is False
    assert data.view_data()["n"] == 2


# ── navigate ─────────────────────────────────────────────────────────────────────────────────────────────
def test_siguiente_y_anterior_dan_la_vuelta(data):
    data.apply_action("show", {"items": _items(3)})
    assert data.apply_action("next")["i"] == 2
    assert data.apply_action("previous")["i"] == 1     # back to the first
    assert data.apply_action("previous")["i"] == 3     # …and from the first, to the last
    assert data.apply_action("next")["i"] == 1         # …and from the last to the first


def test_se_elige_por_numero_o_por_parte_del_titulo(data):
    """The operator says «the third one» or «the Ferrari one», never an index — and the model does not guess ids
    (V2-026), which is why resolution lives here, next to the data against which it resolves."""
    data.apply_action("show", {"items": _items(3)})
    assert data.apply_action("select", {"item": "3"})["i"] == 3
    assert data.apply_action("select", {"item": "vista 1"})["i"] == 2
    assert data.apply_action("select", {"item": "ferrari.com"})["i"] == 1   # also by SOURCE
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
    """Storing the duplicated item makes the large image and the selected thumbnail diverge as soon as the set
    reloads: it is the one failure a photo viewer cannot have."""
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


# ── what is stored on this device ────────────────────────────────────────────────────────────────────────
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
    """An SVG is a document that may contain a script, not just an image — and this renders files that
    come from search results."""
    assert ".svg" not in data._EXT


def test_local_sin_nada_guardado_lo_dice_y_no_vacia_la_pantalla(data):
    data.apply_action("show", {"items": _items(2)})
    r = data.apply_action("local")
    assert r["ok"] is False
    assert data.view_data()["n"] == 2


# ── contract ─────────────────────────────────────────────────────────────────────────────────────────────
def test_las_acciones_declaradas_son_EXACTAMENTE_las_que_hace(data):
    """A declared action that `apply_action` does not handle is a dead entry; one that it handles but does not declare
    is invisible to the brain. The generator gate rejects both, so this is checked here as well."""
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


# ── V2-463 — select understands a sentence and its failure shows the menu ───────────────────────────────
def test_una_FRASE_con_el_titulo_dentro_resuelve(data):
    """Measured: the model asks for «the one that is clearly from the Amalfi», never a clean fragment. The full sentence
    is not a substring of any title, but its meaningful token («amalfi») is — and it resolves to the FIRST
    match, which with a homogeneous set is the best interpretation of «one that is from that car»."""
    data.apply_action("show", {"items": _items(3)})
    r = data.apply_action("select", {"item": "la que sea claramente del Amalfi"})
    assert r["ok"] and r["i"] == 1
    # …and the 1-based number still takes precedence when given cleanly (the usual path, unchanged):
    assert data.apply_action("select", {"item": "3"})["i"] == 3


def test_un_select_sin_item_pide_y_ENSEÑA_el_menu(data):
    """The measured literal was «I can't find that image (None)» — three times in one round, and the model replied
    «I'll leave it displayed» after the failure. With the options in the error, the next turn can choose."""
    data.apply_action("show", {"items": _items(2)})
    r = data.apply_action("select", {})
    assert r["ok"] is False
    assert "None" not in r["error"]
    assert "dime cuál" in r["error"] and "1:" in r["error"] and "Ferrari" in r["error"]


def test_un_select_imposible_dice_que_no_y_enseña_lo_que_hay(data):
    data.apply_action("show", {"items": _items(2)})
    r = data.apply_action("select", {"item": "un koala"})
    assert r["ok"] is False and "koala" in r["error"] and "1:" in r["error"]


# ── V2-465 — keyboard ────────────────────────────────────────────────────────────────────────────────────
def test_las_flechas_pasan_fotos_y_no_roban_al_que_escribe():
    """The third of the keyless family: `musica` and `youtube` already had them. The SOURCE is checked
    because the behavior lives in the browser — and both halves matter: that the arrows work, and
    that they are NOT taken away from a text field (the chat lives on the same screen)."""
    import pathlib
    js = (pathlib.Path(__file__).resolve().parents[4] / "widgets" / "imagenes"
          / "widget.js").read_text(encoding="utf-8")
    assert "ArrowRight" in js and "ArrowLeft" in js
    assert 'el.onkeydown' in js, "se escucha en la TARJETA, no en document: dos visores no se pelean"
    assert "INPUT" in js and "isContentEditable" in js, "no robar teclas a quien escribe"


# ── V2-589: the slideshow the model promised four times with nothing behind it ───────────────────────────
# Session 0e3a42d6 (2026-09-05): «voy a ponerlas en modo presentación» with ZERO tool calls, then «Hecho.»
# twice, then `next` advancing ONE photo («Solo ha pasado una foto»). The capability did not exist, so
# narrating was the only move available (V2-540's law). The server owns `auto`/`every_s`/the index;
# widget.js only re-arms a one-shot timer that fires the ordinary `next`.

def test_slideshow_enciende_el_pase_y_view_data_lo_publica(data):
    data.apply_action("show", {"items": _items(3)})
    r = data.apply_action("slideshow", {})
    assert r["ok"] and r["auto"] is True and r["every_s"] == 6
    v = data.view_data()
    assert v["auto"] is True and v["every_s"] == 6


def test_el_ritmo_se_acota_a_2_60_segundos(data):
    data.apply_action("show", {"items": _items(3)})
    assert data.apply_action("slideshow", {"every_s": 1})["every_s"] == 2
    assert data.apply_action("slideshow", {"every_s": 300})["every_s"] == 60
    assert data.apply_action("slideshow", {"every_s": "rápido"})["every_s"] == 60  # unreadable keeps the last


def test_sin_fotos_o_con_una_sola_se_niega_y_lo_dice(data):
    r = data.apply_action("slideshow", {})
    assert not r["ok"] and "no hay" in r["error"]
    data.apply_action("show", {"items": _items(1)})
    r = data.apply_action("slideshow", {})
    assert not r["ok"] and "una imagen" in r["error"]


def test_elegir_una_foto_PARA_el_pase(data):
    """A viewer that keeps advancing after the operator picked a photo fights the operator (V2-551)."""
    data.apply_action("show", {"items": _items(3)})
    data.apply_action("slideshow", {})
    data.apply_action("select", {"item": "2"})
    assert data.view_data()["auto"] is False


def test_next_y_previous_NO_paran_el_pase(data):
    data.apply_action("show", {"items": _items(3)})
    data.apply_action("slideshow", {})
    data.apply_action("next")
    assert data.view_data()["auto"] is True


def test_un_set_nuevo_arranca_QUIETO_y_stop_para(data):
    data.apply_action("show", {"items": _items(3)})
    data.apply_action("slideshow", {})
    data.apply_action("show", {"items": _items(2)})
    assert data.view_data()["auto"] is False
    data.apply_action("slideshow", {})
    r = data.apply_action("slideshow_stop", {})
    assert r["ok"] and r["was_running"] is True and data.view_data()["auto"] is False


def test_el_pase_es_PRODUCCION_y_el_manifest_lo_declara(data):
    """The V2-465 judgement revisited: a STILL photo does not produce, an AUTO-ADVANCING viewer does — so the
    ⏻ global stop must reach it. `producers` reads active_when against view_data, and suspend must be a
    declared action or the global stop dispatches into the void."""
    import json
    from pathlib import Path
    man = json.loads((Path(__file__).resolve().parents[4] / "widgets/imagenes/manifest.json")
                     .read_text(encoding="utf-8"))
    rt = man.get("runtime") or {}
    assert "slideshow" in (rt.get("produce") or []), "the ⏻ gate no longer knows the pase produces"
    assert rt.get("suspend") in man["actions"], "suspend must be a DECLARED action"
    assert rt.get("active_when") == {"auto": True}


def test_el_widget_arma_UN_timer_de_un_disparo_que_llama_a_next():
    """Source-level: the timer must go through ctx.action('next') — the same path a click or the voice takes —
    and must be a one-shot re-armed per render, never an interval that can leak."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[4] / "widgets/imagenes/widget.js").read_text(encoding="utf-8")
    assert "_hbImgAuto" in src and "setTimeout" in src
    assert "setInterval" not in src, "an interval leaks across renders; the one-shot re-arms from the data cycle"
    assert 'ctx.action("next")' in src.split("_hbImgAuto", 1)[1][:400], "the pase must advance through the server"
    assert "ctx.running===false" in src, "a stopped agent must arm nothing (V2-092)"
