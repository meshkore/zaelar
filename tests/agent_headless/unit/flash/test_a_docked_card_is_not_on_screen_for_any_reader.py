"""V2-776 L2 · A docked card is not on screen, for EVERY reader (node 2.184).

Pass 59, S1: the monitors sheet was minimised at A2; `open_widgets` (the canvas report) includes docked cards,
so the harness called it open, `live_blocks` told the model the results were «ya en pantalla», and «show me»
got «Done.» over the dock. `canvas_visibility.is_minimized` already knew; nobody else asked it. Now every
«is it on screen» reads `truth.canvas_state`: visible = open minus minimized.

And the collections a widget declares FROM ITS VIEW (`"from": "view"`) are what `rows` reads for them — the
seam L2 uses for `mensajeria.sent`, `documento.sections`, `youtube.search_results` and `agenda.occurrences`.
"""
import asyncio

import pytest


@pytest.fixture
def docked(monkeypatch):
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda: {"open_widgets": ["results", "agenda"], "minimized_widgets": ["results"]})


def test_the_harness_does_not_count_a_docked_card_as_open(docked):
    from nucleo import harness
    assert harness._card_is_open("results") is False
    assert harness._card_is_open("agenda") is True


def test_the_live_state_does_not_call_a_docked_card_open(docked):
    from nucleo.flash import live_blocks
    assert live_blocks._is_open("results") is False
    assert live_blocks._is_open("agenda") is True


def test_a_met_content_goal_needs_the_card_visible(docked, monkeypatch):
    from nucleo import harness, truth
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"empty": False})
    g = {"kind": harness.KIND_WIDGET_CONTENT, "target": "results", "text": "x", "checks": 0}
    assert asyncio.run(harness.verify(g)) is False, "content in the dock is not content in front of him"
    g2 = {"kind": harness.KIND_WIDGET_CONTENT, "target": "agenda", "text": "x", "checks": 0}
    assert asyncio.run(harness.verify(g2)) is True


def test_a_collection_declared_from_the_view_is_read_from_the_view(monkeypatch):
    from widgets import rows
    monkeypatch.setattr(rows, "declared", lambda wid: {"things": {"id": "id", "from": "view", "ops": ["list"]}} if wid == "demo" else {})
    from nucleo import truth
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"things": [{"id": "1", "title": "One"}, {"id": "2", "title": "Two"}]})
    assert [r["id"] for r in rows.select("demo", "things", {"title~": "two"})] == ["2"]
    assert rows.ops_for("demo", "things") == ("list",)
