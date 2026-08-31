"""V2-227 scope C — the sheet WIRING as the live progress surface.

The SCREEN contract was already green (`tests/browser/e2e/results/render_process_tab.py`, 6/6): that file mounts
`widget.js` on a blank page and manually passes it three payloads, so it tests that the sheet BEHAVES when the data
arrives. What it cannot test —and what was precisely missing for the operator to see anything— is that someone
PRODUCES that data: `view_data()` did not return `progress` at all, and nobody opened the sheet when placing an
order. A contract fulfilled in a test and absent from the product.

What is fixed here, in the order in which an order occurs:

  1. With nothing running, the sheet does not claim work (`alive: False`), which is different from saying nothing.
  2. When an order is PLACED, it opens — and opens EMPTY, without the tab the operator chose for the previous order.
  3. It is alive BEFORE the first phase: that gap of seconds is the blank screen the operator asked to remove, so
     it is the part that matters most.
  4. The phases from the LIVE record reach the sheet in order, without being stored in it.
  5. When it FINISHES, the loader stops and the history remains — persisted, because the report is too.

And both directions at every point where the fix could overreach: a surface that is NOT the sheet does not render
here, and an order that arrives while another is working does not erase what that one has already delivered.
"""
import time

import pytest

from nucleo import dispatch, surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """ISOLATED store and ISOLATED session registry.

    The second is not symmetry: `sheet_progress()` reads `dispatch._SESSIONS`, which is PROCESS state — without
    clearing it, a test that leaves a session inside paints «Trabajando…» on the next one and the failure points to
    nothing of its own. And the first already proved costly in this same directory: the first version of the sheet
    tests cleared the REAL store and deleted the report the operator had on screen.
    """
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


def _live(tid: str, goal: str, surface: str = "lista", phases=()) -> SessionRecord:
    """A LIVE session in the registry, sealed through the same gate that seals it in production."""
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, surface)
    rec.sheet = dispatch.sheet_id_for(tid)      # `_sheet_open` seals it in production; same here
    rec.status = "running"
    dispatch._SESSIONS[tid] = rec
    for ph in phases:
        dispatch.session_phase(tid, ph)
    return rec


# ── 1) with nothing running, the sheet does not claim work ───────────────────────────────────────────────────

def test_sin_encargo_vivo_la_hoja_no_dice_que_trabaja():
    assert sheet.view_data()["progress"] == {"alive": False, "phases": []}


# ── 2) the sheet opens when an order is PLACED ───────────────────────────────────────────────────────────────

def test_encargar_abre_SU_hoja_y_la_anterior_no_se_toca(monkeypatch):
    """V2-259 — this used to be called «open the EMPTY sheet»: the sheet was unique, so opening it for the first
    time meant DELETING the previous search, which is literally the «error of deleting searches» the operator asked
    to remove. Now an order opens ITS OWN (`results::<task_id>`) and the previous one remains intact where it was.
    The property has not been relaxed: it has become stronger, which is why both sheets are checked."""
    shown = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda k, l, **kw: shown.append((k, l, kw.get("extra", {}).get("id"))))
    sheet.apply_action("present", {"title": "Coches en Levante",
                                   "items": [{"title": "de la búsqueda ANTERIOR"}]})
    sheet.apply_action("tab", {"tab": "sources"})       # …and the operator looking at another tab

    rec = SessionRecord(task_id="t1", goal="Busca hoteles de 4 estrellas en Sevilla", kind="web")
    surfaces.set_once(rec, "lista")
    dispatch._sheet_open(rec)

    assert ("widget", "show", "results::" + dispatch.sheet_id_for("t1")) in shown, (
        "la hoja tiene que ABRIRSE al encargar, no al entregar — y con el id de SU instancia, que es lo que hace "
        "que el canvas pinte una tarjeta nueva en vez de reusar la de la búsqueda anterior")
    nueva = sheet.view_data(dispatch.sheet_id_for("t1"))
    assert nueva["items"] == [], "la hoja del encargo nuevo empieza en blanco"
    assert nueva["title"] == "Busca hoteles de 4 estrellas en Sevilla"
    assert nueva.get("tab") is None, "la pestaña elegida era del encargo ANTERIOR; arrastrarla tapa el proceso"

    vieja = sheet.view_data()
    assert [i["title"] for i in vieja["items"]] == ["de la búsqueda ANTERIOR"], (
        "estrenar dejó de significar borrar: la búsqueda anterior sigue en SU hoja")
    assert vieja["title"] == "Coches en Levante"


