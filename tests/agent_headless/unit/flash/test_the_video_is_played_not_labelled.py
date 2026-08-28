"""El canal de texto rotulaba el vídeo en vez de ponerlo (V2-383).

Hermano exacto de V2-380 (la música) y una rama más abajo en el mismo `elif`. Medido en
`watch-a-video-not-listen-to-it` (2026-08-27 12:53), **1/5**:

    tester  Pon el vídeo del tráiler de la última de Dune.
    zaelar  Te lo abro, aunque de momento está vacío.
    tester  Eso no me vale, quiero el tráiler de verdad, no un vídeo vacío.
    zaelar  Te lo abro, aunque de momento está vacío.
    …
    tester  Tío, eso me lo has dicho ya tres veces y sigue sin salir el vídeo.

`play_video` resolvía a la etiqueta «canvas:show:youtube» y ahí acababa: ninguna `load`, el widget PELADO. Y
lo que más duele — el sistema SÍ encontró los tráileres: seis búsquedas con títulos reales («Dune: Part Two |
Official Trailer»), todas a la HOJA DE RESULTADOS, ninguna al reproductor. El buscador tampoco estaba roto:
`_search_id('Dune tráiler oficial')` resuelve hoy a `mSY_NbSmaUI` de Warner Bros. España. Estaba
INALCANZABLE desde este canal.

Cuarta vez de esta familia en `probe.py`: tags de cron (V2-121), traspaso de login (V2-176), música (V2-380).
Y la frase repetida NO era enlatada nuestra —no está en el código— sino el modelo diciendo la verdad sobre una
caja vacía, que es peor: el guarda de honestidad funcionaba y no había nada honesto que contar.
"""
import asyncio
from pathlib import Path

import pytest

from nucleo.flash import video_turn as VT


@pytest.fixture
def rail(monkeypatch):
    """Sustituye el rail por un testigo: aquí se mide el CABLEADO, no el buscador de YouTube."""
    visto = {}

    async def _brain_action(wid, action, payload):
        visto.update({"wid": wid, "action": action, "payload": payload})
        return visto.get("_res", {"ok": True, "videoId": "Way9Dexny3w",
                                  "title": "Dune: Part Two | Official Trailer"})
    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    return visto


# ── el TURNO ENTERO, que es donde vivía el defecto ─────────────────────────────────────────────────────────
#
# Los guardas de más abajo miran el fichero y el módulo por separado, y con eso NO basta: al desarmar
# `video_req = _video_turn.request_from(tool_calls)` → `video_req = None` los catorce seguían en verde. La rama
# de ejecución existía, el módulo funcionaba, y entre los dos no llegaba nada — que es exactamente la forma del
# defecto original. Lo único que lo caza es conducir el turno de verdad.

class _ClienteQuePideVideo:
    """Stub: el modelo llama a `play_video`, como en la ronda real."""

    async def stream(self, *_a, on_tool_call=None, **_kw):
        if on_tool_call is not None:
            res = on_tool_call("play_video", {"query": "tráiler oficial de Dune"})
            if asyncio.iscoroutine(res):
                await res
        yield "Te lo pongo."


def test_un_turno_de_video_CARGA_el_widget_de_verdad(monkeypatch, tmp_path):
    """De la petición del modelo al `load` del widget, sin saltarse nada por el medio."""
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
    """El modelo llama a `play_video` y NO dice nada — ahí es donde habla nuestro ack."""

    async def stream(self, *_a, on_tool_call=None, **_kw):
        if on_tool_call is not None:
            res = on_tool_call("play_video", {"query": "tráiler oficial de Dune"})
            if asyncio.iscoroutine(res):
                await res
        if False:          # pragma: no cover — generador mudo
            yield ""


def test_un_turno_MUDO_de_video_NOMBRA_lo_que_cargo(monkeypatch, tmp_path):
    """Sin esto el turno cae al ack genérico de `canvas:`, que solo sabe decir «aquí lo tienes» o —si el
    widget está vacío— la frase que el tester leyó cuatro veces seguidas."""
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

    # `reply`, no `text` ni `spoken`: medir contra la forma REAL del dato. Con el nombre equivocado el guarda
    # habría salido rojo sobre un turno que decía exactamente lo que tenía que decir.
    assert "Dune: Part Two" in (res.get("reply") or "")


def test_la_boca_del_video_va_ANTES_del_ack_generico_de_canvas():
    """El orden ES la corrección: `canvas:show:youtube` empieza por `canvas:`, así que la rama genérica se lo
    come si va primero."""
    src = Path("nucleo/flash/probe.py").read_text()
    i_video = src.index("# V2-383 — se NOMBRA el vídeo que cargó")
    i_canvas = src.index('elif action.startswith("canvas:"):')
    assert i_video < i_canvas


# ── el cableado ────────────────────────────────────────────────────────────────────────────────────────────

def test_el_rail_de_video_ESTA_enchufado_en_este_canal():
    """El guarda que habría bastado: la rama existía y no ejecutaba nada."""
    src = Path("nucleo/flash/probe.py").read_text()
    assert "from nucleo.flash import video_turn as _video_turn" in src
    assert "await _video_turn.execute(video_req[" in src


