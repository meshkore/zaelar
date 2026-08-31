"""The text channel labelled the video instead of playing it (V2-383).

The exact sibling of V2-380 (music), one branch lower in the same `elif`. Measured in
`watch-a-video-not-listen-to-it` (2026-08-27 12:53), **1/5**:

    tester  Pon el vídeo del tráiler de la última de Dune.
    zaelar  Te lo abro, aunque de momento está vacío.
    tester  Eso no me vale, quiero el tráiler de verdad, no un vídeo vacío.
    zaelar  Te lo abro, aunque de momento está vacío.
    …
    tester  Tío, eso me lo has dicho ya tres veces y sigue sin salir el vídeo.

`play_video` resolved to the «canvas:show:youtube» label and ended there: no `load`, the widget was BARE. And
what hurts most—the system DID find the trailers: six searches with real titles («Dune: Part Two |
Official Trailer»), all going to the RESULTS SHEET, none to the player. The search engine was not broken either:
`_search_id('Dune tráiler oficial')` resolves today to `mSY_NbSmaUI` from Warner Bros. España. It was
UNREACHABLE from this channel.

Fourth occurrence in this family in `probe.py`: cron tags (V2-121), login handoff (V2-176), music (V2-380).
And the repeated phrase was NOT canned by us—it is not in the code—but the model telling the truth about an
empty box, which is worse: the honesty guard was working and there was nothing honest to report.
"""
import asyncio
from pathlib import Path

import pytest

from nucleo.flash import video_turn as VT


@pytest.fixture
def rail(monkeypatch):
    """Replace the rail with a witness: this measures the WIRING, not the YouTube search engine."""
    visto = {}

    async def _brain_action(wid, action, payload):
        visto.update({"wid": wid, "action": action, "payload": payload})
        return visto.get("_res", {"ok": True, "videoId": "Way9Dexny3w",
                                  "title": "Dune: Part Two | Official Trailer"})
    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    return visto


# ── the ENTIRE TURN, where the defect lived ─────────────────────────────────────────────────────────────────
#
# The guards below inspect the file and module separately, and that is NOT enough: when unpacking
# `video_req = _video_turn.request_from(tool_calls)` → `video_req = None`, all fourteen remained green. The execution
# branch existed, the module worked, and nothing reached the other from one to the other—exactly the shape of the
# original defect. The only thing that catches it is running the real turn.

class _ClienteQuePideVideo:
    """Stub: el modelo llama a `play_video`, como en la ronda real."""

    async def stream(self, *_a, on_tool_call=None, **_kw):
        if on_tool_call is not None:
            res = on_tool_call("play_video", {"query": "tráiler oficial de Dune"})
            if asyncio.iscoroutine(res):
                await res
        yield "Te lo pongo."


def test_un_turno_de_video_CARGA_el_widget_de_verdad(monkeypatch, tmp_path):
    """From the model's request to the widget's `load`, without skipping anything in between."""
    from memory import db as memdb
    from memory import embeddings as mememb
    from nucleo.flash import probe

    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset(); memdb.reset_db(); memdb.get_db()

    visto = {}

    async def _brain_action(wid, action, payload):
        visto.update({"wid": wid, "action": action, "payload": payload})
        return {"ok": True, "videoId": "Way9Dexny3w", "title": "Dune: Part Two | Official Trailer"}

    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _ClienteQuePideVideo)
    try:
        res = asyncio.run(probe.run_turn("Pon el vídeo del tráiler de la última de Dune.",
                                         sid="test-video-turn", ingest=False, execute=True))
    finally:
        probe._SESSIONS.pop("test-video-turn", None)
        memdb.reset_db(); mememb.reset()

    assert res["ok"] is True
    assert visto == {"wid": "youtube", "action": "load", "payload": {"query": "tráiler oficial de Dune"}}, \
        "el turno tiene que llegar al widget: rotularlo y no cargarlo ES el defecto"


class _ClienteMudoQuePideVideo(_ClienteQuePideVideo):
    """The model calls `play_video` and says NOTHING—that is where our ack speaks."""

    async def stream(self, *_a, on_tool_call=None, **_kw):
        if on_tool_call is not None:
            res = on_tool_call("play_video", {"query": "tráiler oficial de Dune"})
            if asyncio.iscoroutine(res):
                await res
        if False:          # pragma: no cover — generador mudo
            yield ""


