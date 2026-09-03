"""V2-571 — ONE widget per errand: the browser is EMBEDDED in the sheet's process tab.

The operator, with both cards on screen: «no tiene sentido abrir un browser que solo muestra capturas y un
widget de Resultados en paralelo — ambas cosas son parte de la misma tarea y el mismo flujo». So:

  1. `sheet_browser()` derives the errand's live browser monitor (capture, page, wall, login, question) for
     the sheet to render — never stored, `{}` once nothing is live.
  2. `_prepare_web` STOPS opening the separate `navegador::tN` card for an errand that has a sheet; a task
     with NO sheet keeps its monitor card, because there it is the only surface.
  3. The task registry refreshes the SHEET's card on every change (`_notify`), or the embedded capture would
     stand still between phase changes.
  4. A struck wall raises the SHEET, not the retired card.
  5. The login handoff button lives in the sheet: `auth_done` forwards to the browser owner's mailbox and
     never touches the browser's state itself.

Wiring is tested through the REAL paths (the V2-199 lesson): `_prepare_web` is actually run, `_notify` is
actually fired by a registry write, and the emits are captured at `voice.observer.emit` — a test that calls
the predicate by hand passes with the call site deleted.
"""
import asyncio

import pytest

from nucleo import dispatch, surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.navegador import tasks as navtasks
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Isolated widget store + session registry + task registry — all three are process state, and a leftover
    from another test paints «Trabajando…» (or a live browser) on a sheet that has nothing to do with it."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    monkeypatch.setattr(navtasks, "_tasks", {})
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


def _live(tid: str, goal: str = "busca hoteles en Sevilla") -> SessionRecord:
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, "lista")
    rec.sheet = dispatch.sheet_id_for(tid)
    rec.status = "running"
    dispatch._SESSIONS[tid] = rec
    return rec


def _capture_emits(monkeypatch):
    import voice.observer as observer
    seen = []
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, **kw: seen.append((kind, label, kw.get("extra") or {})))
    return seen


# ── 1 · sheet_browser derives the errand's live browser ─────────────────────────────────────────────────────

def test_the_sheet_sees_its_errands_browser():
    rec = _live("81")
    tid = navtasks.create(rec.goal, sheet=rec.sheet)
    rec.nav_task = tid
    navtasks.set_status(tid, "working")
    navtasks.update_view(tid, url="https://www.booking.com/hoteles", page_title="Booking.com", shot_rev=4)
    br = dispatch.sheet_browser(rec.sheet)
    assert br["task_id"] == tid
    assert br["url"] == "https://www.booking.com/hoteles"
    assert br["shot"] == f"shot-{tid}.png" and br["shot_rev"] == 4
    assert br["awaiting_login"] is False and br["question"] == ""


def test_with_no_live_errand_the_browser_is_empty_not_frozen():
    """A finished errand's capture must disappear: a frozen screenshot pretending to be a live browser lies."""
    assert dispatch.sheet_browser("whatever") == {}


def test_an_errand_without_a_tab_has_no_browser():
    _live("82")
    assert dispatch.sheet_browser(dispatch.sheet_id_for("82")) == {}


def test_the_nav_cli_fallback_tab_is_found_by_the_errands_own_id():
    """Not every errand driving the browser has a reserved tab: the `nav_cli` fallback names the tab after the
    TASK (V2-290). The embedded view has to find those too, or a research worker's browsing is invisible."""
    rec = _live("83")
    navtasks.ensure(rec.task_id, rec.goal)
    navtasks.update_view(rec.task_id, url="https://coches.net", shot_rev=1)
    br = dispatch.sheet_browser(rec.sheet)
    assert br.get("task_id") == rec.task_id


def test_view_data_carries_the_browser_to_the_widget():
    rec = _live("84")
    tid = navtasks.create(rec.goal, sheet=rec.sheet)
    rec.nav_task = tid
    navtasks.update_view(tid, url="https://example.com", shot_rev=2)
    data = sheet.view_data(rec.sheet)
    assert data["browser"].get("task_id") == tid


def test_the_browser_is_never_persisted():
    """Derived per read, like `progress`: a stored capture would outlive its browser and freeze on screen."""
    rec = _live("85")
    tid = navtasks.create(rec.goal, sheet=rec.sheet)
    rec.nav_task = tid
    data = sheet.view_data(rec.sheet)
    sheet._save(data, rec.sheet)
    raw = store.load(sheet.sheet_key(rec.sheet), {})
    assert "browser" not in raw and "progress" not in raw


# ── 2 · the separate card no longer opens for an errand with a sheet ────────────────────────────────────────

def _run_prepare_web(rec, monkeypatch):
    import nucleo.agentes.web as _web

    async def _no_synth(req):
        return ""
    monkeypatch.setattr(_web, "_synthesize_goal", _no_synth)
    return asyncio.run(dispatch._prepare_web(rec, rec.goal))


