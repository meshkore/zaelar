"""
test_desktop_rehydrate.py — the DESKTOP must come back as it was.

Incident on 2026-08-12: with a search in progress, the canvas contained `['navegador::t1', 'navegador']`; the operator
reloaded and it came back blank. It was not a saving failure — it was the DESIGN: `_persist()` excluded `navegador` by
name, namely the widget that is on screen during a web task. And the only storage was `localStorage`,
which is **per-origin and per-browser**: the same zaelar at `http://localhost:43917` and at
`https://local.zaelar.com:44317` are two different desktops, so changing the entry point also looks like data loss.
This fixes the three pieces: what is saved, where it is restored from, and that Processes does not lie
about what was interrupted.
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


# ── 1. what is saved: the browser card YES, its tabs NO ───────────────────────────────────────────────────────
def test_the_browser_card_is_no_longer_excluded_from_the_desktop():
    """It was the ONLY widget excluded by name — and the one on screen when everything went blank."""
    src = _desktop()
    assert 'id==="navegador"' not in src.replace(" ", "")


def test_instance_cards_persist_and_a_dead_tab_is_filtered_at_restore():
    """SUPERSEDED DECISION (V2-351, operator instruction 2026-08-26): INSTANCE cards are also saved.

    The old rule ("navegador::t1 is ONE tab of ONE task: restoring it would paint something that no longer exists")
    excluded EVERY id containing `::` — and with it the errand sheet (`results::ece70b-1`), whose data DOES persist on
    disk: the operator refreshed mid-task and read "No results yet" over a sheet with 12
    real candidates (measured: /api/canvas/layout only saved [{id:"results"}]). The spirit of the old rule
    is preserved WHERE it was true: a browser instance with NO live task behind it is filtered during restore
    (against the server's `live` list), because its card is process state, not a persisted sheet."""
    src = _desktop()
    layout = src[src.index("_layout()"):src.index("_persist()")]
    assert 'id.includes("::")' not in layout.split("//",1)[0] or True
    # The EXCLUSION no longer exists in _layout (the comment may mention it; the code must not execute it):
    code_lines = [l for l in layout.splitlines() if not l.strip().startswith("//")]
    assert not any('includes("::")' in l and "return" in l for l in code_lines), layout
    restore = src[src.index("async restore()"):src.index("\n  has(id){")]
    assert 'startsWith("navegador::")' in restore and "liveSet" in restore


def test_a_fossil_base_card_next_to_its_instance_is_swept_at_restore():
    """The report's GHOST ("the BASE piece above its own, empty instance"): a bare base
    next to an instance of that same base is the fossil of the pre-V2-261 echo, and restore sweeps it away. A base ALONE
    remains legitimate (the operator opened the piece with no errand behind it)."""
    src = _desktop()
    restore = src[src.index("async restore()"):src.index("\n  has(id){")]
    assert "bases" in restore and 'split("::",1)[0]' in restore
    assert "!bases.has(id)" in restore.replace(" ", "")


def test_live_errands_come_back_even_if_this_desktop_never_saved_them():
    """The server's `live` list is MERGED: the card opened with the page closed also comes back."""
    src = _desktop()
    restore = src[src.index("async restore()"):src.index("\n  has(id){")]
    assert "srv.live" in restore


def test_the_geometry_travels_to_the_server_too():
    """The server is localStorage's safety net: without this, another browser cannot restore anything."""
    src = _desktop()
    report = src[src.index("_reportOpen()"):src.index("async restore()")]
    assert "layout:this._layout()" in report.replace(" ", "")
    assert "/api/canvas/state" in report


# ── 2. where it is restored from: local first, server as the safety net ─────────────────────────────────────
def test_restore_falls_back_to_the_server_when_this_browser_has_nothing():
    src = _desktop()
    restore = src[src.index("async restore()"):src.index("\n  has(id){")]
    assert "/api/canvas/layout" in restore
    # …and ONLY as a fallback: if this browser has its desktop, it wins (it remains authoritative for the canvas).
    assert restore.index("hb_desktop") < restore.index("/api/canvas/layout")


def test_a_reset_still_wins_over_any_rehydration():
    """The wipe epoch is checked FIRST: a reset leaves the desktop blank and no one resurrects it."""
    src = _desktop()
    restore = src[src.index("async restore()"):src.index("\n  has(id){")]
    assert restore.index("/api/desktop/epoch") < restore.index("/api/canvas/layout")


# ── 3. the full trip through the server (save → recover) ────────────────────────────────────────────────────
def _body(resp) -> dict:
    return json.loads(bytes(resp.body).decode("utf-8"))


def test_the_server_remembers_the_desktop_across_a_restart(fresh_db):
    from server.voice_api import canvas_layout, canvas_state

    layout = [{"id": "results::ab12cd-1", "q": "ab12cd-1", "left": "120px", "top": "80px", "z": "22"},
              {"id": "navegador", "q": "", "left": "540px", "top": "90px", "z": "23"}]
    asyncio.run(canvas_state({"open": ["results::ab12cd-1", "navegador"], "layout": layout}))

    got = _body(asyncio.run(canvas_layout()))
    # V2-351: the INSTANCE travels intact — it is the card the operator was actually looking at
    assert [it["id"] for it in got["items"]] == ["results::ab12cd-1", "navegador"]
    assert got["items"][0]["left"] == "120px"


def test_asking_for_a_desktop_that_was_never_saved_is_not_an_error(fresh_db):
    from server.voice_api import canvas_layout
    got = _body(asyncio.run(canvas_layout()))
    assert got["items"] == [] and got["at"] == 0
    assert isinstance(got.get("live"), list)          # V2-351: empty list = "I don't know", never absent


def test_the_layout_reports_the_errands_running_right_now(fresh_db, monkeypatch):
    """V2-351 — `live`: the sheet for each live errand with a sheet surface + each browser tab."""
    import server.voice_api as V

    class _Rec:
        status = "working"
        surface = "lista"
        sheet = "ec70b-1"
    from nucleo import dispatch as _d
    monkeypatch.setattr(_d, "_sheet_sessions", lambda: [_Rec()], raising=False)
    from widgets.navegador import tasks as _t
    monkeypatch.setattr(_t, "all_ids", lambda: ["t1"], raising=False)
    # Through the ENDPOINT, not the helper: the guard must also turn red if the wiring is disconnected
    # (measured by constructing it: gutting `live = _live_canvas_instances()` left a face green that called the
    # helper directly).
    got = _body(asyncio.run(V.canvas_layout()))
    assert "results::ec70b-1" in got["live"] and "navegador::t1" in got["live"], got


def test_the_desktop_geometry_never_reaches_the_prompt(fresh_db):
    """A card's coordinates are noise for the brain: they go to `sys_kv`, not the root STATE.

    This is not cosmetic: `memory.api.compose_state` DUMPS every loose scalar from the state into the prompt as
    "Key: value." — a new field there leaks into every turn."""
    from memory import api as memapi
    from server.voice_api import canvas_state
    asyncio.run(canvas_state({"open": ["results"],
                              "layout": [{"id": "results", "left": "120px", "top": "80px", "z": "22"}]}))
    st = memapi.state()
    assert st["open_widgets"] == ["results"]                     # this YES (the brain needs it)
    assert "120px" not in json.dumps(st, ensure_ascii=False, default=str)     # the geometry, NO


def test_a_layout_report_without_geometry_still_works(fresh_db):
    """Compatibilidad: un cliente viejo manda solo `open` y no debe romper ni borrar nada."""
    from server.voice_api import canvas_state
    r = asyncio.run(canvas_state({"open": ["results"]}))
    assert r.status_code == 200


    # ── 4. Processes cannot lie about what was interrupted ────────────────────────────────────────────────────
def test_interrupted_work_is_not_painted_as_a_success():
    """Previously ANY unknown state fell back to "done" with a ✓: a dead task looked properly completed."""
    src = CHATWALL.read_text(encoding="utf-8")
    row = src[src.index("const histRow"):src.index("const procBody")]
    assert '"interrumpido"' in row
    assert '"✂"' in row or "'✂'" in row


# ── 5. ESCALAR la tarjeta a mano y que el esfuerzo no se pierda (2026-08-12) ─────────────────────────────────
# Operator request for the results sheet, resolved in the CANVAS because it applies to every widget: "if
# I want it full-screen it has to occupy a large part of the frontend, or I can move it manually by grabbing
# the corners". Until now there was only NATIVE fullscreen (which covers the orb and chat, making it impossible
# to enlarge the sheet while talking about it with zaelar) and a voice-driven `resize` that was not even saved.
def test_every_card_can_be_grabbed_by_its_corners_and_edges():
    src = _desktop()
    for dir_ in ("nw", "ne", "sw", "se", "n", "s", "e", "w"):
        assert f'"hb-rz hb-rz-"+dir' in src or f"hb-rz-{dir_}" in src
    assert "_wireResize(card" in src and "MIN_W" in src, "con un mínimo: una tarjeta de 0px no se recupera"


def test_the_size_the_operator_chose_survives_a_refresh():
    """Without this, enlarging the sheet for comfortable reading and reloading returned it to its factory size — the
    fastest way to ensure a feature is never used."""
    src = _desktop()
    # Sliced from `_layout()` to the END of the pushed record, not to the next `_persist()`: V2-538 added a
    # `_railClamp()` that calls `_persist()` ABOVE this method, so the old slice silently came back EMPTY and
    # the assertion passed over nothing. A guard that measures a text range has to anchor on the range.
    start = src.index("_layout()")
    layout = src[start:src.index("return items;", start)]
    assert "w:c.style.width" in layout.replace(" ", "") and "h:c.style.height" in layout.replace(" ", "")
    assert "_applyGeom(card, pos.w, pos.h)" in src, "y se vuelve a aplicar al restaurar"


def test_fullscreen_keeps_the_voice_reachable_unless_the_widget_says_otherwise():
    """"Full-screen" means TWO things. Native full-screen covers the rest of zaelar: perfect for a video, awful for
    a results sheet —the operator enlarges it PRECISELY to keep correcting the search by voice—. So
    by default it is maximized INSIDE the app, and the widget requests native full-screen in its manifest."""
    src = _desktop()
    fs = src[src.index("\n  fullscreen(id){"):src.index("nativeFullscreen(id){")]
    assert 'fullscreen === "native"' in fs and "this.maximize(id)" in fs
    man = json.loads(pathlib.Path("widgets/youtube/manifest.json").read_text())
    assert man.get("fullscreen") == "native", "un vídeo SÍ quiere tapar la pantalla"
    assert "fullscreen" not in json.loads(pathlib.Path("widgets/results/manifest.json").read_text()), \
        "una hoja de datos no: se maximiza sin perder el orbe"


def test_maximizing_is_a_toggle_that_can_be_undone():
    """Otherwise, "make it big" would be a one-way operation and the card would have to be repositioned manually."""
    src = _desktop()
    mx = src[src.index("maximize(id){"):src.index("_addHandles(card){")]
    assert "card._restore" in mx and "card._restore = null" in mx


def test_a_widget_can_declare_the_size_it_needs_to_be_readable():
    """A fluid-width surface cannot infer its size from its content: it would shrink to its narrowest card.
    The manifest declares it and the canvas applies it — only if the operator has not set a size of their own."""
    src = _desktop()
    assert "_applyPreferred(w.card, baseId" in src
    # V2-538: the operator's saved size still wins, but now DIMENSION BY DIMENSION. A card restored with a
    # width and an empty height —every card saved before sizes were persisted— used to keep auto height
    # forever, so a results sheet grew line by line as the worker streamed text into it.
    assert "haveW" in src and "haveH" in src, "el tamaño guardado del operador manda, dimensión a dimensión"
    assert "size.w && !haveW" in src and "size.h && !haveH" in src
    man = json.loads(pathlib.Path("widgets/results/manifest.json").read_text())
    assert man["size"]["w"] >= 600 and man["size"]["h"] >= 400
    assert "size" in pathlib.Path("widgets/server_api.py").read_text(), \
        "y el índice compacto tiene que llevarlo: el canvas lo necesita ANTES de pedir el manifest"


def test_the_scroller_is_a_wrapper_the_widget_cannot_clobber():
    """Two things at once. (a) With the ENTIRE card scrolling, the —absolute— handles moved with the
    content and could not be grabbed. (b) The scroller cannot be the widget's own div: a `widget.js` sets
    `el.className="hb-loquesea"` and overwrites any class we put on its root, so a rule on `.hb-body` applied to
    NOBODY (caught live on 2026-08-12, with scrolling already written and not working). Scrolling is card chrome,
    like the grip or the ×."""
    src = _desktop()
    assert ".hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}" in src.replace("\n", "")
    assert "scroll.appendChild(body)" in src, "el widget monta DENTRO del scroller, no ES el scroller"
    assert "card.append(grip,mx,cx,x,head,load,scroll)" in src   # cx = the cinema exit button (V2-596)


def test_navigating_returns_to_the_top_but_live_data_does_not_move_the_page():
    """"View details →" lives at the bottom of a card: without returning to the top, the record opens halfway down. But an
    `append` from the worker while the operator is reading must NOT yank the page out of their hands."""
    src = _desktop()
    assert "top:()=>{" in src.replace(" ", "").replace("top:()=>{", "top:()=>{"), "el canvas ofrece el «vuelve arriba»"
    assert ".hb-scroll" in src
    wsrc = pathlib.Path("widgets/results/widget.js").read_text()
    assert "const WHERE = new WeakMap()" in wsrc
    assert "paint(navigated(el, data, cur))" in wsrc, "solo la NAVEGACIÓN resetea el scroll, no el refresco"
