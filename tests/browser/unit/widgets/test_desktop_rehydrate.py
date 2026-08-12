"""
test_desktop_rehydrate.py — el ESCRITORIO tiene que volver como estaba.

Incidente del 2026-08-12: con una búsqueda en marcha el canvas tenía `['navegador::t1', 'navegador']`; el operador
recargó y se quedó en blanco. No fue un fallo de guardado — era el DISEÑO: `_persist()` excluía `navegador` por
nombre, o sea justo el widget que está en pantalla durante una tarea web. Y el único almacén era el `localStorage`,
que es **per-origen y per-navegador**: el mismo zaelar por `http://localhost:43917` y por
`https://local.zaelar.com:44317` son dos escritorios distintos, así que cambiar de puerta de entrada también parece
pérdida de datos. Aquí se fijan las tres piezas: qué se guarda, de dónde se restaura, y que Procesos no mienta
sobre lo que se cortó.
"""
import asyncio
import json
import pathlib

import pytest

from memory import db as memdb
from memory import embeddings as mememb

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")
CHATWALL = pathlib.Path("frontend/app/components/ChatWall.js")


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _desktop() -> str:
    return DESKTOP.read_text(encoding="utf-8")


# ── 1. qué se guarda: la tarjeta del navegador SÍ, sus pestañas NO ───────────────────────────────────────────
def test_the_browser_card_is_no_longer_excluded_from_the_desktop():
    """Era el ÚNICO widget excluido por nombre — y el que estaba en pantalla cuando todo se fue en blanco."""
    src = _desktop()
    assert 'id==="navegador"' not in src.replace(" ", "")


def test_per_task_browser_tabs_stay_ephemeral():
    """`navegador::t1` es UNA pestaña de UNA tarea: restaurarla pintaría algo que ya no existe."""
    src = _desktop()
    layout = src[src.index("_layout()"):src.index("_persist()")]
    assert 'id.includes("::")' in layout and "return" in layout


def test_the_geometry_travels_to_the_server_too():
    """El server es la red de seguridad del localStorage: sin esto, otro navegador no puede restaurar nada."""
    src = _desktop()
    report = src[src.index("_reportOpen()"):src.index("async restore()")]
    assert "layout:this._layout()" in report.replace(" ", "")
    assert "/api/canvas/state" in report


# ── 2. de dónde se restaura: local primero, server como red ─────────────────────────────────────────────────
def test_restore_falls_back_to_the_server_when_this_browser_has_nothing():
    src = _desktop()
    restore = src[src.index("async restore()"):src.index("\n  has(id){")]
    assert "/api/canvas/layout" in restore
    # …y SOLO como fallback: si este navegador tiene su escritorio, manda él (sigue siendo autoritativo del canvas).
    assert restore.index("hb_desktop") < restore.index("/api/canvas/layout")


def test_a_reset_still_wins_over_any_rehydration():
    """La época de wipe se comprueba ANTES: un reset deja el escritorio en blanco y nadie lo resucita."""
    src = _desktop()
    restore = src[src.index("async restore()"):src.index("\n  has(id){")]
    assert restore.index("/api/desktop/epoch") < restore.index("/api/canvas/layout")


# ── 3. el viaje completo por el servidor (guardar → recuperar) ──────────────────────────────────────────────
def _body(resp) -> dict:
    return json.loads(bytes(resp.body).decode("utf-8"))


def test_the_server_remembers_the_desktop_across_a_restart(fresh_db):
    from server.voice_api import canvas_layout, canvas_state

    layout = [{"id": "results", "q": "", "left": "120px", "top": "80px", "z": "22"},
              {"id": "navegador", "q": "", "left": "540px", "top": "90px", "z": "23"}]
    asyncio.run(canvas_state({"open": ["results", "navegador::t1", "navegador"], "layout": layout}))

    got = _body(asyncio.run(canvas_layout()))
    assert [it["id"] for it in got["items"]] == ["results", "navegador"]
    assert got["items"][0]["left"] == "120px"


def test_asking_for_a_desktop_that_was_never_saved_is_not_an_error(fresh_db):
    from server.voice_api import canvas_layout
    assert _body(asyncio.run(canvas_layout())) == {"items": [], "at": 0}


def test_the_desktop_geometry_never_reaches_the_prompt(fresh_db):
    """Las coordenadas de una tarjeta son ruido para el cerebro: van a `sys_kv`, no al ESTADO raíz.

    No es cosmético: `memory.api.compose_state` VUELCA cada escalar suelto del estado al prompt como
    «Clave: valor.» — un campo nuevo ahí se cuela en todos los turnos."""
    from memory import api as memapi
    from server.voice_api import canvas_state
    asyncio.run(canvas_state({"open": ["results"],
                              "layout": [{"id": "results", "left": "120px", "top": "80px", "z": "22"}]}))
    st = memapi.state()
    assert st["open_widgets"] == ["results"]                     # esto SÍ (el cerebro lo necesita)
    assert "120px" not in json.dumps(st, ensure_ascii=False, default=str)     # la geometría, NO


def test_a_layout_report_without_geometry_still_works(fresh_db):
    """Compatibilidad: un cliente viejo manda solo `open` y no debe romper ni borrar nada."""
    from server.voice_api import canvas_state
    r = asyncio.run(canvas_state({"open": ["results"]}))
    assert r.status_code == 200


# ── 4. Procesos no puede mentir sobre lo que se cortó ───────────────────────────────────────────────────────
def test_interrupted_work_is_not_painted_as_a_success():
    """Antes CUALQUIER estado desconocido caía a "done" con un ✓: una tarea muerta se veía terminada bien."""
    src = CHATWALL.read_text(encoding="utf-8")
    row = src[src.index("const histRow"):src.index("const procBody")]
    assert '"interrumpido"' in row
    assert '"✂"' in row or "'✂'" in row


