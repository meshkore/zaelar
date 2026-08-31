"""V2-259 — two searches are two sheets, and starting fresh no longer means deleting.

WHAT THE OPERATOR REQUESTED (2026-08-21, verbatim): “if we have an open results widget, a completed search, and
launch another one, a new widget opens. With this rule we will not make mistakes by deleting searches.”

And the deletion the operator feared WAS IN THE CODE, with its comment: `dispatch._sheet_open()` called
`begin_task(fresh=True)`, which started the sheet —new title, with no results or history— as soon as the next
errand arrived. There was only one sheet (`store.load(WIDGET_ID)`, a single key), so the choice was: either start
fresh and delete what had been delivered to whoever kept writing, or reuse it and show the previous search’s
results under this one’s title. Neither is good; both had been measured.

THE KEY IS THE ERRAND, NOT THE BROWSER. This is the exact continuation of V2-257: the browser card SHOWS
(N cards), and the sheet STORES the findings regardless of which browser they come from. Thus two browsers for the
same errand still land in the same sheet, and two errands are two sheets.

What is fixed here is the boundary and its two edges: two errands must not overwrite one another, and whoever WRITES
must know which one — a writer without a sheet writes into nobody’s while the operator watches theirs, a silent bug.
"""
from pathlib import Path

import pytest

from nucleo import dispatch, surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.results import data as sheet, intake

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    store._last_hash.clear()
    yield
    store._last_hash.clear()


def _encargo(tid: str, goal: str, nav: str = "") -> SessionRecord:
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, "lista")
    rec.sheet = dispatch.sheet_id_for(tid)      # `_sheet_open` seals it in production; same here
    rec.status = "running"
    if nav:
        rec.nav_task = nav
    dispatch._SESSIONS[tid] = rec
    return rec


# ── 1) the key ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_bare_sheet_keeps_its_key_byte_for_byte():
    """Today’s sheet has data on disk under the old key. Changing it would leave TWO live lineages — exactly the
    situation in V2-242, where `weather:soria` and `meteo-soria:weather:soria` both coexisted with `valid=1`."""
    assert sheet.sheet_key("") == "results"
    assert sheet.sheet_key("t1") == "results--t1"
    assert sheet.instance_id("t1") == "results::t1", "el canvas usa «::»; el disco no lo admite"


def test_a_hostile_correlation_id_cannot_escape_its_directory():
    assert sheet.sheet_key("../../etc") == "results--etc"
    assert sheet.sheet_key("a b/c:d") == "results--abcd"
    assert sheet.sheet_key("   ") == "results", "un id en blanco no es una instancia"


# ── 2) two errands do not overwrite one another ────────────────────────────────────────────────────────────────

def test_two_errands_do_not_overwrite_each_other():
    _encargo("t1", "Busca fontaneros en Madrid")
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Fontaneros", "items": [{"title": "Relatores"}]})

    rec2 = _encargo("t2", "Busca un coche de segunda mano")
    dispatch._sheet_open(rec2)

    assert [i["title"] for i in sheet.view_data(dispatch.sheet_id_for("t1"))["items"]] == ["Relatores"]
    assert sheet.view_data(dispatch.sheet_id_for("t2"))["items"] == []
    assert sheet.view_data(dispatch.sheet_id_for("t1"))["title"] == "Fontaneros"
    assert sheet.view_data(dispatch.sheet_id_for("t2"))["title"] == "Busca un coche de segunda mano"


def test_the_next_errand_no_longer_wipes_the_finished_one():
    """The operator’s EXACT case: a search is complete, another arrives. Previously this deleted the first one."""
    rec1 = _encargo("t1", "Busca fontaneros en Madrid")
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Fontaneros", "items": [{"title": "Relatores"}]})
    rec1.status = "done"
    dispatch._SESSIONS.pop("t1")
    dispatch._sheet_close(rec1)

    dispatch._sheet_open(_encargo("t2", "Busca un coche"))
    assert [i["title"] for i in sheet.view_data(dispatch.sheet_id_for("t1"))["items"]] == ["Relatores"], (
        "la búsqueda TERMINADA se borraba al llegar la siguiente — es el «error de borrar búsquedas» que el "
        "operador pidió quitar")


