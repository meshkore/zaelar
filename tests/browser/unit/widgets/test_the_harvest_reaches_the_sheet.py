"""V2-296 — the harvest WIRING: from the one that counts to the one that displays it, and what remains when the job dies.

Sibling to `test_sheet_is_the_live_process_surface.py` and for the same reason: the grid's SCREEN contract is
already green (`test_harvest_grid.mjs`), but that file passes it the figures by hand. It cannot prove that
someone PRODUCES them and that they arrive — which is exactly how this kind of fix can go green while nothing
appears on screen.

The chain has four links and EACH ONE can break independently:

  1. `tasks.tally()` accumulates them on the browser tab (the owner of the numbers).
  2. `dispatch.sheet_harvest(sheet)` SUMS them across the jobs for that sheet — a job can open two tabs, and
     two pages viewed are two pages, wherever they come from.
  3. `view_data()['harvest']` brings them out through the surface.
  4. `end_task()` saves them, because when the live record disappears the sheet has nowhere left to read from.

The fourth is what is really tested here. A report that survives the job but whose explanation of how much it
took to reach it evaporates tells only half of what happened.
"""
import pytest

from nucleo import dispatch, surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.navegador import tasks as nav
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Store, session records, and browser tabs, all three kept SEPARATE.

    The third is not window dressing: `tasks._tasks` is a module-level dictionary, so a tab left inside it adds
    its pages to the next test's total — and a contaminated counter does not fail, it comes out higher, which is
    the hardest kind of failure to spot.
    """
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    monkeypatch.setattr(nav, "_tasks", {})
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


def _encargo(tid: str, nav_task: str, goal: str = "Busca un monitor") -> SessionRecord:
    """A LIVE job with its tab, sealed through the same gates as in production."""
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, "lista")
    rec.sheet = dispatch.sheet_id_for(tid)
    rec.status = "running"
    rec.nav_task = nav_task
    dispatch._SESSIONS[tid] = rec
    nav._tasks[nav_task] = {"id": nav_task, "goal": goal}
    return rec


def _harvest_en_pantalla(hoja: str) -> dict:
    """Through the SAME gate that the canvas uses to open it: `view_data` receives the INSTANCE as a string
    (V2-259), which is what `desktop.js::show` passes it after splitting `results::<sheet>`. The first version
    of this helper gave it a dict and returned `{}` in three tests — without an error, because `_safe_sheet` of
    a dict is a strange string that simply matches no sheet. A helper that calls what it measures incorrectly
    falsely accuses the product."""
    return sheet.view_data(hoja).get("harvest") or {}


# ── 1) nothing counted, “we do not know” — which is NOT zero ─────────────────────────────────────────────────

def test_sin_encargo_la_hoja_no_inventa_ceros():
    """`{}`, not `{pages: 0, …}`. A zero asserts that it was checked and there was nothing; here it has not been
    checked. The grid relies on this distinction to know whether it should stay silent (see `test_harvest_grid.mjs`)."""
    assert dispatch.sheet_harvest("una-hoja-cualquiera") == {}
    assert _harvest_en_pantalla("una-hoja-cualquiera") == {}


def test_un_encargo_sin_contar_todavia_tampoco_pinta_ceros():
    """The gap of seconds between assigning the job and the first extraction. That is when filling in zeroes is
    MOST tempting."""
    rec = _encargo("t1", "nav1")
    assert dispatch.sheet_harvest(rec.sheet) == {}


# ── 2) what the tab counts reaches the screen ─────────────────────────────────────────────────────────────────

def test_lo_que_cuenta_la_pestana_sale_por_la_hoja():
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=1, rows=40, repeated=9, unnamed=4, hollow=5, kept=22, offered=3)

    vivo = dispatch.sheet_harvest(rec.sheet)
    assert vivo["pages"] == 1 and vivo["rows"] == 40 and vivo["kept"] == 22
    assert _harvest_en_pantalla(rec.sheet) == vivo, "the sheet displays something different from what the record says"


def test_dos_paginas_del_mismo_encargo_SUMAN():
    """`tally` is cumulative: viewing two pages means two pages, not the last one."""
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=1, rows=40, kept=22)
    nav.tally("nav1", pages=1, rows=18, kept=7)
    vivo = dispatch.sheet_harvest(rec.sheet)
    assert (vivo["pages"], vivo["rows"], vivo["kept"]) == (2, 58, 29)


def test_dos_PESTANAS_de_la_misma_hoja_tambien_suman():
    """A job can search in two places at once. Two pages viewed are two pages, wherever they come from — and
    this is what breaks if someone decides that the harvest is “the one from the active tab.”"""
    rec1 = _encargo("t1", "nav1")
    rec2 = SessionRecord(task_id="t2", goal="Busca un monitor", kind="web")
    surfaces.set_once(rec2, "lista")
    rec2.sheet = rec1.sheet                      # MISMA hoja: es el mismo encargo
    rec2.status = "running"
    rec2.nav_task = "nav2"
    dispatch._SESSIONS["t2"] = rec2
    nav._tasks["nav2"] = {"id": "nav2", "goal": "Busca un monitor"}

    nav.tally("nav1", pages=1, rows=40, kept=22)
    nav.tally("nav2", pages=2, rows=11, kept=4)
    vivo = dispatch.sheet_harvest(rec1.sheet)
    assert (vivo["pages"], vivo["rows"], vivo["kept"]) == (3, 51, 26)


def test_la_cosecha_de_OTRA_hoja_no_se_cuela():
    """The symmetrical defect, and the more costly one: adding too much displays another job's work on the
    operator's sheet, and that does not look strange — it looks like a higher number."""
    mio = _encargo("t1", "nav1")
    otro = _encargo("t9", "nav9", goal="Busca un hotel")
    nav.tally("nav1", pages=1, rows=40, kept=22)
    nav.tally("nav9", pages=7, rows=90, kept=50)
    assert dispatch.sheet_harvest(mio.sheet)["pages"] == 1
    assert dispatch.sheet_harvest(otro.sheet)["pages"] == 7


