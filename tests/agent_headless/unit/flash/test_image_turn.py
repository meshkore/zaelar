"""V2-457 — enseñar fotos: la ejecución compartida por los dos canales, y lo que se DICE después."""
from __future__ import annotations

import asyncio

from nucleo.flash import image_turn


def _items(n=3):
    return [{"url": f"https://cdn.ferrari.com/{i}.jpg", "thumb": f"https://t/{i}",
             "title": f"Ferrari Amalfi {i}", "site": "www.ferrari.com",
             "page": "https://www.ferrari.com/x", "w": 1080, "h": 565} for i in range(n)]


# ── lo que pidió la tool ────────────────────────────────────────────────────────────────────────────────
def test_lee_la_peticion_y_acota_cuantas():
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "  Ferrari Amalfi "}}]) == {
        "query": "Ferrari Amalfi", "n": image_turn.DEFAULT_N}
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "x", "n": 3}}])["n"] == 3
    # Un `n` disparatado no puede convertir un turno ligero en una carga de cien imágenes, y uno ilegible
    # (el modelo escribe "cinco") cae al defecto en vez de reventar.
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "x", "n": 900}}])["n"] == 24
    # `n: 0` («cero fotos») y `n: "cinco"` son las dos formas de que el modelo se equivoque escribiendo el
    # número, y las dos caen al defecto: enseñar UNA foto no es lo que quiso decir ninguna de ellas.
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "x", "n": 0}}])["n"] == 12
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "x", "n": "cinco"}}])["n"] == 12
    assert image_turn.request_from([])["query"] == ""


# ── ejecución ───────────────────────────────────────────────────────────────────────────────────────────
def test_busca_y_carga_el_visor_y_reporta_lo_que_paso(monkeypatch):
    visto = {}

    async def _images(q, k):
        visto["buscado"] = (q, k)
        return {"query": q, "items": _items(3), "source": "google", "blocked": False}

    async def _brain_action(wid, action, payload):
        visto["cargado"] = (wid, action, len(payload.get("items") or []))
        return {"ok": True, "n": 3}

    monkeypatch.setattr("nucleo.browser_search.images", _images, raising=False)
    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)

    parte = asyncio.run(image_turn.execute("Ferrari Amalfi", 3))
    assert visto["buscado"] == ("Ferrari Amalfi", 3)
    assert visto["cargado"] == ("imagenes", "show", 3)   # el VISOR, jamás la hoja de resultados
    assert parte["ok"] is True and parte["count"] == 3
    assert parte["sites"] == ["www.ferrari.com"]


def test_sin_fotos_no_toca_el_visor_y_lo_dice(monkeypatch):
    """Un `show` vacío BORRARÍA lo que hubiera en pantalla: no encontrar nada no puede costarle al operador
    las fotos que ya tenía delante."""
    async def _images(q, k):
        return {"query": q, "items": [], "source": "google", "blocked": False}

    async def _brain_action(*a, **k):  # pragma: no cover — no debe llamarse
        raise AssertionError("no se toca el visor si no hay fotos")

    monkeypatch.setattr("nucleo.browser_search.images", _images, raising=False)
    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    parte = asyncio.run(image_turn.execute("algo que no existe"))
    assert parte["ok"] is False and parte["count"] == 0


def test_un_fallo_del_navegador_no_tumba_el_turno(monkeypatch):
    async def _boom(q, k):
        raise RuntimeError("chromium muerto")
    monkeypatch.setattr("nucleo.browser_search.images", _boom, raising=False)
    parte = asyncio.run(image_turn.execute("Ferrari"))
    assert parte["ok"] is False and "chromium muerto" in parte["execute_error"]


def test_sin_consulta_no_busca_nada():
    parte = asyncio.run(image_turn.execute("   "))
    assert parte["ok"] is False and parte["count"] == 0


# ── lo que se dice ──────────────────────────────────────────────────────────────────────────────────────
def test_nombra_cuantas_y_de_quien():
    """Se NOMBRA el conjunto por lo mismo que el reproductor nombra el vídeo que cargó (V2-057): deja
    verificar de un vistazo que son las fotos que se pidieron. Y la FUENTE es justo lo que el operador
    valoró de la ruta lenta — una ruta rápida que no pueda decir de quién es la foto cambia lo que le
    importaba por velocidad."""
    dicho = image_turn.spoken_for(
        {"executed": "show_images", "ok": True, "count": 10, "sites": ["www.ferrari.com", "es.wikipedia.org"]}, "ack")
    assert "10" in dicho and "ferrari.com" in dicho


def test_una_sola_foto_no_se_cuenta_en_plural():
    dicho = image_turn.spoken_for({"executed": "show_images", "ok": True, "count": 1, "sites": []}, "ack")
    assert "1 fotos" not in dicho


def test_si_no_cargo_lo_dice_en_vez_de_dar_por_bueno():
    """Quinta vez que una frase nuestra sobre una caja vacía es la que miente (V2-176/209/377/380/383)."""
    dicho = image_turn.spoken_for(
        {"executed": "show_images", "ok": False, "message": "no encontré fotos de eso"}, "Hecho.")
    assert dicho != "Hecho."
    assert "no" in dicho.lower()


def test_un_bloqueo_del_buscador_no_es_que_no_haya_fotos():
    """Piden acciones distintas: reintentar, frente a buscar otra cosa. Confundirlas manda al operador a
    cambiar una consulta que estaba bien."""
    dicho = image_turn.spoken_for({"executed": "show_images", "ok": False, "blocked": True}, "ack")
    assert "bloque" in dicho.lower()


def test_un_turno_que_no_era_de_fotos_conserva_su_propio_ack():
    assert image_turn.spoken_for({"executed": "play_video"}, "ack") == "ack"
    assert image_turn.spoken_for({}, "ack") == "ack"
