"""V2-457 — showing images: execution shared by both channels, and what is SAID afterward."""
from __future__ import annotations

import asyncio

from nucleo.flash import image_turn


def _items(n=3):
    return [{"url": f"https://cdn.ferrari.com/{i}.jpg", "thumb": f"https://t/{i}",
             "title": f"Ferrari Amalfi {i}", "site": "www.ferrari.com",
             "page": "https://www.ferrari.com/x", "w": 1080, "h": 565} for i in range(n)]


# ── what the tool requested ────────────────────────────────────────────────────────────────────────────
def test_lee_la_peticion_y_acota_cuantas():
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "  Ferrari Amalfi "}}]) == {
        "query": "Ferrari Amalfi", "n": image_turn.DEFAULT_N}
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "x", "n": 3}}])["n"] == 3
    # An absurd `n` cannot turn a lightweight turn into a load of a hundred images, and an unreadable one
    # (the model writes "cinco") falls back to the default instead of crashing.
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "x", "n": 900}}])["n"] == 24
    # `n: 0` («cero fotos») and `n: "cinco"` are the two ways the model can make a mistake when writing the
    # number, and both fall back to the default: showing ONE image is not what either of them meant.
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "x", "n": 0}}])["n"] == 12
    assert image_turn.request_from([{"name": "show_images", "args": {"query": "x", "n": "cinco"}}])["n"] == 12
    assert image_turn.request_from([])["query"] == ""


# ── execution ───────────────────────────────────────────────────────────────────────────────────────────
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
    assert visto["cargado"] == ("imagenes", "show", 3)   # the VIEWER, never the results sheet
    assert parte["ok"] is True and parte["count"] == 3
    assert parte["sites"] == ["www.ferrari.com"]


def test_sin_fotos_no_toca_el_visor_y_lo_dice(monkeypatch):
    """An empty `show` would DELETE whatever was on screen: finding nothing cannot cost the operator
    the images they already had in front of them."""
    async def _images(q, k):
        return {"query": q, "items": [], "source": "google", "blocked": False}

    async def _brain_action(*a, **k):  # pragma: no cover — must not be called
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


# ── what is said ───────────────────────────────────────────────────────────────────────────────────────
def test_nombra_cuantas_y_de_quien():
    """The set is NAMED for the same reason the player names the video it loaded (V2-057): it lets you
    verify at a glance that these are the requested images. And the SOURCE is exactly what the operator
    valued about the slow path — a fast path that cannot say whose image it is changes what mattered to
    them for the sake of speed."""
    dicho = image_turn.spoken_for(
        {"executed": "show_images", "ok": True, "count": 10, "sites": ["www.ferrari.com", "es.wikipedia.org"]}, "ack")
    assert "10" in dicho and "ferrari.com" in dicho


def test_una_sola_foto_no_se_cuenta_en_plural():
    dicho = image_turn.spoken_for({"executed": "show_images", "ok": True, "count": 1, "sites": []}, "ack")
    assert "1 fotos" not in dicho


def test_si_no_cargo_lo_dice_en_vez_de_dar_por_bueno():
    """The fifth time one of our phrases about an empty box is the one that lies (V2-176/209/377/380/383)."""
    dicho = image_turn.spoken_for(
        {"executed": "show_images", "ok": False, "message": "no encontré fotos de eso"}, "Hecho.")
    assert dicho != "Hecho."
    assert "no" in dicho.lower()


def test_un_bloqueo_del_buscador_no_es_que_no_haya_fotos(monkeypatch):
    """They call for different actions: retrying versus searching for something else. Confusing them sends
    the operator to change a query that was fine. (Language FIXED: since V2-464 the phrases follow the
    engine, and the suite environment resolves to English — this case measures CONTENT, not language.)"""
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es", raising=False)
    dicho = image_turn.spoken_for({"executed": "show_images", "ok": False, "blocked": True}, "ack")
    assert "bloque" in dicho.lower()


def test_un_turno_que_no_era_de_fotos_conserva_su_propio_ack():
    assert image_turn.spoken_for({"executed": "play_video"}, "ack") == "ack"
    assert image_turn.spoken_for({}, "ack") == "ack"


# ── V2-463 — the card OPENS where the data lands, and each search leaves its evidence ──────────────────
def test_cargar_fotos_ABRE_la_tarjeta_del_visor(monkeypatch):
    """The round that established this (2026-08-28): 12 images in storage and the operator looking at a
    canvas where the card never opened — voice emitted the `show` and the probe channel did not. The
    SHARED rail is what opens it: the fifth time that «wiring both» has cost us, so the decision belongs
    where both channels already pass."""
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
    """Opening an empty viewer for a «found nothing» result is showing a hollow box — half the sensitivity."""
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
    """The dictionaries' search could not be diagnosed: the next `show` overwrote storage and the
    garbage query disappeared. What a search requested and what it returned is evidence of the TURN, not
    widget state — it is emitted as soon as it exists, including when it went wrong."""
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
    """The other half, in the harness: `widget_ops` already counted the `show`s, but the «data without a
    card» fact was not stated, and a field the judge cannot see in words is invisible (V2-346)."""
    import pathlib as _pl
    src = (_pl.Path(__file__).resolve().parents[4] / "tests" / "use_cases" / "e2e" / "agent"
           / "judge.py").read_text(encoding="utf-8")
    assert "ESCRITOS PERO NUNCA ABIERTOS" in src


# ── V2-464 — the mouth speaks the ENGINE's language ────────────────────────────────────────────────────
def test_en_el_motor_ingles_las_frases_salen_en_ingles(monkeypatch):
    """Measured live in the first US agent round: the tester in English, zaelar replying «I've put 12
    photos on screen…» throughout the conversation. The engine is monolingual per process — one read
    determines the entire set of phrases."""
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "en-US", raising=False)
    dicho = image_turn.spoken_for(
        {"executed": "show_images", "ok": True, "count": 12, "sites": ["www.ferrari.com"]}, "ack")
    assert "photos on screen" in dicho and "ferrari.com" in dicho
    assert "pantalla" not in dicho
    fallo = image_turn.spoken_for({"executed": "show_images", "ok": False, "message": "x"}, "ack")
    assert fallo.startswith("I couldn't")


def test_y_el_reproductor_de_video_igual(monkeypatch):
    """Its sibling had carried the SAME hole since V2-383 without any US video round exposing it."""
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "en", raising=False)
    from nucleo.flash import video_turn
    dicho = video_turn.spoken_for({"executed": "play_video", "ok": True, "title": "Some Doc"}, "ack")
    assert dicho == "It's up on your screen: «Some Doc»."
