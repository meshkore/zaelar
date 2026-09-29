"""V2-776 L2 · Every card the demo shows declares whether it is EMPTY (node 4.235).

The turn harness (V2-660) verifies «a shown card has content» from `view_data()["empty"]`, and only documento
and youtube declared it: results, imagenes, map, markets, musica and navegador were «NO verificable» on every
turn that showed them (pass 60: 2 of 3 goals unverifiable, expired unverified). And four of them always carry
an `error` KEY whose value is "" — the harness read the key and called them unreadable for a month.
"""
import pytest


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.musica import data as _musica
    monkeypatch.setattr(_musica, "_spotify_status", lambda: {})
    yield tmp_path


@pytest.mark.parametrize("wid", ["results", "imagenes", "map", "markets", "musica", "navegador", "documento", "youtube"])
def test_a_fresh_card_says_it_is_empty(fresh, wid):
    import importlib
    view = importlib.import_module(f"widgets.{wid}.data").view_data()
    assert view.get("empty") is True, f"{wid} does not declare emptiness"
    assert not str(view.get("error") or ""), f"{wid} reports an error on a fresh store"


def test_a_card_with_content_says_so(fresh):
    from widgets import store
    from widgets.map import data as _map
    from widgets.markets import data as _markets
    from widgets.imagenes import data as _img
    store.save(_map.WID, {**_map._seed(), "places": [{"name": "Griffith Observatory"}]})
    store.save(_markets.WID, {**_markets._seed(), "symbol": "AAPL", "points": [[1, 2]]})
    store.save(_img.WIDGET_ID, {**_img._seed(), "items": [{"url": "https://x/1.jpg", "title": "F40"}]})
    assert _map.view_data()["empty"] is False
    assert _markets.view_data()["empty"] is False
    assert _img.view_data()["empty"] is False


def test_the_harness_reads_the_error_value_not_the_key(monkeypatch):
    """`harness.verify` returned None for any view carrying an `error` key, even `""`."""
    import asyncio

    from nucleo import harness, truth
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"empty": False, "error": ""})
    monkeypatch.setattr(truth, "canvas_state", lambda wid: "visible")
    g = {"kind": harness.KIND_WIDGET_CONTENT, "target": "markets", "text": "x", "checks": 0}
    assert asyncio.run(harness.verify(g)) is True
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"empty": False, "error": "store unreadable"})
    assert asyncio.run(harness.verify(g)) is None