def test_each_card_tells_ITS_own_story():
    """With a single sheet, the phases were interleaved in time order, which was the honest answer. With separate
    sheets, two boxes telling the same mixed-up story is lying with a larger surface area."""
    a, b = _encargo("t1", "hoteles"), _encargo("t2", "restaurantes")
    a.phases.append({"t": 100.0, "s": "entrando en booking.com…"})
    b.phases.append({"t": 101.0, "s": "entrando en thefork.es…"})
    assert sheet.view_data(dispatch.sheet_id_for("t1"))["progress"]["phases"] == ["entrando en booking.com…"]
    assert sheet.view_data(dispatch.sheet_id_for("t2"))["progress"]["phases"] == ["entrando en thefork.es…"]
    assert sheet.view_data()["progress"]["phases"] == ["entrando en booking.com…", "entrando en thefork.es…"], (
        "la hoja SIN encargo detrás —la que el operador abre a mano— sigue mereciendo el relato completo")


# ── 3) whoever WRITES knows which one ─────────────────────────────────────────────────────────────────────────

def test_two_browsers_of_the_SAME_errand_land_in_the_SAME_sheet():
    """The V2-257 boundary still stands: the sheet belongs to the ERRAND, not the browser."""
    _encargo("t1", "Busca fontaneros", nav="nav-A")
    assert dispatch.sheet_for_nav_task("nav-A") == dispatch.sheet_id_for("t1")
    intake.push([{"title": "Relatores", "tel": "910"}], sheet=dispatch.sheet_for_nav_task("nav-A"))
    _encargo("t1b", "otro navegador del mismo encargo")     # noise: it is not attached to nav-A
    dispatch._SESSIONS["t1"].nav_task = "nav-A"
    intake.push([{"title": "GASFONCLIMA", "tel": "911"}], sheet=dispatch.sheet_for_nav_task("nav-A"))
    assert [i["title"] for i in sheet.view_data(dispatch.sheet_id_for("t1"))["items"]] == ["Relatores", "GASFONCLIMA"]


def test_a_browser_with_no_errand_behind_it_writes_the_bare_sheet():
    """The operator driving the browser manually: there is no errand, so the usual sheet is the right one."""
    assert dispatch.sheet_for_nav_task("suelto") == ""
    intake.push([{"title": "algo"}], sheet=dispatch.sheet_for_nav_task("suelto"))
    assert [i["title"] for i in sheet.view_data()["items"]] == ["algo"]


@pytest.mark.parametrize("rel", ["widgets/navegador/act_api.py", "widgets/navegador/owner.py",
                                 "nucleo/dispatch.py"])
def test_no_writer_pushes_without_naming_its_sheet(rel):
    """The guardrail needed here and not in V2-257: back then, knocking on the door was enough; now they have to
    say WHICH sheet. A `push` without `sheet=` does not fail — it writes into the box nobody is watching."""
    src = (ENGINE / rel).read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.splitlines()):
        if "intake.push(" in line and "def " not in line:
            bloque = "\n".join(src.splitlines()[i:i + 3])
            assert "sheet=" in bloque, f"{rel}:{i + 1} entrega a la hoja sin decir a cuál"


def test_the_worker_bridge_resolves_the_sheet_so_the_worker_never_has_to():
    """The worker’s prompt says “deliver to the `results` sheet” (V2-257), and with instances that bare name is no
    longer an address. The BRIDGE resolves it: a worker should not need to know instance IDs."""
    src = (ENGINE / "nucleo/worker_api.py").read_text(encoding="utf-8")
    assert 'wid == "results"' in src and '"sheet"' in src, (
        "sin esto el worker escribe en la hoja de nadie mientras el operador mira la de su encargo")


# ── 4) the brain sees ALL sheets ───────────────────────────────────────────────────────────────────────────────

def test_the_brain_sees_every_open_sheet_and_says_which_is_which():
    """Reading only one gives no warning: the turn would confidently answer about the wrong search. “Number two”
    with two sheets on screen means two different things."""
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Fontaneros", "items": [{"title": "Relatores"}]})
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t2"), "title": "Coches", "items": [{"title": "Ibiza 2019"}]})

    refs = sheet.ref_index()
    assert {r["id"] for r in refs} == {"Relatores", "Ibiza 2019"}
    assert all("de «" in r["hint"] for r in refs), "cada referencia dice de qué hoja es"

    dig = sheet.prompt_digest()
    assert "Fontaneros" in dig and "Coches" in dig
    assert "Relatores" in dig and "Ibiza 2019" in dig

    solo = sheet.prompt_digest(dispatch.sheet_id_for("t1"))
    assert "Relatores" in solo and "Ibiza 2019" not in solo, "y se puede pedir UNA cuando se sabe cuál"


