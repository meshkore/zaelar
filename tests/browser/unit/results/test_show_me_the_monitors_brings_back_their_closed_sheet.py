"""«Show me the monitors» with no sheet open brings back the CLOSED sheet it names — never the empty base.

Measured 2026-09-27 (demo pass v7, S1): the monitor errand's sheet had been closed two blocks earlier; the model
called `show_widget(results)`, `resolve_show` found no open instance and returned the bare `results` — empty — and
«Compare them visually» / «Open the best value option» then worked on nothing.
"""
from widgets import instances


def _recent(monkeypatch, rows):
    monkeypatch.setattr(instances, "recent_faces", lambda limit=5: rows)


def test_the_sheet_named_by_the_phrase_comes_back(monkeypatch):
    _recent(monkeypatch, [{"id": "results::94b220-7", "label": "Five free days in Anna's vacation"},
                          {"id": "results::94b220-ls1", "label": "27-inch 4K monitors under 400 dollars"}])
    out = instances.resolve_show("results", [], "Show me the monitors.")
    assert out["id"] == "results::94b220-ls1", out


def test_a_bare_request_brings_the_most_recent_sheet(monkeypatch):
    _recent(monkeypatch, [{"id": "results::b", "label": "Weekend plan"}, {"id": "results::a", "label": "Monitors"}])
    assert instances.resolve_show("results", [], "Show me the results.")["id"] == "results::b"


def test_with_no_sheet_at_all_the_base_as_always(monkeypatch):
    _recent(monkeypatch, [])
    assert instances.resolve_show("results", [], "Show me the monitors.")["id"] == "results"


def test_an_open_sheet_still_wins(monkeypatch):
    _recent(monkeypatch, [{"id": "results::old", "label": "Monitors"}])
    assert instances.resolve_show("results", ["results::live"], "Show me the monitors.")["id"] == "results::live"