# ── 5. ESCALAR la tarjeta a mano y que el esfuerzo no se pierda (2026-08-12) ─────────────────────────────────
# Petición del operador para la hoja de resultados, resuelta en el CANVAS porque vale para cualquier widget: «si
# yo lo quiero a pantalla completa tiene que ocupar gran parte del frontend, o lo puedo mover a mano pinchando en
# las esquinas». Hasta hoy solo existía el fullscreen NATIVO (que tapa el orbe y el chat, así que agrandar la hoja
# para hablar sobre ella con zaelar era imposible) y un `resize` por voz que ni siquiera se guardaba.
def test_every_card_can_be_grabbed_by_its_corners_and_edges():
    src = _desktop()
    for dir_ in ("nw", "ne", "sw", "se", "n", "s", "e", "w"):
        assert f'"hb-rz hb-rz-"+dir' in src or f"hb-rz-{dir_}" in src
    assert "_wireResize(card" in src and "MIN_W" in src, "con un mínimo: una tarjeta de 0px no se recupera"


def test_the_size_the_operator_chose_survives_a_refresh():
    """Sin esto, agrandar la hoja para leerla a gusto y recargar la devolvía a su tamaño de fábrica — la forma
    más rápida de que una función no se use."""
    src = _desktop()
    layout = src[src.index("_layout()"):src.index("_persist()")]
    assert "w:c.style.width" in layout.replace(" ", "") and "h:c.style.height" in layout.replace(" ", "")
    assert "_applyGeom(card, pos.w, pos.h)" in src, "y se vuelve a aplicar al restaurar"


def test_fullscreen_keeps_the_voice_reachable_unless_the_widget_says_otherwise():
    """«Pantalla completa» son DOS cosas. La nativa tapa el resto de zaelar: perfecta para un vídeo, pésima para
    una hoja de resultados —el operador la agranda JUSTO para seguir corrigiendo la búsqueda por voz—. Así que
    por defecto se maximiza DENTRO de la app, y la nativa la pide el widget en su manifest."""
    src = _desktop()
    fs = src[src.index("\n  fullscreen(id){"):src.index("nativeFullscreen(id){")]
    assert 'fullscreen === "native"' in fs and "this.maximize(id)" in fs
    man = json.loads(pathlib.Path("widgets/youtube/manifest.json").read_text())
    assert man.get("fullscreen") == "native", "un vídeo SÍ quiere tapar la pantalla"
    assert "fullscreen" not in json.loads(pathlib.Path("widgets/results/manifest.json").read_text()), \
        "una hoja de datos no: se maximiza sin perder el orbe"


def test_maximizing_is_a_toggle_that_can_be_undone():
    """Si no, «ponlo grande» sería una operación de ida sin vuelta y habría que recolocar la tarjeta a mano."""
    src = _desktop()
    mx = src[src.index("maximize(id){"):src.index("_addHandles(card){")]
    assert "card._restore" in mx and "card._restore = null" in mx


def test_a_widget_can_declare_the_size_it_needs_to_be_readable():
    """Una superficie de ancho fluido no puede deducir su tamaño del contenido: encogería a su tarjeta más
    estrecha. Lo declara el manifest y lo aplica el canvas — y solo si el operador no dejó uno suyo."""
    src = _desktop()
    assert "_applyPreferred(w.card, baseId)" in src
    assert "!(pos && (pos.w || pos.h))" in src, "el tamaño guardado por el operador manda sobre el preferido"
    man = json.loads(pathlib.Path("widgets/results/manifest.json").read_text())
    assert man["size"]["w"] >= 600 and man["size"]["h"] >= 400
    assert "size" in pathlib.Path("widgets/server_api.py").read_text(), \
        "y el índice compacto tiene que llevarlo: el canvas lo necesita ANTES de pedir el manifest"


def test_the_scroller_is_a_wrapper_the_widget_cannot_clobber():
    """Dos cosas a la vez. (a) Con la tarjeta ENTERA scrolleando, los tiradores —absolutos— se iban con el
    contenido y no se podían agarrar. (b) El scroller no puede ser el div del propio widget: un `widget.js` hace
    `el.className="hb-loquesea"` y se lleva por delante cualquier clase que le pongamos a su raíz, así que una
    regla sobre `.hb-body` no aplicaba a NADIE (cazado en vivo el 2026-08-12, con el scroll ya escrito y sin
    funcionar). El scroll es chrome de la tarjeta, como el grip o la ×."""
    src = _desktop()
    assert ".hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}" in src.replace("\n", "")
    assert "scroll.appendChild(body)" in src, "el widget monta DENTRO del scroller, no ES el scroller"
    assert "card.append(grip,mx,x,head,load,scroll)" in src


def test_navigating_returns_to_the_top_but_live_data_does_not_move_the_page():
    """«Ver detalle →» vive al final de una tarjeta: sin volver arriba el expediente se abre por la mitad. Pero un
    `append` del worker mientras el operador lee NO puede arrancarle la página de las manos."""
    src = _desktop()
    assert "top:()=>{" in src.replace(" ", "").replace("top:()=>{", "top:()=>{"), "el canvas ofrece el «vuelve arriba»"
    assert ".hb-scroll" in src
    wsrc = pathlib.Path("widgets/results/widget.js").read_text()
    assert "const WHERE = new WeakMap()" in wsrc
    assert "paint(navigated(el, data, cur))" in wsrc, "solo la NAVEGACIÓN resetea el scroll, no el refresco"
