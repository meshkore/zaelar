"""Two errands with no sheet of their own never deliver into the same box.

Measured 2026-09-27 (demo pass v6): the monitor search was dispatched without a sheet (its surface did not open
one), delivered into the bare `results`, and the Ferrari search that came next — also sheet-less — `present`ed
into that same bare sheet, REPLACING the monitors. «Show me the monitors» then found no monitors anywhere.
Each errand now gets its own sheet on its first delivery.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from nucleo import worker_api


def _rec(tid, goal):
    return SimpleNamespace(task_id=tid, trace_id="", sheet="", goal=goal, title=goal, kind="web")


def _present(rec, title, price):
    return asyncio.run(worker_api._exec_allow("widget_data", {
        "widget_id": "results", "action": "present",
        "payload": {"items": [{"title": title, "price": price, "url": f"https://example.com/{price}"}]}}, rec))


def test_the_second_errand_does_not_replace_the_first(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: None, raising=False)
    monitors, ferraris = _rec("901", "three 4K monitors"), _rec("902", "red Ferrari F40")
    _present(monitors, "Samsung ViewFinity S7", 189.99)
    _present(ferraris, "Ferrari F40 1989", 2500000)
    assert monitors.sheet and ferraris.sheet and monitors.sheet != ferraris.sheet, (monitors.sheet, ferraris.sheet)
    from widgets.results import data as sheet
    titles = [i.get("title") for i in (sheet.view_data(monitors.sheet).get("items") or [])]
    assert "Samsung ViewFinity S7" in titles, f"the monitors must still be on their own sheet: {titles}"
