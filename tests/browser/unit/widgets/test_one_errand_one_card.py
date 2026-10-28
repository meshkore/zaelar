"""V2-797 — one errand presents ONE card, and a resumed errand keeps it.

Measured: one request («reserve a table for two tomorrow at 14:00 in the town centre») opened THREE cards — the
browser's monitor card when the errand started (it had no sheet yet), the results sheet when the worker wrote its
first rows, and after a restart a SECOND sheet beside the first, because the resumed worker named its sheet after
the new boot instead of after its durable row.

The rule (`nucleo/errand_card.py`):
  1. starting an errand opens no card; its deliverable (the sheet, whose PROCESS tab embeds the browser) is the card;
  2. when he must act in the page (a wall, a login) the errand's sheet is raised — opened then if it had none;
  3. only a tab no errand drives — or an errand whose deliverable is not a sheet — falls back to the monitor card;
  4. a refresh never restores an errand's tab as a card of its own;
  5. a resumed errand reopens the sheet of its durable row, with what was already delivered still in it.

Every errand below is a different one on purpose (a hotel, a flight, a shopping list): nothing here may know which.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import dispatch, surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.navegador import tasks as navtasks
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    monkeypatch.setattr(navtasks, "_tasks", {})
    store._last_hash.clear()
    yield
    store._last_hash.clear()


def _capture(monkeypatch):
    import voice.observer as observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: seen.append((kind, label, kw.get("extra") or {})))
    return seen


def _shows(seen) -> list:
    return [e.get("id", "") for k, lbl, e in seen if k == "widget" and lbl == "show"]


def _errand(tid: str, goal: str, surface: str = "voz") -> SessionRecord:
    """An errand whose surface did NOT open a sheet at commission (the measured case: the booking was «told»)."""
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, surface)
    rec.status = "running"
    dispatch._SESSIONS[tid] = rec
    return rec


def _run_prepare_web(rec, monkeypatch) -> str:
    import nucleo.agentes.web as _web

    async def _no_synth(req):
        return ""
    monkeypatch.setattr(_web, "_synthesize_goal", _no_synth)
    return asyncio.run(dispatch._prepare_web(rec, rec.goal))


# ── 1 + 2 · the start opens nothing; a wall raises the errand's sheet, never the monitor ────────────────────

def test_a_wall_on_an_errand_without_a_sheet_opens_its_sheet_not_the_monitor(monkeypatch):
    rec = _errand("41", "book a double room in Porto for Friday")
    seen = _capture(monkeypatch)
    tid = _run_prepare_web(rec, monkeypatch)
    assert _shows(seen) == [], "starting an errand opened a card"
    navtasks.set_status(tid, "working")
    navtasks.update_view(tid, url="https://www.example-hotels.com/sorry/index?continue=x")
    shows = _shows(seen)
    assert rec.sheet, "the wall did not open the errand's sheet"
    assert shows == [sheet.instance_id(rec.sheet)], shows
    assert navtasks.get(tid)["sheet"] == rec.sheet, "the tab must now refresh the sheet's process tab"


def test_a_login_wait_on_an_errand_raises_its_sheet(monkeypatch):
    rec = _errand("42", "find a flight Madrid–Lisbon under 90 euros")
    tid = _run_prepare_web(rec, monkeypatch)
    seen = _capture(monkeypatch)
    navtasks.set_login_wait(tid, True)
    assert _shows(seen) == [sheet.instance_id(rec.sheet)], _shows(seen)
    seen.clear()
    navtasks.set_login_wait(tid, False)
    assert _shows(seen) == [], "the login ending is not a reason to raise anything"


def test_then_the_first_rows_land_in_the_same_card(monkeypatch):
    """The point of opening the sheet at the wall: the rows that come later have no second card to open."""
    rec = _errand("43", "put together a shopping list for a paella for six")
    tid = _run_prepare_web(rec, monkeypatch)
    navtasks.set_login_wait(tid, True)
    first = rec.sheet
    assert dispatch.sheet_for_nav_task(tid) == first


# ── 3 · the monitor card stays for what has no sheet ─────────────────────────────────────────────────────────

def test_a_tab_no_errand_drives_keeps_its_monitor_card(monkeypatch):
    tid = navtasks.create("browsing by hand")
    navtasks.set_status(tid, "working")
    seen = _capture(monkeypatch)
    navtasks.update_view(tid, url="https://www.example.com/sorry/index?continue=x")
    assert _shows(seen) == [navtasks.inst_id(tid)], _shows(seen)


def test_a_report_errand_has_no_results_sheet_so_its_page_shows_in_the_monitor(monkeypatch):
    rec = _errand("44", "write a report on Roman aqueducts", surface="informe")
    tid = _run_prepare_web(rec, monkeypatch)
    seen = _capture(monkeypatch)
    navtasks.set_login_wait(tid, True)
    assert _shows(seen) == [navtasks.inst_id(tid)], _shows(seen)
    assert not rec.sheet


# ── 4 · a refresh restores the errand's card, not its tab beside it ──────────────────────────────────────────

def test_a_refresh_does_not_bring_an_errands_monitor_back():
    from server import canvas_api
    rec = _errand("45", "book a double room in Porto for Friday")
    errand_tab = navtasks.create(rec.goal)
    rec.nav_task = errand_tab
    manual_tab = navtasks.create("browsing by hand")
    restored = canvas_api._live_canvas_instances()
    assert navtasks.inst_id(errand_tab) not in restored, restored
    assert navtasks.inst_id(manual_tab) in restored, restored


# ── 5 · a resumed errand reopens its row's sheet, with what it had delivered ─────────────────────────────────

def _deliver(sheet_id: str, title: str) -> None:
    sheet.apply_action("present", {"sheet": sheet_id, "title": "x", "items": [{"title": title}]})


def test_a_resumed_errand_reopens_its_rows_sheet_and_keeps_its_rows():
    old = "aaaaaa-1"                       # named by the PREVIOUS boot: row id == sheet id by construction
    _deliver(old, "Hotel Ribeira")
    rec = SessionRecord(task_id="1", goal="book a double room in Porto for Friday", kind="web", uid=old)
    surfaces.set_once(rec, "lista")
    dispatch._sheet_open(rec, show=False)
    assert rec.sheet == old, f"the resumed errand opened {rec.sheet!r} beside its own sheet"
    assert [i["title"] for i in sheet.view_data(old)["items"]] == ["Hotel Ribeira"], "resuming wiped the sheet"


def test_the_rows_recorded_sheet_wins_over_its_id(monkeypatch):
    from nucleo.circuit import ledger as _tasks
    monkeypatch.setattr(_tasks, "get", lambda uid: {"id": uid, "sheet": "bbbbbb-ls3"} if uid == "bbbbbb-2" else None)
    rec = SessionRecord(task_id="2", goal="find a flight Madrid–Lisbon", kind="web", uid="bbbbbb-2")
    surfaces.set_once(rec, "lista")
    dispatch._sheet_open(rec, show=False)
    assert rec.sheet == "bbbbbb-ls3"


def test_a_fresh_errand_still_opens_its_own_fresh_sheet():
    """The counterweight: an errand whose row is its own (uid composed from this boot) is NOT a continuation."""
    from nucleo.circuit import ledger as _tasks
    mine = dispatch.sheet_id_for("3")
    _deliver(mine, "leftover")
    rec = SessionRecord(task_id="3", goal="put together a shopping list", kind="web", uid=_tasks.task_uid("3"))
    surfaces.set_once(rec, "lista")
    dispatch._sheet_open(rec, show=False)
    assert rec.sheet == mine and sheet.view_data(mine)["items"] == []


def test_the_listener_hands_the_durable_row_to_the_record():
    """Wiring: the record is born with the `task_uid` the rehydration carries, BEFORE the sheet is opened."""
    import inspect
    from nucleo import dispatch_listener
    src = inspect.getsource(dispatch_listener.run_listener)
    born = src.index("rec = _d.SessionRecord(")
    assert 'uid=str(ctx.get("task_uid"' in src[born:born + 1500]
    assert src.index("_d._sheet_open(rec)") > born