def test_an_errand_with_a_sheet_does_not_open_the_browser_card(monkeypatch):
    rec = _live("86")
    seen = _capture_emits(monkeypatch)
    tid = _run_prepare_web(rec, monkeypatch)
    assert tid, "the tab itself must still be created — only its CARD is retired"
    shows = [e for k, lbl, e in seen if k == "widget" and lbl == "show"]
    assert not any(e.get("id", "").startswith("navegador::") for e in shows), shows
    assert navtasks.get(tid).get("sheet") == rec.sheet


def test_a_task_with_no_sheet_keeps_its_monitor_card(monkeypatch):
    """The counterweight: for a sheetless task the card is the ONLY surface, and retiring it there would
    leave the operator with a browser working somewhere invisible."""
    rec = SessionRecord(task_id="87", goal="abre booking", kind="web")
    rec.status = "running"
    dispatch._SESSIONS["87"] = rec
    seen = _capture_emits(monkeypatch)
    tid = _run_prepare_web(rec, monkeypatch)
    assert any(lbl == "show" and e.get("id") == navtasks.inst_id(tid)
               for _k, lbl, e in seen), seen


# ── 3 · the registry refreshes the sheet's card ─────────────────────────────────────────────────────────────

def test_a_task_change_refreshes_the_sheet_card_too(monkeypatch):
    rec = _live("88")
    tid = navtasks.create(rec.goal, sheet=rec.sheet)
    seen = _capture_emits(monkeypatch)
    navtasks.update_view(tid, url="https://example.com", shot_rev=1)
    datas = [e.get("id") for k, lbl, e in seen if k == "widget" and lbl == "data"]
    assert sheet.instance_id(rec.sheet) in datas, datas
    assert navtasks.inst_id(tid) in datas, "the task's own card event stays — sheetless tasks still need it"


def test_a_sheetless_task_does_not_touch_the_default_sheet(monkeypatch):
    tid = navtasks.create("manual browsing")
    seen = _capture_emits(monkeypatch)
    navtasks.update_view(tid, url="https://example.com", shot_rev=1)
    datas = [e.get("id") for k, lbl, e in seen if k == "widget" and lbl == "data"]
    assert not any(d.startswith("results") for d in datas), datas


# ── 4 · a wall raises the sheet, not the retired card ───────────────────────────────────────────────────────

def test_a_wall_on_an_errands_tab_raises_the_sheet(monkeypatch):
    rec = _live("89")
    tid = navtasks.create(rec.goal, sheet=rec.sheet)
    navtasks.set_status(tid, "working")
    seen = _capture_emits(monkeypatch)
    navtasks.update_view(tid, url="https://www.booking.com/index.es.html?chal_t=12345")
    shows = [e.get("id") for k, lbl, e in seen if k == "widget" and lbl == "show"]
    assert sheet.instance_id(rec.sheet) in shows, shows
    assert navtasks.inst_id(tid) not in shows


# ── 5 · the login handoff forwards, and never silently ──────────────────────────────────────────────────────

def test_auth_done_forwards_to_the_browser_owner(monkeypatch):
    import widgets.supervisor as supervisor
    calls = []
    monkeypatch.setattr(supervisor, "enqueue", lambda wid, action, payload: (calls.append((wid, action, payload)), True)[1])
    out = sheet.apply_action("auth_done", {"task_id": "t7", "sheet": "abc"})
    assert out["ok"] is True
    assert calls == [("navegador", "auth_done", {"task_id": "t7"})]


def test_auth_done_resolves_the_task_from_the_sheets_live_browser(monkeypatch):
    """The button always sends the id; a voice-driven call may not. The sheet's own live browser is the
    only honest default — guessing another sheet's browser would confirm a stranger's login."""
    import widgets.supervisor as supervisor
    rec = _live("90")
    tid = navtasks.create(rec.goal, sheet=rec.sheet)
    rec.nav_task = tid
    calls = []
    monkeypatch.setattr(supervisor, "enqueue", lambda wid, action, payload: (calls.append(payload), True)[1])
    out = sheet.apply_action("auth_done", {"sheet": rec.sheet})
    assert out["ok"] is True and calls and calls[0]["task_id"] == tid


def test_auth_done_with_nothing_waiting_says_so():
    out = sheet.apply_action("auth_done", {"sheet": "nadie"})
    assert out["ok"] is False and "navegador" in out["error"]


def test_auth_done_with_a_dead_owner_is_a_refusal_not_a_silence(monkeypatch):
    import widgets.supervisor as supervisor
    monkeypatch.setattr(supervisor, "enqueue", lambda *a: False)
    out = sheet.apply_action("auth_done", {"task_id": "t7"})
    assert out["ok"] is False and "activo" in out["error"]


# ── set_sheet: a reused tab follows its new errand, and a stamp is never blanked ────────────────────────────

def test_a_reused_tab_is_restamped_with_the_new_errands_sheet():
    tid = navtasks.create("primer encargo", sheet="vieja")
    navtasks.set_sheet(tid, "nueva")
    assert navtasks.get(tid)["sheet"] == "nueva"


def test_set_sheet_never_blanks_an_existing_stamp():
    tid = navtasks.create("encargo", sheet="mia")
    navtasks.set_sheet(tid, "")
    assert navtasks.get(tid)["sheet"] == "mia"