def test_with_one_sheet_the_digest_says_nothing_about_sheets():
    """Without two searches there is no ambiguity to disambiguate, and adding the heading anyway would be noise in
    every prompt of every turn."""
    sheet.apply_action("present", {"sheet": dispatch.sheet_id_for("t1"), "title": "Fontaneros", "items": [{"title": "Relatores"}]})
    assert "── HOJA" not in sheet.prompt_digest()
    assert all("de «" not in r["hint"] for r in sheet.ref_index())


# ── 5) the sheet persists, so N sheets need a ceiling ──────────────────────────────────────────────────────────

def test_the_sheets_do_not_grow_without_a_ceiling():
    """The sheet PERSISTS deliberately (a report survives a restart, V2-233). N persisted instances grow without
    end, and silent trimming is worse than an announced one."""
    for n in range(sheet._MAX_SHEETS + 3):
        sheet.apply_action("present", {"sheet": f"t{n}", "title": f"Búsqueda {n}",
                                       "items": [{"title": f"r{n}"}]})
    assert len([s for s in sheet.sheets() if s]) == sheet._MAX_SHEETS + 3
    tiradas = sheet.prune_sheets()
    quedan = [s for s in sheet.sheets() if s]
    assert tiradas == 3 and len(quedan) == sheet._MAX_SHEETS
    assert f"t{sheet._MAX_SHEETS + 2}" in quedan, "se conservan las MÁS RECIENTES"
    assert "t0" not in quedan


def test_pruning_never_touches_the_bare_sheet():
    """It belongs to no errand: no one should delete it."""
    sheet.apply_action("present", {"title": "la de siempre", "items": [{"title": "x"}]})
    for n in range(sheet._MAX_SHEETS + 2):
        sheet.apply_action("present", {"sheet": f"t{n}", "items": [{"title": f"r{n}"}]})
    sheet.prune_sheets()
    assert [i["title"] for i in sheet.view_data()["items"]] == ["x"]


# ── 6) the sheet ID has to survive a RESTART ──────────────────────────────────────────────────────────────────

def test_the_sheet_id_does_not_repeat_across_restarts():
    """The harness caught it in this same newly built initiative, and it is the defect V2-259 exists to remove,
    reintroduced through the back door: `escalate._seq` starts at 0 in EACH process, so `task_id` values repeat
    across restarts. With the sheet named by the bare `task_id`, the first errand of a new startup landed in
    `results--1` —the previous session’s sheet— and `begin_task(fresh=True)` STARTED it fresh, effectively deleting
    it. A report the operator wanted to preserve, silently destroyed.

    So the ID carries a PROCESS stamp. The sheet is stored on disk and survives a restart (V2-233): its name must
    survive just as well.
    """
    assert dispatch.sheet_id_for("1") != "1", "el id de hoja no puede ser el task_id a pelo"
    assert dispatch.sheet_id_for("1").endswith("-1")
    # F5 (2026-08-23): the stamp is no longer a private `_BOOT` in this module — it is emitted by the OWNER of
    # process identity (`nucleo/runtime_ids.py`), which prevents the next standalone counter from being created.
    # What this case asserts is unchanged: the sheet ID includes a stamp that differs on every startup.
    from nucleo import runtime_ids
    assert runtime_ids.boot_id() and runtime_ids.boot_id() in dispatch.sheet_id_for("1")
    # two different “startups”, the same task_id, two sheets
    otro = "otroboot"
    assert sheet.sheet_key(dispatch.sheet_id_for("1")) != sheet.sheet_key(f"{otro}-1")


def test_the_sheet_is_stamped_ONCE_like_the_surface():
    """Same principle as `surfaces.set_once`: changing sheets halfway through is not correcting; it is moving what
    the operator is already watching."""
    rec = _encargo("t1", "Busca fontaneros")
    primero = dispatch.sheet_of(rec)
    dispatch._sheet_open(rec)
    assert dispatch.sheet_of(rec) == primero


def test_an_errand_with_no_sheet_writes_the_bare_one():
    """`sheet_of` does NOT reconstruct the ID from the task_id: an errand whose sheet was never opened has no sheet,
    and fabricating one would make a voice errand —with no surface— write into a box nobody opened."""
    from nucleo.workers.session import SessionRecord
    rec = SessionRecord(task_id="t9", goal="dime la hora", kind="generic")
    assert dispatch.sheet_of(rec) == ""