def test_la_rama_de_video_va_DENTRO_del_bloque_de_ejecucion():
    """Fuera del `if execute:` volvería a ser una etiqueta — y ese es exactamente el defecto que se cierra."""
    src = Path("nucleo/flash/probe.py").read_text()
    i_exec = src.index("    if execute:")
    i_video = src.index('elif action == "canvas:show:youtube" and video_req:')
    assert i_exec < i_video


def test_el_rail_es_el_MISMO_que_usa_la_voz():
    """La voz hace `_apply_widget_data("youtube", "load", {"query": …})`. Si este canal inventara su propio
    camino habría DOS formas de poner un vídeo, y la que se mide no sería la que usa el operador."""
    assert 'brain_action("youtube", "load"' in Path("nucleo/flash/video_turn.py").read_text()


def test_los_argumentos_del_modelo_llegan_al_rail(rail):
    parte = asyncio.run(VT.execute("  Dune tráiler oficial  "))
    assert rail["wid"] == "youtube" and rail["action"] == "load"
    assert rail["payload"] == {"query": "Dune tráiler oficial"}
    assert parte["executed"] == "play_video" and parte["ok"] is True


def test_una_query_VACIA_no_manda_una_busqueda_vacia(rail):
    """`load` sin query recarga lo que hubiera; mandar `{"query": ""}` haría buscar la nada."""
    asyncio.run(VT.execute("   "))
    assert rail["payload"] == {}


# Reescritos por V2-402, no volteados: `request_from` ganó el campo `action` (play|list) porque una búsqueda
# de vídeos («búscame vídeos de…») ahora también es de esta tool y va a la LISTA del reproductor, no a la hoja
# de resultados. Lo que estos dos tests protegen —no inventar una petición y recortar la query— sigue intacto.
def test_sin_llamada_a_play_video_no_se_inventa_una():
    assert VT.request_from([{"name": "web_search", "args": {}}]) == {"query": "", "action": "play"}


def test_la_query_se_recorta_al_extraerla():
    assert VT.request_from([{"name": "play_video", "args": {"query": " tráiler de Dune "}}]) == \
        {"query": "tráiler de Dune", "action": "play"}


def test_una_averia_del_reproductor_devuelve_parte_y_no_lanza(monkeypatch):
    """Fail-soft como el resto del bloque: el turno tiene que salir aunque el reproductor esté roto."""
    async def _boom(*a, **k):
        raise RuntimeError("el widget no responde")
    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _boom)
    parte = asyncio.run(VT.execute("Dune"))
    assert parte["ok"] is False and "no responde" in parte["execute_error"]


def test_un_NO_ENCONTRADO_del_widget_se_reporta_como_fallo(rail):
    """El propio widget devuelve `{"ok": False, "error": "no_video"}`. Darlo por bueno sería volver a decir
    «te lo abro» sobre una pantalla vacía, que es el defecto entero."""
    rail["_res"] = {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
    parte = asyncio.run(VT.execute("un vídeo que no existe"))
    assert parte["ok"] is False and "No encontré" in parte["message"]


# ── la boca dice lo que PASÓ ───────────────────────────────────────────────────────────────────────────────

def _boca(extra):
    """La decisión REAL, no una copia: reimplementarla aquí probaría que mi copia funciona (V2-199)."""
    return VT.spoken_for(extra, "Hecho.")


def test_si_CARGA_se_NOMBRA_el_video():
    """Nombrarlo es lo que deja verificar de un vistazo que es el que pedía (V2-057). «Hecho.» no lo deja."""
    salida = _boca({"executed": "play_video", "ok": True, "title": "Dune: Part Two | Official Trailer"})
    assert "Dune: Part Two" in salida and "Hecho." not in salida


def test_si_NO_carga_se_DICE_en_vez_de_Hecho(monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es", raising=False)  # V2-464: frases siguen al motor
    """El corazón del defecto: una frase de entrega sobre una caja vacía. Quinta vez (V2-176, V2-209, V2-377,
    V2-380)."""
    salida = _boca({"executed": "play_video", "ok": False, "message": "No encontré ese vídeo."})
    assert salida.startswith("No he podido ponerlo")
    assert "Hecho." not in salida


def test_un_fallo_SIN_motivo_no_se_queda_mudo(monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "es", raising=False)  # V2-464: frases siguen al motor
    assert "no encontré ese vídeo" in _boca({"executed": "play_video", "ok": False})


def test_un_turno_que_NO_es_de_video_conserva_su_ack():
    assert _boca({"executed": "widget_data", "ok": True}) == "Hecho."


def test_un_exito_SIN_titulo_no_inventa_uno():
    """Sin título no hay nada que verificar, así que se cae al ack en vez de fabricar un nombre."""
    assert _boca({"executed": "play_video", "ok": True, "title": ""}) == "Hecho."


# ── V2-463 — la tarjeta del reproductor se abre en el rail COMPARTIDO ───────────────────────────────────
def test_cargar_un_video_ABRE_la_tarjeta_tambien_desde_el_probe(monkeypatch):
    """Mismo agujero que el visor de imágenes: la voz emitía su `show` y el canal probe ninguno, así que una
    ronda medida reproducía sobre un canvas sin tarjeta. La apertura vive en `video_turn.execute`."""
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
