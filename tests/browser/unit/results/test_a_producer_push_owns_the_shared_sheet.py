"""The two producers that can land on the SHARED results sheet name their errand, so their push owns it instead of
appending under another errand's rows (V2-831 T-01, node 4.323).

`dispatch._finalize_web` (an errand's final scrape) and `owner._automate` (the browser's own task loop) are run for
real; only their edges are doubles — the tab that extracts, the task registry, the agent loop and the announcement.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from nucleo.dispatch import prepare
from widgets.navegador import act_api, agent, owner, owner_actions, tasks as navtasks
from widgets.results import data as sheet

STALE = [{"title": "Comedores Escolares - Educacyl", "url": "https://www.educa.jcyl.es/"}]
FOUND = [{"title": "SkyShowtime", "price": "6,99€", "url": "https://www.skyshowtime.com/es"}]


def _titles():
    return [it["title"] for it in sheet.view_data("")["items"]]


class _Tab:
    def __init__(self, *_a):
        pass

    async def extract_listings(self, *_a):
        return list(FOUND)


def _quiet_registry(monkeypatch):
    for name in ("set_results", "finish", "set_phase", "set_status", "cancel", "milestone"):
        monkeypatch.setattr(navtasks, name, lambda *a, **k: None)
    monkeypatch.setattr(navtasks, "get", lambda *a, **k: {"url": "https://www.justwatch.com/es"})


def test_an_errands_final_scrape_owns_the_shared_sheet(monkeypatch):
    _quiet_registry(monkeypatch)
    monkeypatch.setitem(owner._task_browsers, "nav-1", _Tab())
    sheet.apply_action("present", {"items": STALE})
    rec = SimpleNamespace(nav_task="nav-1", task_id="errand-1", sheet="", status="done", ok=True,
                          result_summary="", goal="streaming offers")
    asyncio.run(prepare._finalize_web(rec))
    assert _titles() == ["SkyShowtime"], _titles()


def test_the_browsers_own_loop_owns_the_shared_sheet(monkeypatch):
    _quiet_registry(monkeypatch)
    monkeypatch.setattr(owner, "TaskBrowser", _Tab)

    async def _run(goal, tb, plan=""):
        return {"ok": True, "success": True, "summary": "ok", "results": {"items": list(FOUND)}}

    async def _silent(*_a, **_k):
        return None

    monkeypatch.setattr(agent, "run_task", _run)
    monkeypatch.setattr(owner_actions, "_announce", _silent)
    monkeypatch.setattr(act_api, "_sheet_of", lambda _tid: "")
    sheet.apply_action("present", {"items": STALE})
    asyncio.run(owner_actions._automate("streaming offers", task_id="nav-2"))
    owner._task_browsers.pop("nav-2", None)
    assert _titles() == ["SkyShowtime"], _titles()
