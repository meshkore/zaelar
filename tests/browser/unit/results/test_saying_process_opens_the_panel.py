"""«Proceso» said while the results sheet is open OPENS the processes panel (V2-822, the operator's decision 5).

The sheet lost its «Proceso» tab: what an errand is doing lives in the running process's entry in the processes
panel. The request still reaches the sheet as its declared action (`tab` → `process`, «proceso» through the tab
vocabulary the sheet declares), and that action used to REFUSE with «it is in the processes panel — show_panel
procesos», leaving the model a second call it may not make. Now the action itself takes him there: the same `panel`
event `show_panel` emits, on «Procesos», and the sheet stays on the tab he was looking at.

Disarm: `_a_tab` back to refusing `process` → red.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from widgets import store
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


@pytest.fixture
def panels(monkeypatch):
    from voice import observer
    out: list = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: out.append((label, (k.get("extra") or {}).get("tab")))
                        if kind == "panel" else None)
    return out


@pytest.mark.parametrize("said", ["process", "proceso"])
def test_saying_process_to_the_sheet_opens_the_processes_panel(said, panels):
    sheet.apply_action("present", {"title": "Hoteles", "items": [{"title": "Bécquer"}]})
    sheet.apply_action("tab", {"tab": "sources"})
    out = sheet.apply_action("tab", {"tab": said})
    assert out["ok"] is True, f"«{said}» is not refused any more: it opens the panel — {out}"
    assert panels == [("open", "procesos")], f"the panel opens on Procesos, once: {panels}"
    assert sheet.view_data().get("tab") == "sources", "the sheet stays on the tab he was looking at"


def test_any_other_tab_opens_no_panel(panels):
    sheet.apply_action("present", {"title": "Hoteles", "items": [{"title": "Bécquer"}]})
    assert sheet.apply_action("tab", {"tab": "criterios"})["ok"] is True
    assert sheet.apply_action("tab", {"tab": "inventada"})["ok"] is False
    assert panels == [], panels
