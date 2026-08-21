"""The screen is read from the engine, and the two sources are never merged.

`lab/screen.py` answers the judge's question — did the right thing open, with the right content — from
the events the engine already emits. Everything here is about the ways that reading can quietly say
something false, which is the only kind of failure it can have: it never raises.
"""
from __future__ import annotations

import json

import pytest

from tests.use_cases.lab import screen


def _ev(i: int, label: str, wid: str, src: str = "system") -> dict:
    """An observability row shaped like the real one: the columns the sink promotes on the outside, and
    everything else inside `payload` AS A JSON STRING. Building these by hand from the real payload is
    the point — a fixture that puts the widget id where the reader expects it proves nothing."""
    return {"id": i, "kind": "widget", "label": label, "cat": "widget", "corr_id": "T1·aaaa",
            "ts_ms": 1000.0 + i,
            "payload": json.dumps({"kind": "widget", "label": label, "id": wid, "src": src,
                                   "text": "", "role": ""})}


def _engine(events, *, canvas=(), layout=(), tasks=(), data=None):
    data = data or {}

    def fake_get(base, path, timeout=10.0):
        if path.startswith("/api/observability/events"):
            return {"events": list(events)}
        if path == "/api/memory/map":
            return {"state": {"open_widgets": list(canvas)}}
        if path == "/api/canvas/layout":
            return {"items": list(layout)}
        if path == "/api/tasks":
            return {"sessions": list(tasks)}
        if path.startswith("/widgets/"):
            return data.get(path)
        return None
    return fake_get


def test_a_widget_shown_and_then_closed_is_not_on_screen(monkeypatch):
    """The events are replayed IN ORDER. A set built by union would report a closed card as open, which
    is the difference between «the agent left it up» and «the agent tidied up after itself»."""
    monkeypatch.setattr(screen, "_get", _engine([
        _ev(1, "show", "results"),
        _ev(2, "show", "agenda"),
        _ev(3, "close", "results"),
    ]))
    snap = screen.read("http://x", with_data=False)
    assert snap["opened_by_agent"] == ["agenda"]


def test_the_trail_still_shows_what_was_closed(monkeypatch):
    """«Never opened» and «opened and closed again» are different failures, so the final set is not
    enough: the trail has to keep both events."""
    monkeypatch.setattr(screen, "_get", _engine([
        _ev(1, "show", "results"), _ev(2, "close", "results"),
    ]))
    snap = screen.read("http://x", with_data=False)
    assert snap["opened_by_agent"] == []
    assert [(e["label"], e["widget"]) for e in snap["widget_trail"]] == [
        ("show", "results"), ("close", "results")]


def test_close_all_empties_the_screen(monkeypatch):
    monkeypatch.setattr(screen, "_get", _engine([
        _ev(1, "show", "results"), _ev(2, "show", "agenda"), _ev(3, "closeAll", ""),
    ]))
    assert screen.read("http://x", with_data=False)["opened_by_agent"] == []


def test_the_widget_id_comes_from_the_payload_and_not_from_the_text(monkeypatch):
    """THE bug this reader shipped with. These rows carry an EMPTY `text`, so taking the id from there
    returned nothing and the screen read «(nada)» with four cards open. A field read at the wrong level
    does not fail — it invents a fact, and the fact it invented was that the agent had opened nothing."""
    row = _ev(1, "show", "results")
    assert json.loads(row["payload"])["text"] == "", "the fixture must keep text empty or it proves nothing"
    monkeypatch.setattr(screen, "_get", _engine([row]))
    assert screen.read("http://x", with_data=False)["opened_by_agent"] == ["results"]


def test_who_ordered_the_open_is_carried(monkeypatch):
    """«Did the right thing open» and «did the right ACTOR open it» are different questions. A card the
    engine put up and one a Brain Worker put up read the same without this."""
    monkeypatch.setattr(screen, "_get", _engine([
        _ev(1, "show", "results", src="worker:2"),
        _ev(2, "show", "agenda", src="system"),
    ]))
    trail = screen.read("http://x", with_data=False)["widget_trail"]
    assert [(e["widget"], e["src"]) for e in trail] == [("results", "worker:2"), ("agenda", "system")]


def test_an_empty_canvas_report_is_not_an_empty_screen(monkeypatch):
    """With no browser connected the frontend reports nothing, and that must never be read as «the agent
    opened nothing». The two lists stay apart and `watched` says which reading is available."""
    monkeypatch.setattr(screen, "_get", _engine([_ev(1, "show", "results")], canvas=()))
    snap = screen.read("http://x", with_data=False)
    assert snap["opened_by_agent"] == ["results"]
    assert snap["confirmed_by_canvas"] == []
    assert snap["watched"] is False
    assert "NO hay navegador" in screen.render(snap)


def test_a_watched_screen_reports_both(monkeypatch):
    monkeypatch.setattr(screen, "_get", _engine([_ev(1, "show", "results")], canvas=("results",)))
    snap = screen.read("http://x", with_data=False)
    assert snap["watched"] is True
    assert snap["confirmed_by_canvas"] == ["results"]


def test_an_instance_card_keeps_its_id_but_reads_the_base_widget_data(monkeypatch):
    """`navegador::t1` is one task's card. Its id has to survive whole (two cards for two tasks are two
    different things on screen) while its content comes from the widget, whose route has no instance."""
    monkeypatch.setattr(screen, "_get", _engine(
        [_ev(1, "show", "navegador::t1", src="worker:t1")],
        data={"/widgets/navegador/data": {"title": "Nuevo navegador", "items": []}}))
    snap = screen.read("http://x")
    assert snap["opened_by_agent"] == ["navegador::t1"]
    assert snap["data"]["navegador::t1"]["title"] == "Nuevo navegador"


def test_the_summary_says_what_is_inside_without_naming_a_widget(monkeypatch):
    """The one-liner is generic on purpose: title, item count, live progress. Special-casing a widget
    here would make the reader work for the cases it was written against and go quiet on the next one."""
    monkeypatch.setattr(screen, "_get", _engine(
        [_ev(1, "show", "results")],
        data={"/widgets/results/data": {"title": "Buscar un fontanero", "items": [1, 2, 3],
                                        "progress": {"alive": True, "phases": ["a", "b"]}}}))
    out = screen.render(screen.read("http://x"))
    assert "Buscar un fontanero" in out and "3 item(s)" in out
    assert "vivo" in out and "2 fase(s)" in out


def test_an_engine_that_does_not_answer_reads_as_empty_and_never_raises(monkeypatch):
    """A dead agent must give a readable «nothing», not a traceback in the middle of a round."""
    monkeypatch.setattr(screen, "_get", lambda base, path, timeout=10.0: None)
    snap = screen.read("http://x")
    assert snap["opened_by_agent"] == [] and snap["tasks"] == []
    assert isinstance(screen.render(snap), str)