def test_un_turno_MUDO_de_video_NOMBRA_lo_que_cargo(monkeypatch, tmp_path):
    """Without this, the turn falls back to the generic `canvas:` ack, which only knows how to say «here you go» or—if the
    widget is empty—the phrase the tester heard four times in a row."""
    from memory import db as memdb
    from memory import embeddings as mememb
    from nucleo.flash import probe

    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset(); memdb.reset_db(); memdb.get_db()

    async def _brain_action(wid, action, payload):
        return {"ok": True, "videoId": "Way9Dexny3w", "title": "Dune: Part Two | Official Trailer"}

    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _ClienteMudoQuePideVideo)
    try:
        res = asyncio.run(probe.run_turn("Pon el tráiler de Dune.", sid="test-video-mudo",
                                         ingest=False, execute=True))
    finally:
        probe._SESSIONS.pop("test-video-mudo", None)
        memdb.reset_db(); mememb.reset()

    # `reply`, not `text` or `spoken`: measure against the data's REAL shape. With the wrong name, the guard
    # would have gone red on a turn that said exactly what it was supposed to say.
    assert "Dune: Part Two" in (res.get("reply") or "")


def test_la_boca_del_video_va_ANTES_del_ack_generico_de_canvas():
    """The order IS the fix: `canvas:show:youtube` starts with `canvas:`, so the generic branch consumes it
    if it comes first."""
    src = Path("nucleo/flash/probe.py").read_text()
    i_video = src.index("# V2-383 — se NOMBRA el vídeo que cargó")
    i_canvas = src.index('elif action.startswith("canvas:"):')
    assert i_video < i_canvas


# ── the wiring ─────────────────────────────────────────────────────────────────────────────────────────────

def test_el_rail_de_video_ESTA_enchufado_en_este_canal():
    """The guard that would have been enough: the branch existed and executed nothing."""
    src = Path("nucleo/flash/probe.py").read_text()
    assert "from nucleo.flash import video_turn as _video_turn" in src
    assert "await _video_turn.execute(video_req[" in src


def test_la_rama_de_video_va_DENTRO_del_bloque_de_ejecucion():
    """Outside `if execute:`, it would become a label again—and that is exactly the defect being closed."""
    src = Path("nucleo/flash/probe.py").read_text()
    i_exec = src.index("    if execute:")
    i_video = src.index('elif action == "canvas:show:youtube" and video_req:')
    assert i_exec < i_video


def test_el_rail_es_el_MISMO_que_usa_la_voz():
    """The voice uses `_apply_widget_data("youtube", "load", {"query": …})`. If this channel invented its own
    path, there would be TWO ways to play a video, and the one being measured would not be the one the operator uses."""
    assert 'brain_action("youtube", "load"' in Path("nucleo/flash/video_turn.py").read_text()


def test_los_argumentos_del_modelo_llegan_al_rail(rail):
    parte = asyncio.run(VT.execute("  Dune tráiler oficial  "))
    assert rail["wid"] == "youtube" and rail["action"] == "load"
    assert rail["payload"] == {"query": "Dune tráiler oficial"}
    assert parte["executed"] == "play_video" and parte["ok"] is True


def test_una_query_VACIA_no_manda_una_busqueda_vacia(rail):
    """`load` without a query reloads whatever was there; sending `{"query": ""}` would search for nothing."""
    asyncio.run(VT.execute("   "))
    assert rail["payload"] == {}


# Rewritten by V2-402, not reversed: `request_from` gained the `action` field (play|list) because a video search
# («find me videos of…») is now also handled by this tool and goes to the player's LIST, not the results sheet.
# What these two tests protect—not inventing a request and trimming the query—remains intact.
def test_sin_llamada_a_play_video_no_se_inventa_una():
    assert VT.request_from([{"name": "web_search", "args": {}}]) == {"query": "", "action": "play"}


def test_la_query_se_recorta_al_extraerla():
    assert VT.request_from([{"name": "play_video", "args": {"query": " tráiler de Dune "}}]) == \
        {"query": "tráiler de Dune", "action": "play"}


def test_una_averia_del_reproductor_devuelve_parte_y_no_lanza(monkeypatch):
    """Fail-soft like the rest of the block: the turn must complete even if the player is broken."""
    async def _boom(*a, **k):
        raise RuntimeError("el widget no responde")
    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _boom)
    parte = asyncio.run(VT.execute("Dune"))
    assert parte["ok"] is False and "no responde" in parte["execute_error"]