def test_dos_encargos_a_la_vez_son_dos_hojas_y_ninguno_pisa_al_otro():
    """The operator's request, word for word: «if we do 2 searches at once, 2 browsers and 2 results widgets will
    open, each with its own correlation_id». Before, this was a compromise —the sheet was unique, so the second
    order reused it without emptying it to avoid deleting the first one's data— and the price was that the operator
    saw the results of one search under the title of the other."""
    _live("t1", "Busca hoteles en Sevilla")
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Hoteles en Sevilla",
                                   "items": [{"title": "Bécquer"}]})

    rec2 = SessionRecord(task_id="t2", goal="Busca restaurantes en Madrid", kind="web")
    surfaces.set_once(rec2, "lista")
    dispatch._sheet_open(rec2)

    a, b = sheet.view_data(dispatch.sheet_id_for("t1")), sheet.view_data(dispatch.sheet_id_for("t2"))
    assert [i["title"] for i in a["items"]] == ["Bécquer"], "al primero no se le toca nada"
    assert a["title"] == "Hoteles en Sevilla"
    assert b["items"] == [] and b["title"] == "Busca restaurantes en Madrid"
    assert sheet.sheet_key(dispatch.sheet_id_for("t1")) != sheet.sheet_key("t2"), "dos encargos, dos claves"


# ── 3) alive BEFORE the first phase ───────────────────────────────────────────────────────────────────────────

def test_la_hoja_esta_viva_antes_de_la_primera_fase():
    """The gap between placing an order and the first phase is seconds of blank screen — exactly what the operator
    asked to remove. `alive` means «an order is in progress», not «it has said something»."""
    _live("t1", "Busca hoteles en Sevilla")
    assert sheet.view_data()["progress"] == {"alive": True, "phases": []}


# ── 4) phases from the live record reach the sheet ───────────────────────────────────────────────────────────

def test_las_fases_llegan_en_orden_desde_el_registro_vivo():
    _live("t1", "Busca hoteles en Sevilla",
          phases=["entrando en booking.com…", "aplicando filtro 4 estrellas…", "lanzando la búsqueda…"])
    pr = sheet.view_data()["progress"]
    assert pr["alive"] is True
    assert pr["phases"] == ["entrando en booking.com…", "aplicando filtro 4 estrellas…",
                            "lanzando la búsqueda…"]


def test_una_superficie_que_no_es_la_hoja_no_pinta_aqui():
    """Sensitivity. An order handled by voice does not need to open or move the sheet: if `alive` turned on for any
    worker, the sheet would say «Trabajando…» about work that will not land in it."""
    for surface in ("voz", "silenciosa", "widget"):
        dispatch._SESSIONS.clear()
        _live("t1", "Ponme música", surface=surface, phases=["buscando la canción…"])
        assert sheet.view_data()["progress"] == {"alive": False, "phases": []}, surface


def test_el_progreso_es_DERIVADO_y_no_se_guarda_en_la_hoja():
    """Storing it would mean having the same state in two places, and the one left on screen is always stale — a
    frozen «Trabajando…» over a worker that no longer exists."""
    _live("t1", "Busca hoteles en Sevilla", phases=["entrando en booking.com…"])
    sheet.apply_action("present", {"title": "Hoteles", "items": [{"title": "Bécquer"}]})
    guardado = store.load("results", {})
    assert "progress" not in guardado
    assert "counts" not in guardado


def test_la_hoja_SIN_instancia_sigue_entrelazando_los_encargos_vivos():
    """V2-259 gives each order its own sheet, and there `sheet_progress(task_id)` counts only its own data. But the
    sheet WITHOUT an instance still exists —it is the one the operator opens manually, with no order behind it— and
    for THAT sheet, interleaving in time order remains the honest answer: keeping one order would hide the other."""
    a = _live("t1", "Busca hoteles en Sevilla")
    b = _live("t2", "Busca restaurantes en Madrid")
    a.phases.append({"t": 100.0, "s": "entrando en booking.com…"})
    b.phases.append({"t": 101.0, "s": "entrando en thefork.es…"})
    a.phases.append({"t": 102.0, "s": "aplicando filtro 4 estrellas…"})
    assert sheet.view_data()["progress"]["phases"] == [
        "entrando en booking.com…", "entrando en thefork.es…", "aplicando filtro 4 estrellas…"]


# ── 5) when it FINISHES ──────────────────────────────────────────────────────────────────────────────────────

def test_al_terminar_el_loader_para_y_la_historia_se_queda():
    rec = _live("t1", "Busca hoteles en Sevilla",
                phases=["entrando en booking.com…", "lanzando la búsqueda…"])
    sheet.apply_action("present", {"title": "Hoteles en Sevilla", "items": [{"title": "Bécquer"}]})

    rec.status = "done"
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)

    pr = sheet.view_data(dispatch.sheet_id_for("t1"))["progress"]
    assert pr["alive"] is False, "nadie más avisa del final: sin esta escritura la tarjeta sigue «Trabajando…»"
    assert pr["phases"] == ["entrando en booking.com…", "lanzando la búsqueda…"]