# ── 3) the link that is really tested: surviving the job's death ──────────────────────────────────────────────

def test_los_numeros_SOBREVIVEN_a_que_el_encargo_muera():
    """The real case: it ends, the live record disappears, and the sheet is left looking. Without persistence,
    the grid goes dark just when the operator is about to read the report — and with it the only explanation of
    why the result is what it is."""
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=3, rows=40, repeated=9, unnamed=4, hollow=5, kept=22, offered=3)
    vivo = dict(dispatch.sheet_harvest(rec.sheet))

    sheet.end_task(["entrando en es.wallapop.com", "leyendo 40 fichas"], sheet=rec.sheet)
    dispatch._SESSIONS.clear()                   # the job DIES: there is nowhere left to read from live
    nav._tasks.clear()

    assert dispatch.sheet_harvest(rec.sheet) == {}, "without a live job there is no live reading; that is the assumption"
    guardado = _harvest_en_pantalla(rec.sheet)
    assert guardado == vivo, "the numbers did not survive the job: the sheet lost half the story"


def test_un_encargo_que_no_conto_NADA_no_guarda_ceros():
    """The other half of the same rule. Persisting `{pages: 0, …}` is worse than not persisting: the sheet would
    display forever that zero pages were viewed, which is an assertion, not an absence."""
    rec = _encargo("t1", "nav1")
    sheet.end_task(["entrando en es.wallapop.com"], sheet=rec.sheet)
    dispatch._SESSIONS.clear()
    assert _harvest_en_pantalla(rec.sheet) == {}


def test_el_registro_VIVO_manda_sobre_lo_guardado():
    """A new job on the same sheet has to display ITS OWN data, not the previous one's memory. State in two places
    always ends the same way: what remains on screen is the stale one."""
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=3, rows=40, kept=22)
    sheet.end_task(["ya terminé"], sheet=rec.sheet)
    dispatch._SESSIONS.clear()
    nav._tasks.clear()
    assert _harvest_en_pantalla(rec.sheet)["pages"] == 3

    nuevo = _encargo("t2", "nav2")
    nuevo.sheet = rec.sheet                      # the operator assigns a new job on the same sheet
    dispatch._SESSIONS["t2"] = nuevo
    nav.tally("nav2", pages=1, rows=5, kept=5)
    assert _harvest_en_pantalla(rec.sheet)["pages"] == 1, "the sheet is still displaying the harvest from the dead job"


# ── 4) the counter does not allow invented keys ────────────────────────────────────────────────────────────────

def test_una_clave_que_no_existe_se_tira_en_vez_de_guardarse():
    """A typo must not create a counter that no surface reads and no test covers — it would remain there adding
    silently, and the day someone displays it there would be no way to know how long it had been lying."""
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=1, paginas=99, kept=1)
    vivo = dispatch.sheet_harvest(rec.sheet)
    assert "paginas" not in vivo and vivo["pages"] == 1
