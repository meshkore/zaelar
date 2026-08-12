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