def test_un_NO_ENCONTRADO_del_widget_se_reporta_como_fallo(rail):
    """The widget itself returns `{"ok": False, "error": "no_video"}`. Treating that as successful would mean saying
    «I'll open it for you» again over an empty screen, which is the entire defect."""
    rail["_res"] = {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
    parte = asyncio.run(VT.execute("un vídeo que no existe"))
    assert parte["ok"] is False and "No encontré" in parte["message"]


# ── the mouth says what HAPPENED ────────────────────────────────────────────────────────────────────────────

def _boca(extra):
    """The REAL decision, not a copy: reimplementing it here would only prove that my copy works (V2-199)."""
    return VT.spoken_for(extra, "Hecho.")


def test_si_CARGA_se_NOMBRA_el_video():
    """Naming it makes it possible to verify at a glance that it is the one requested (V2-057). «Hecho.» does not."""
    salida = _boca({"executed": "play_video", "ok": True, "title": "Dune: Part Two | Official Trailer"})
    assert "Dune: Part Two" in salida and "Hecho." not in salida


def test_si_NO_carga_se_DICE_en_vez_de_Hecho(monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es", raising=False)  # V2-464: phrases follow the engine
    """The heart of the defect: a delivery phrase over an empty box. Fifth occurrence (V2-176, V2-209, V2-377,
    V2-380)."""
    salida = _boca({"executed": "play_video", "ok": False, "message": "No encontré ese vídeo."})
    assert salida.startswith("No he podido ponerlo")
    assert "Hecho." not in salida


def test_un_fallo_SIN_motivo_no_se_queda_mudo(monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es", raising=False)  # V2-464: phrases follow the engine
    assert "no encontré ese vídeo" in _boca({"executed": "play_video", "ok": False})


def test_un_turno_que_NO_es_de_video_conserva_su_ack():
    assert _boca({"executed": "widget_data", "ok": True}) == "Hecho."


def test_un_exito_SIN_titulo_no_inventa_uno():
    """Without a title there is nothing to verify, so it falls back to the ack instead of fabricating a name."""
    assert _boca({"executed": "play_video", "ok": True, "title": ""}) == "Hecho."


# ── V2-463 — the player's card opens on the SHARED rail ─────────────────────────────────────────────────
def test_cargar_un_video_ABRE_la_tarjeta_tambien_desde_el_probe(monkeypatch):
    """The same hole as the image viewer: voice emitted its `show` and the probe channel emitted none, so a
    measured run played on a canvas without a card. The opening lives in `video_turn.execute`."""
    import asyncio
    emitted: list[tuple] = []

    async def _brain_action(wid, action, payload):
        return {"ok": True, "videoId": "abc123", "title": "x"}

    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        emitted.append((kind, label, extra or {})))
    from nucleo.flash import video_turn
    asyncio.run(video_turn.execute("un documental"))
    shows = [e for e in emitted if e[0] == "widget" and e[1] == "show"]
    assert shows and shows[0][2].get("id") == "youtube"


def test_un_video_que_NO_cargo_no_abre_nada(monkeypatch):
    import asyncio
    emitted: list[tuple] = []

    async def _brain_action(wid, action, payload):
        return {"ok": False, "error": "nada"}

    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action, raising=False)
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        emitted.append((kind, label, extra or {})))
    from nucleo.flash import video_turn
    asyncio.run(video_turn.execute("algo"))
    assert not [e for e in emitted if e[0] == "widget" and e[1] == "show"]


# ── V2-465 — the player PUBLISHES its list ──────────────────────────────────────────────────────────────
def test_el_reproductor_publica_sus_items_para_que_el_cerebro_los_nombre(monkeypatch, tmp_path):
    """The only one in the media family that did not do so (measured on 2026-08-28 by comparing all three): `musica` and
    `imagenes` answered and this one returned "". Two consequences, the second being the ugly one: «pon la tercera»
    had nothing to resolve against—and the model must NEVER invent an id (V2-026)—and with the card OPEN
    AND EMPTY the brief could not say it, which is the «claiming delivery of what is not there» of V2-377/380/383."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.youtube import data as yt
    db = yt._load()
    db["list"] = [{"videoId": "a1", "title": "Paella paso a paso", "channel": "Cocina"},
                  {"videoId": "b2", "title": "Ferrari Amalfi first drive", "channel": "MotorTrend"}]
    db["pos"] = 1
    store.save(yt.WID, db)

    idx = yt.ref_index()
    assert [i["id"] for i in idx] == ["1", "2"], "se nombra por NÚMERO, como se dice en voz"
    assert all(i["field"] == "item" for i in idx), "`item` es la clave que usa play_item/remove/move"
    assert "Paella" in idx[0]["label"]
    assert "la que suena" in idx[1]["hint"], "cuál de doce está sonando es una referencia real del operador"

    from widgets import refs
    linea = refs.items_line("youtube")
    assert "Paella" in linea and "MotorTrend" in linea


def test_una_lista_VACIA_lo_dice_en_vez_de_callar(monkeypatch, tmp_path):
    """The half that prevents the costly defect: without an index, «open and empty» and «does not publish» were indistinguishable."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets import refs
    assert "VACÍA" in refs.items_line("youtube")


