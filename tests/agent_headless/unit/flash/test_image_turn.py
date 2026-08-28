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


def test_un_bloqueo_del_buscador_no_es_que_no_haya_fotos(monkeypatch):
    """Piden acciones distintas: reintentar, frente a buscar otra cosa. Confundirlas manda al operador a
    cambiar una consulta que estaba bien. (Idioma FIJADO: desde V2-464 las frases siguen al motor, y el
    entorno de la suite resuelve inglés — este caso mide el CONTENIDO, no el idioma.)"""
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es", raising=False)
    dicho = image_turn.spoken_for({"executed": "show_images", "ok": False, "blocked": True}, "ack")
    assert "bloque" in dicho.lower()


def test_un_turno_que_no_era_de_fotos_conserva_su_propio_ack():
    assert image_turn.spoken_for({"executed": "play_video"}, "ack") == "ack"
    assert image_turn.spoken_for({}, "ack") == "ack"


# ── V2-463 — la tarjeta se ABRE donde aterrizan los datos, y cada búsqueda deja su evidencia ────────────
def test_cargar_fotos_ABRE_la_tarjeta_del_visor(monkeypatch):
    """La ronda que lo fijó (2026-08-28): 12 fotos en el almacén y el operador mirando un canvas donde la
    tarjeta nunca se abrió — la voz emitía el `show` y el canal probe no. El rail COMPARTIDO es quien abre:
    quinta vez que «cablear en ambos» se paga, así que la decisión vive donde los dos canales ya pasan."""
    emitted: list[tuple] = []

    async def _images(q, k):
        return {"query": q, "items": _items(2), "source": "google", "blocked": False}

    async def _brain_action(wid, action, payload):
        return {"ok": True, "n": 2}

    monkeypatch.setattr("nucleo.browser_search.images", _images, raising=False)
    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        emitted.append((kind, label, extra or {})))
    asyncio.run(image_turn.execute("Ferrari Amalfi", 2))
    shows = [e for e in emitted if e[0] == "widget" and e[1] == "show"]
    assert shows and shows[0][2].get("id") == "imagenes", "sin el show, el operador mira un canvas vacío"


def test_sin_fotos_NO_se_abre_ninguna_tarjeta(monkeypatch):
    """Abrir un visor vacío sobre un «no encontré nada» es enseñar una caja hueca — la mitad de sensibilidad."""
    emitted: list[tuple] = []

    async def _images(q, k):
        return {"query": q, "items": [], "source": "google", "blocked": False}

    monkeypatch.setattr("nucleo.browser_search.images", _images, raising=False)
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        emitted.append((kind, label, extra or {})))
    asyncio.run(image_turn.execute("algo inexistente"))
    assert not [e for e in emitted if e[0] == "widget" and e[1] == "show"]


def test_cada_busqueda_emite_su_evidencia_con_la_QUERY(monkeypatch):
    """La búsqueda de los diccionarios no se pudo diagnosticar: el `show` siguiente pisó el almacén y la
    query basura desapareció. Lo que una búsqueda pidió y lo que trajo es evidencia del TURNO, no estado del
    widget — se emite en el momento en que existe, incluida la que salió mal."""
    emitted: list[tuple] = []

    async def _images(q, k):
        return {"query": q, "items": [], "source": "bing", "blocked": False}

    monkeypatch.setattr("nucleo.browser_search.images", _images, raising=False)
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        emitted.append((kind, label, extra or {})))
    asyncio.run(image_turn.execute("avísame cuando la tengas"))
    ev = [e for e in emitted if e[0] == "brain" and "búsqueda" in e[1]]
    assert ev, "una búsqueda sin rastro es indiagnosticable"
    x = ev[0][2]
    assert x.get("query") == "avísame cuando la tengas"
    assert x.get("source") == "bing" and x.get("ok") is False


def test_el_juez_ve_un_widget_escrito_pero_nunca_abierto():
    """La otra mitad, en el arnés: `widget_ops` ya contaba los `show`, pero el hecho «datos sin tarjeta» no
    se enunciaba y un campo que el juez no ve en palabras es invisible (V2-346)."""
    import pathlib as _pl
    src = (_pl.Path(__file__).resolve().parents[4] / "tests" / "use_cases" / "e2e" / "agent"
           / "judge.py").read_text(encoding="utf-8")
    assert "ESCRITOS PERO NUNCA ABIERTOS" in src


# ── V2-464 — la boca habla el idioma del MOTOR ──────────────────────────────────────────────────────────
def test_en_el_motor_ingles_las_frases_salen_en_ingles(monkeypatch):
    """Medido en vivo en la primera ronda del agente US: el tester en inglés, zaelar contestando «Te he
    puesto 12 fotos en pantalla…» toda la conversación. El motor es monolingüe por proceso — una lectura
    decide el juego entero de frases."""
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "en-US", raising=False)
    dicho = image_turn.spoken_for(
        {"executed": "show_images", "ok": True, "count": 12, "sites": ["www.ferrari.com"]}, "ack")
    assert "photos on screen" in dicho and "ferrari.com" in dicho
    assert "pantalla" not in dicho
    fallo = image_turn.spoken_for({"executed": "show_images", "ok": False, "message": "x"}, "ack")
    assert fallo.startswith("I couldn't")


def test_y_el_reproductor_de_video_igual(monkeypatch):
    """El hermano llevaba el MISMO agujero desde V2-383 sin que ninguna ronda US de vídeo lo destapara."""
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "en", raising=False)
    from nucleo.flash import video_turn
    dicho = video_turn.spoken_for({"executed": "play_video", "ok": True, "title": "Some Doc"}, "ack")
    assert dicho == "It's up on your screen: «Some Doc»."