def test_la_historia_sobrevive_al_informe_porque_se_PERSISTE():
    """The sheet survives a restart; a report whose explanation of how it was produced has disappeared tells only
    half of what happened."""
    rec = _live("t1", "Busca hoteles en Sevilla", phases=["entrando en booking.com…"])
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)
    assert store.load(sheet.sheet_key(dispatch.sheet_id_for("t1")), {}).get("process") == ["entrando en booking.com…"]
    assert sheet.view_data(dispatch.sheet_id_for("t1"))["progress"]["phases"] == ["entrando en booking.com…"]


def test_un_encargo_que_no_dijo_una_sola_fase_no_inventa_historia():
    rec = _live("t1", "Busca hoteles en Sevilla")
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)
    assert sheet.view_data(dispatch.sheet_id_for("t1"))["progress"] == {"alive": False, "phases": []}
    assert "process" not in store.load(sheet.sheet_key(dispatch.sheet_id_for("t1")), {})


def test_el_encargo_siguiente_estrena_su_historia_y_la_del_anterior_SIGUE():
    """An old account beneath a new order is worse than none: it explains a result that is no longer there. With
    separate sheets this is achieved without deleting anything — and the check has to look at BOTH, because after
    V2-259 asking the bare sheet always returns empty and the case would pass without testing anything."""
    rec = _live("t1", "Busca hoteles en Sevilla", phases=["entrando en booking.com…"])
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)

    rec2 = SessionRecord(task_id="t2", goal="Busca restaurantes en Madrid", kind="web")
    surfaces.set_once(rec2, "lista")
    dispatch._sheet_open(rec2)
    assert sheet.view_data(dispatch.sheet_id_for("t2"))["progress"]["phases"] == [], "el encargo nuevo no hereda el relato del viejo"
    assert sheet.view_data(dispatch.sheet_id_for("t1"))["progress"]["phases"] == ["entrando en booking.com…"], (
        "…y el viejo conserva el suyo: estrenar dejó de significar borrar")


# ── the operator's click on «Process» must PERSIST ───────────────────────────────────────────────────────────

def test_el_operador_puede_quedarse_en_la_pestana_de_proceso():
    """`process` was missing from `_TABS`, so the click returned `ok:false` and was not saved. The tab was rendered
    anyway (the widget switches immediately), and on the next data refresh —which arrives with EVERY phase during
    a live order— the derived state switched it back to Results."""
    sheet.apply_action("present", {"title": "Hoteles", "items": [{"title": "Bécquer"}]})
    assert sheet.apply_action("tab", {"tab": "process"})["ok"] is True
    assert sheet.view_data().get("tab") == "process"
    assert sheet.apply_action("tab", {"tab": "proceso"})["tab"] == "process"


def test_una_pestana_inventada_sigue_rechazandose():
    assert sheet.apply_action("tab", {"tab": "inventada"})["ok"] is False


# ── fail-soft: the sheet also mounts without a dispatcher ───────────────────────────────────────────────────

def test_sin_dispatcher_la_hoja_ensena_lo_guardado_y_no_revienta(monkeypatch):
    """A test of the sheet alone, or the widget mounted outside the engine: that is `alive: False` with its history,
    which is exactly what is shown — not an error."""
    rec = _live("t1", "Busca hoteles en Sevilla", phases=["entrando en booking.com…"])
    dispatch._SESSIONS.pop("t1", None)
    dispatch._sheet_close(rec)

    def _boom():
        raise RuntimeError("sin dispatcher")

    monkeypatch.setattr(dispatch, "sheet_progress", _boom)
    assert sheet.view_data(dispatch.sheet_id_for("t1"))["progress"] == {"alive": False, "phases": ["entrando en booking.com…"]}


# ── ORDER guard: the sheet reads the live record, so the end is written AFTER the pop ─────────────────────────

def test_el_cierre_de_la_hoja_va_despues_de_sacar_la_sesion_del_registro():
    """Otherwise, `sheet_progress()` would still see the session and the sheet would be saved saying that it is
    working. This is an ORDER guard on the code: reordering two lines does not fail noisily; it leaves the loader
    spinning forever."""
    import inspect
    src = inspect.getsource(dispatch._run_session)
    pop = src.rindex('_SESSIONS.pop(key, None)')
    cierre = src.rindex('_sheet_close(rec)')
    assert pop < cierre, "el `_sheet_close` tiene que ir DESPUÉS de sacar la sesión del registro"