# ── V2-467 — the player's list can be NAMED ──────────────────────────────────────────────────────────────
def test_la_lista_se_puede_nombrar_como_las_de_musica(monkeypatch, tmp_path):
    """Family asymmetry measured in `build-a-video-playlist-from-links`: `musica` has named lists and
    this player did not, so «call it the afternoon one» had nowhere to go—the model found no action
    and the escalate catalog itself («not being in the catalog is NOT a reason to refuse») sent a queue of
    two links to a Brain Worker. The scenario calls that a FAILURE: it is a rail, resolved in the turn."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.youtube import data as yt
    r = yt.apply_action("name_list", {"name": "la de la tarde"})
    assert r["ok"] and r["name"] == "la de la tarde"
    assert yt.view_data()["list_name"] == "la de la tarde"


def test_un_nombre_vacio_lo_QUITA_igual_que_el_filtro(monkeypatch, tmp_path):
    """Two list actions cannot disagree about what an empty payload means: `filter_list` already uses
    «empty = remove»."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.youtube import data as yt
    yt.apply_action("name_list", {"name": "x"})
    assert yt.apply_action("name_list", {})["name"] == ""
    assert yt.view_data()["list_name"] == ""


def test_la_tarjeta_ENSEÑA_el_nombre_o_no_sirve_de_nada():
    """Un nombre que solo vive en el store no deja al operador verificar que se le hizo caso."""
    import pathlib
    js = (pathlib.Path(__file__).resolve().parents[4] / "widgets" / "youtube"
          / "widget.js").read_text(encoding="utf-8")
    assert "list_name" in js and "_rot" in js


def test_las_acciones_declaradas_siguen_siendo_las_que_hace(monkeypatch, tmp_path):
    """The generator gate rejects a declared action that nobody handles and a handled action that is undeclared."""
    import json
    import pathlib
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.youtube import data as yt
    m = json.loads((pathlib.Path(__file__).resolve().parents[4] / "widgets" / "youtube"
                    / "manifest.json").read_text(encoding="utf-8"))
    assert "name_list" in m["actions"]
    assert yt.apply_action("name_list", {}).get("ok") is True


def test_con_player_error_la_pista_dice_que_NO_suena_y_por_que(monkeypatch, tmp_path):
    """V2-469 · «la que suena» is a LIE over a broken player. Measured in `build-a-video-playlist-from-links`
    (23:05): `play` → `player_error ×2` (embedding disabled — Rick Astley refuses the iframe) and nothing
    surfaced the fact, so the model answered «¿qué está sonando?» with evasions for four turns. V2-401
    already fixed the producing predicate; the hint the brain READS still claimed playback. With
    `player_error` set, the current item's hint states the block instead."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.youtube import data as yt
    db = yt._load()
    db["list"] = [{"videoId": "a1", "title": "Never Gonna Give You Up", "channel": "Rick Astley"}]
    db["pos"] = 0
    db["player_error"] = "150"
    store.save(yt.WID, db)

    idx = yt.ref_index()
    assert "la que suena" not in (idx[0]["hint"] or "")
    assert "no se puede reproducir" in idx[0]["hint"]


def test_sin_player_error_la_pista_de_la_que_suena_se_conserva(monkeypatch, tmp_path):
    """Sensitivity in the safe direction: a healthy player keeps the reference the operator actually uses."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.youtube import data as yt
    db = yt._load()
    db["list"] = [{"videoId": "a1", "title": "Paella paso a paso", "channel": "Cocina"}]
    db["pos"] = 0
    db["player_error"] = ""
    store.save(yt.WID, db)
    assert "la que suena" in yt.ref_index()[0]["hint"]
