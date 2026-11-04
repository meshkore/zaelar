"""V2-849 step 3 · a name is looked for closest first: his circle, then the people he talks to, then the background.

A real directory: 2,706 contacts imported from an address book, fifteen of them match «pablo» and most are years old
(«Psm Pablo Buso», «Pablo Elastic», «Carmen Mamá de Pablo»). The resolver answered in store order, so a «which
Pablo?» named four arbitrary rows — and the person he writes to every week was not among them.

The rules (`widgets/directory.py`):
  · a level per contact, computed: CIRCLE (his word: favorite, alias, relation), ACTIVE (traffic either way within
    `contacts.active_days`), BACKGROUND (the rest; also a contact marked closed); hidden and blocked are never
    candidates;
  · the match ladder is unchanged (alias → exact → all words → address/number → spelling), and each rung answers
    closest first;
  · ONE person of his circle is the answer; anything else is a question naming at most `CANDIDATES_MAX`, closest
    first, each with what tells them apart — a single active «Pablo» beside fourteen background ones is still a
    question (medium certainty is asked, never assumed).
"""
from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def world(tmp_path, monkeypatch):
    """ISOLATED store and workspace — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets.contactos import data as d
    from widgets import directory
    return d, directory


def _put(d, *rows):
    db = d.load_db()
    for i, r in enumerate(rows):
        db["contacts"].append({"id": f"c{i}-{r['name']}", "kind": "person", "channels": [], **r})
    d.store.save(d.WIDGET_ID, db)


def _talked(days_ago: float, platform: str = "whatsapp") -> list[dict]:
    return [{"platform": platform, "chatId": f"x{days_ago}", "handle": "", "volume": 3,
             "last_seen": time.time() - days_ago * 86400}]


def _names(rows) -> list[str]:
    return [r["name"] for r in rows]


# ── the levels ───────────────────────────────────────────────────────────────────────────────────────────────

def test_each_contact_has_a_level_computed_from_what_he_did(world):
    _d, dr = world
    assert dr.level({"name": "A", "favorite": True}) == dr.CIRCLE
    assert dr.level({"name": "A", "aliases": ["mi tontita"]}) == dr.CIRCLE
    assert dr.level({"name": "A", "relation": "mother"}) == dr.CIRCLE
    assert dr.level({"name": "A", "channels": _talked(3)}) == dr.ACTIVE
    assert dr.level({"name": "A", "channels": _talked(400)}) == dr.BACKGROUND
    assert dr.level({"name": "A"}) == dr.BACKGROUND
    assert dr.level({"name": "A", "favorite": True, "flags": ["closed"]}) == dr.BACKGROUND
    assert dr.level({"name": "A", "channels": _talked(1), "flags": ["blocked"]}) == 0
    assert dr.level({"name": "A", "favorite": True, "hidden": True}) == 0


def test_the_window_is_his_setting(world, tmp_path):
    _d, dr = world
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "contacts.json").write_text(json.dumps({"active_days": 7}))
    assert dr.level({"name": "A", "channels": _talked(30)}) == dr.BACKGROUND


# ── closest first ────────────────────────────────────────────────────────────────────────────────────────────

def test_a_first_name_is_asked_with_the_one_he_talks_to_first(world):
    d, dr = world
    _put(d, {"name": "Psm Pablo Buso"}, {"name": "Pablo Elastic"}, {"name": "Pablo Hernandez"},
         {"name": "Pablo Sabin", "channels": _talked(2)})
    hits = dr.resolve("Pablo")
    assert _names(hits)[0] == "Pablo Sabin" and len(hits) == 4, "one active Pablo beside three others: still a question"
    from widgets.mensajeria.outbound import targets
    t = targets.resolve_target({"contact": "Pablo", "text": "¿has probado Zaelar?"})
    assert t["ok"] is False and t["candidates"][0] == "Pablo Sabin" and len(t["candidates"]) == dr.CANDIDATES_MAX
    assert "y 1 más" in t["error"] and "WhatsApp, hace 2 días" in t["error"]


def test_one_person_of_his_circle_is_the_answer(world):
    d, dr = world
    _put(d, {"name": "Raquel Jofre"}, {"name": "Raquel Ares", "channels": _talked(5)},
         {"name": "Raquel Salvador Esteban", "aliases": ["Raquel", "mi tontita"]})
    assert _names(dr.resolve("Raquel")) == ["Raquel Salvador Esteban"]
    assert _names(dr.resolve("mi tontita")) == ["Raquel Salvador Esteban"]


def test_a_full_name_reaches_the_background(world):
    d, dr = world
    _put(d, {"name": "Pablo Sabin", "channels": _talked(2)}, {"name": "Pablo Hernandez"})
    assert _names(dr.resolve("Pablo Hernandez")) == ["Pablo Hernandez"]


def test_hidden_and_blocked_people_are_never_candidates(world):
    d, dr = world
    _put(d, {"name": "Ana Ruiz", "hidden": True}, {"name": "Ana Gil", "flags": ["blocked"], "channels": _talked(1)},
         {"name": "Ana Mora"})
    assert _names(dr.resolve("Ana")) == ["Ana Mora"]


def test_the_same_in_english_on_another_channel(world):
    d, dr = world
    _put(d, {"name": "Rowan Ferrer"}, {"name": "Rowan Lee", "channels": _talked(1, "telegram")})
    from widgets.mensajeria.outbound import targets
    t = targets.resolve_target({"contact": "Rowan", "text": "running late"})
    assert t["candidates"] == ["Rowan Lee", "Rowan Ferrer"] and "Telegram, ayer" in t["error"]


def test_a_favorite_among_namesakes_is_the_answer_without_an_alias(world):
    """The circle rule itself, not the alias rung: his ★ on one Raquel makes her the Raquel."""
    d, dr = world
    _put(d, {"name": "Raquel Jofre", "channels": _talked(3)}, {"name": "Raquel Ares"},
         {"name": "Raquel Salvador Esteban", "favorite": True})
    assert _names(dr.resolve("Raquel")) == ["Raquel Salvador Esteban"]
