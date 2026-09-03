"""connectors/catalog.py (V2-561, implementing V2-526) — the connector CATALOG: what is merely LISTED

versus what is LIVE. `connectors/registry.py` stays the live inventory (built connectors, real state);
this module is its opposite half — connectors we do NOT have (`state="planned"`) or CANNOT have
(`state="not-possible"`, with why the door is shut).

The rule this module exists to hold: anything merely listed costs 0 prompt bytes, 0 tool entries, 0
imports at startup — only what the operator has CONNECTED, or a lookup that just ran, costs anything.
Nothing in this pass wires the catalog into any FlashBrain prompt or tool at all (it is a ChatWall/
ConfigPanel-only surface), so that property holds trivially here — these tests instead pin the two
pieces that DO exist: a bad manifest cannot blank the whole wishlist (registry.py's own isolation
pattern), and a lookup never touches a model or the network.
"""
from __future__ import annotations

import json

import pytest

from connectors import catalog


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    """A private catalog dir, never the operator's real `connectors/catalog/`."""
    monkeypatch.setattr(catalog, "_DIR", tmp_path)
    return tmp_path


def _write(dirpath, name, data):
    (dirpath / name).write_text(json.dumps(data), encoding="utf-8")


def test_an_empty_or_missing_directory_yields_no_manifests(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "_DIR", tmp_path / "does-not-exist")
    assert catalog.load_manifests() == []


def test_a_broken_manifest_does_not_blank_the_whole_shelf(shelf):
    """Same isolation as registry.py's per-family reads: one bad file must not take down the rest."""
    _write(shelf, "good.json", {"id": "good", "label": "Good", "family": "infra", "state": "planned",
                                 "capabilities": ["good"]})
    (shelf / "broken.json").write_text("{not json", encoding="utf-8")
    _write(shelf, "not-a-dict.json", ["nope"])
    _write(shelf, "no-id.json", {"label": "Missing id"})
    ids = {m["id"] for m in catalog.load_manifests()}
    assert ids == {"good"}


def test_wishlist_returns_only_planned_and_not_possible(shelf):
    _write(shelf, "built.json", {"id": "built-one", "label": "Built", "family": "infra", "state": "built",
                                  "capabilities": ["built"]})
    _write(shelf, "planned.json", {"id": "planned-one", "label": "Planned", "family": "infra",
                                    "state": "planned", "capabilities": ["planned"]})
    _write(shelf, "impossible.json", {"id": "impossible-one", "label": "Impossible", "family": "infra",
                                       "state": "not-possible", "capabilities": ["impossible"],
                                       "why-not": "a real, stated reason"})
    ids = {m["id"] for m in catalog.wishlist()}
    assert ids == {"planned-one", "impossible-one"}
    all_ids = {m["id"] for m in catalog.load_manifests()}
    assert all_ids == {"built-one", "planned-one", "impossible-one"}, \
        "load_manifests() must still return the BUILT entry too — search() needs it for the lexical index"


def test_a_not_possible_entry_carries_its_why_not(shelf):
    _write(shelf, "impossible.json", {"id": "x", "label": "X", "family": "infra", "state": "not-possible",
                                       "capabilities": ["x"], "why-not": "CloudKit does not expose this."})
    entry = catalog.wishlist()[0]
    assert entry["why-not"] == "CloudKit does not expose this."


def test_search_with_no_query_words_returns_nothing(shelf):
    _write(shelf, "a.json", {"id": "a", "label": "A", "family": "infra", "state": "planned",
                              "capabilities": ["alpha"]})
    assert catalog.search("") == []
    assert catalog.search("   ") == []


def test_search_matches_on_label_family_or_capabilities(shelf):
    _write(shelf, "slack.json", {"id": "slack", "label": "Slack", "family": "mensajeria", "state": "planned",
                                  "capabilities": ["canales de equipo", "workspace"]})
    _write(shelf, "cal.json", {"id": "cal", "label": "Calendar", "family": "agenda", "state": "planned",
                                "capabilities": ["citas", "eventos"]})
    assert [m["id"] for m in catalog.search("slack")] == ["slack"]
    assert [m["id"] for m in catalog.search("canales")] == ["slack"]
    assert [m["id"] for m in catalog.search("citas")] == ["cal"]
    assert catalog.search("nothing matches this at all") == []


def test_search_is_capped_at_the_limit(shelf, monkeypatch):
    monkeypatch.setattr("connectors.registry.descriptors", lambda: [])
    for i in range(12):
        _write(shelf, f"m{i}.json", {"id": f"m{i}", "label": f"Match {i}", "family": "infra",
                                      "state": "planned", "capabilities": ["match"]})
    hits = catalog.search("match", limit=5)
    assert len(hits) == 5


def test_search_ranks_connected_above_built_above_planned_above_not_possible(shelf, monkeypatch):
    _write(shelf, "conn.json", {"id": "conn-one", "label": "Match Connected", "family": "infra",
                                 "state": "built", "capabilities": ["match"]})
    _write(shelf, "built.json", {"id": "built-one", "label": "Match Built", "family": "infra",
                                  "state": "built", "capabilities": ["match"]})
    _write(shelf, "planned.json", {"id": "planned-one", "label": "Match Planned", "family": "infra",
                                    "state": "planned", "capabilities": ["match"]})
    _write(shelf, "impossible.json", {"id": "impossible-one", "label": "Match Impossible", "family": "infra",
                                       "state": "not-possible", "capabilities": ["match"]})
    monkeypatch.setattr("connectors.registry.descriptors",
                         lambda: [{"id": "conn-one", "connected": True}])
    ids = [m["id"] for m in catalog.search("match", limit=10)]
    assert ids == ["conn-one", "built-one", "planned-one", "impossible-one"], ids


def test_search_fails_open_when_the_live_registry_is_unreachable(shelf, monkeypatch):
    """A broken registry import must degrade the RANKING, never the search itself."""
    _write(shelf, "a.json", {"id": "a", "label": "A", "family": "infra", "state": "planned",
                              "capabilities": ["alpha"]})

    def _boom():
        raise RuntimeError("registry unavailable")
    monkeypatch.setattr("connectors.registry.descriptors", _boom)
    assert [m["id"] for m in catalog.search("alpha")] == ["a"]


def test_the_real_catalog_directory_has_no_bad_manifests():
    """Guards the operator's actual `connectors/catalog/*.json` — every shipped manifest must be a real
    JSON object with an `id`, and every `state` must be one the rest of this module understands."""
    real = catalog.load_manifests()
    assert real, "expected at least the built connectors to have manifests"
    for m in real:
        assert m.get("id") and m.get("label") and m.get("family")
        assert m.get("state") in ("built", "planned", "not-possible"), m
        if m["state"] == "not-possible":
            assert m.get("why-not"), f"{m['id']}: a not-possible entry must say WHY"


def test_the_real_wishlist_offers_no_button_for_a_not_possible_entry_by_construction():
    """Not a UI test (that lives in the render suite) — pins the DATA contract the frontend relies on:
    only `why-not` distinguishes not-possible from planned, never a separate 'has_button' flag to drift
    from it."""
    wish = catalog.wishlist()
    for m in wish:
        if m["state"] == "not-possible":
            assert "why-not" in m
        else:
            assert m["state"] == "planned"
