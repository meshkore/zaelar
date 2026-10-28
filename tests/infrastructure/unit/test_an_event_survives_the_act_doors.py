"""An event of the act doors survives their fold (V2-826 §2b, refactor2710-06).

The section folds the media, message, errand, memory and search files of `nucleo/flash` into `nucleo/acts/`. A fold
may carry an `emit(...)` to another file; it may never drop it. This freezes what the doors emit with literal
arguments. A pair added later passes; a pair retired on purpose leaves this set in the same commit, with the reason.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

FROZEN_PAIRS = {
    # T-05 · the search door (from flash/search_routing, search_turn, listing_turn and the voice lane)
    ("brain", "🔎 búsqueda web"), ("brain", "🧭 ruta de búsqueda (sombra)"), ("search", "🔎 resultados web"),
    ("brain", "🛒 la pasada rápida acabó después del turno"), ("search", "🛒 búsqueda de anuncios"),
    ("widget", "show"),
}


def _emitted() -> set:
    pairs = set()
    for p in (ENGINE / "nucleo/acts").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call):
                continue
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if "emit" in name and len(n.args) > 1 and all(isinstance(a, ast.Constant) for a in n.args[:2]):
                pairs.add((n.args[0].value, n.args[1].value))
    return pairs


def test_no_frozen_event_of_the_act_doors_vanishes():
    assert not sorted(FROZEN_PAIRS - _emitted()), f"an event stopped being emitted: {sorted(FROZEN_PAIRS - _emitted())}"


def test_disarm_a_dropped_event_is_named():
    pairs = _emitted()
    assert sorted(FROZEN_PAIRS - (pairs - {("search", "🔎 resultados web")})) == [("search", "🔎 resultados web")]


def test_the_fact_door_leaves_its_rows_with_what_came_back(monkeypatch):
    """The search row carries the evidence — titles, URLs, the synthesized answer — and the route row its module."""
    from nucleo.acts import search as door
    from search import web
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": {
        "query": q, "answer": "18 °C", "results": [{"title": "NYC weather", "url": "https://w/1", "snippet": "sunny"}],
        "source": "zai"})
    seen = []
    door.fact({"text": "weather?", "brief": None}, {"query": "weather NYC"},
              emit=lambda kind, label, **kw: seen.append((kind, label, kw.get("extra") or {})), channel="voice")
    labels = [(k, label) for k, label, _ in seen]
    assert labels[0] == ("brain", "🔎 búsqueda web") and ("search", "🔎 resultados web") in labels
    row = next(ex for k, label, ex in seen if label == "🔎 resultados web")
    assert row["n"] == 1 and row["source"] == "zai" and "evidence" in row
    assert next(ex for k, label, ex in seen if label.startswith("🧭"))["module"] == "inline_fact"
