"""V2-854 F2 · the person he means is ONE ranking, not a ladder that stops at its first rung.

Measured on his engine (2026-11-05): «Raquel» against 2,686 contacts — nine carry the WORD «Raquel», and the person he
means is saved as «Rakel Karó» (WhatsApp, a favorite). The resolver tried a near spelling only when NO word matched,
so the nine background namesakes hid her; only an alias found her. The rules (`widgets/directory.resolve`):

  · every contact gets the strongest reason it matches — his word (alias) · the exact name or number · every word ·
    a word inside a compound name · the same SOUND (a generic, language-agnostic normaliser: K/C/Q, B/V, a silent H,
    LL/Y, accents) · a near spelling only as the last resort — and how close he keeps them (a recent conversation,
    then favorites > family > friends > colleagues > other; the unclassified last);
  · the ACT filters first: a WhatsApp send keeps who is reachable there, a mail who has an address, any send drops
    the unclassified;
  · a name in quotes is literal;
  · the best is used alone when it leads by the declared margin (`clear_margin`, a rule row with a default); else
    the closest first, and the send door asks among the first three;
  · his pick of a «which one?» becomes a learned alias of THAT contact.

Synthetic fixtures shaped like his directory (namesakes, a phonetic twin that is his favorite, compound and
handle-like names, an e-mail-only person, a company, an unclassified row) — no personal data.
"""
from __future__ import annotations

import time

import pytest


def _wa(n: int, days_ago: float) -> list[dict]:
    jid = f"{n}000000@lid"
    return [{"platform": "whatsapp", "handle": "", "chatId": jid, "volume": 4, "last_seen": time.time() - days_ago * 86400}]


#: Nine namesakes of one first name, imported with a phone, two of them talked to lately; his favorite saved under a
#: phonetic twin spelling with a WhatsApp chat; one person twice (a phone row and an e-mail-only handle-like row); a
#: company; a row with nothing to reach it by.
SPANISH = [
    *({"name": f"Raquel {last}", "phone": f"+34 600 100 {i:03d}"} for i, last in
      enumerate(["Jofre", "Ares", "Diaz", "Mora", "Puig", "Soler", "Vidal", "Roca"])),
    {"name": "Manu Raquel", "phone": "+34 600 100 900", "channels": _wa(9, 2)},
    {"name": "Rakel Karó", "favorite": True, "channels": _wa(1, 1)},
    {"name": "Raquel Salvador Esteban", "phone": "+34 600 200 001"},
    {"name": "raquel.salvadoresteban", "email": "raquel.se@example.org"},
    {"name": "Raquel Caro Interiorismo", "kind": "company", "phone": "+34 930 000 001"},
    {"name": "Raquel Nadie"},
]
ENGLISH = [
    *({"name": f"Catherine {last}", "phone": f"+1 555 010 {i:04d}"} for i, last in
      enumerate(["Hill", "Price", "Ward", "Stone", "Fox", "Lane", "Moss", "Reed", "Bell"])),
    {"name": "Katherine Lowe", "favorite": True, "channels": [{"platform": "telegram", "handle": "@kat",
                                                               "chatId": "55", "volume": 2, "last_seen": time.time()}]},
]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """ISOLATED store, workspace and rules — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets.contactos import data as d
    from widgets import directory
    directory._WINDOW.clear()
    directory._MARGIN.clear()
    yield d, directory
    directory._WINDOW.clear()
    directory._MARGIN.clear()


def _put(d, rows):
    db = d.load_db()
    for i, r in enumerate(rows):
        db["contacts"].append({"id": f"c{i}", "kind": "person", "channels": [], **r})
    d.store.save(d.WIDGET_ID, db)


def _names(rows) -> list[str]:
    return [r["name"] for r in rows]


# ── one ranking ──────────────────────────────────────────────────────────────────────────────────────────────

def test_his_favorite_spelled_another_way_is_the_one_among_nine_namesakes(world):
    d, dr = world
    _put(d, SPANISH)
    assert _names(dr.resolve("Raquel")) == ["Rakel Karó"], "a favorite that SOUNDS like it outranks nine word matches"
    assert _names(dr.resolve("Raquel", tolerant=False)) == ["Rakel Karó"], "the sound is a match, not a near spelling"
    assert _names(dr.resolve("raquel", platform="whatsapp")) == ["Rakel Karó"]


def test_a_recent_conversation_is_the_first_level(world):
    """The operator (decision 1): the people he has talked to lately come first, even above the relation scale — a
    recent namesake outranks a favorite he has not talked to; a favorite he also talks to stays on top."""
    d, dr = world
    rows = [dict(r) for r in SPANISH]
    fav = next(r for r in rows if r.get("favorite"))
    fav["channels"] = _wa(1, 200)
    _put(d, rows)
    assert _names(dr.resolve("Raquel")) == ["Manu Raquel"], "talked to two days ago, above the ★ of 200 days"
    db = d.load_db()
    next(c for c in db["contacts"] if c.get("favorite"))["channels"] = _wa(1, 0.5)
    d.store.save(d.WIDGET_ID, db)
    assert _names(dr.resolve("Raquel")) == ["Rakel Karó"], "a favorite he also talks to stays on top"


def test_a_recent_conversation_is_the_first_level_in_english(world):
    d, dr = world
    rows = [dict(r) for r in ENGLISH]
    rows[-1]["channels"] = [{"platform": "telegram", "chatId": "55", "volume": 2, "last_seen": time.time() - 300 * 86400}]
    rows[3]["channels"] = [{"platform": "telegram", "chatId": "9", "volume": 2, "last_seen": time.time() - 86400}]
    _put(d, rows)
    assert _names(dr.resolve("Catherine")) == ["Catherine Stone"]


def test_the_same_in_english(world):
    d, dr = world
    _put(d, ENGLISH)
    assert _names(dr.resolve("Catherine")) == ["Katherine Lowe"]
    assert _names(dr.resolve("Catherine Reed")) == ["Catherine Reed"], "a full name reaches the background"


def _no_favorite_two_recent():
    rows = [dict(r) for r in SPANISH if not r.get("favorite")]
    rows[1]["channels"] = _wa(2, 5)                       # «Raquel Ares» talked to lately too: no clear winner
    return rows


def test_without_a_clear_winner_the_closest_come_first(world):
    d, dr = world
    _put(d, _no_favorite_two_recent())
    hits = dr.resolve("Raquel")
    assert len(hits) > dr.CANDIDATES_MAX and hits[0]["name"] == "Manu Raquel", "the one he talks to leads the question"
    assert hits[-1]["name"] == "Raquel Nadie", "the unclassified last"


def test_a_word_of_a_compound_name_and_a_whole_name(world):
    d, dr = world
    _put(d, SPANISH)
    assert set(_names(dr.resolve("Raquel Salvador"))) == {"Raquel Salvador Esteban", "raquel.salvadoresteban"}
    assert _names(dr.resolve("Raquel Salvador Esteban")) == ["Raquel Salvador Esteban"], "the whole name wins"
    assert _names(dr.resolve("Interiorismo")) == ["Raquel Caro Interiorismo"], "a company is found by its words"
    assert _names(dr.resolve("600 200 001")) == ["Raquel Salvador Esteban"], "a number said"


# ── the act filters first ────────────────────────────────────────────────────────────────────────────────────

def test_the_act_keeps_who_it_can_reach(world):
    d, dr = world
    _put(d, SPANISH)
    assert _names(dr.resolve("Raquel Salvador", platform="email")) == ["raquel.salvadoresteban"]
    assert _names(dr.resolve("Raquel Salvador", platform="whatsapp")) == ["Raquel Salvador Esteban"]
    assert "Raquel Nadie" in _names(dr.resolve("Raquel Nadie")), "a lookup still finds the unclassified"
    assert "Raquel Nadie" not in _names(dr.resolve("Raquel", platform="")), "a send never offers them"
    assert _names(dr.resolve("Rakel Karó", platform="email")) == ["Rakel Karó"], \
        "nobody reachable by the act: the match comes back so the door says what is missing"


@pytest.mark.xfail(strict=True, reason="the send door (widgets/mensajeria/outbound/targets.py, another writer's area) "
                                       "does not pass its channel to directory.resolve(platform=…) yet")
def test_the_send_door_mails_only_who_has_an_address(world):
    d, _dr = world
    _put(d, SPANISH)
    from widgets.mensajeria.outbound import targets
    t = targets.resolve_target({"contact": "Raquel Salvador", "channel": "email", "text": "hola"})
    assert t["ok"] is True and t["to"] == "raquel.se@example.org", t


# ── literal, margin, learning ────────────────────────────────────────────────────────────────────────────────

def test_a_name_in_quotes_is_matched_literally(world):
    d, dr = world
    _put(d, SPANISH)
    for quoted in ('"Raquel"', "«Raquel»", "“Raquel”"):
        assert "Rakel Karó" not in _names(dr.resolve(quoted)), quoted
    assert _names(dr.resolve("«Rakel»")) == ["Rakel Karó"]


def test_the_margin_is_his_rule(world):
    d, dr = world
    _put(d, SPANISH)
    import rules
    assert rules.value(rules.path(widget="contactos"), "clear_margin") == 3, "the manifest's default, as a rule row"
    row = rules.add("widget:contactos", "pref", "clear_margin", 99, text="always ask me which one")
    dr._MARGIN.clear()
    try:
        hits = dr.resolve("Raquel")
        assert len(hits) > 1 and hits[0]["name"] == "Rakel Karó", "a margin nobody reaches: a question, closest first"
    finally:
        rules.remove(row["id"])
        dr._MARGIN.clear()


def test_his_pick_is_learned_on_that_contact(world):
    d, dr = world
    _put(d, _no_favorite_two_recent())
    hits = dr.resolve("Raquel")
    dr.asked("Raquel", hits[: dr.CANDIDATES_MAX])
    pick = hits[1]
    got = dr.answered(pick)
    assert got["alias"] == "Raquel"
    from widgets.contactos import model
    row = next(c for c in d.load_db()["contacts"] if c["id"] == pick["id"])
    assert row["aliases"] == ["Raquel"] and model.alias_source(row, "Raquel") == "learned"
    assert _names(dr.resolve("Raquel")) == [pick["name"]], "never asked twice"
    assert _names(dr.resolve("Rakel")) == [pick["name"]], "his word, however it is spelled"


def test_sound_is_a_generic_normaliser():
    from widgets import directory as dr
    same = [("Raquel", "Rakel"), ("Jordi", "Jordy"), ("Vanessa", "Banesa"), ("Karó", "Caro"), ("Helena", "Elena"),
            ("Lluís", "Yuis"), ("Katherine", "Catherine"), ("Philip", "Filip"), ("Núria", "Nuria")]
    assert all(dr.sound(a) == dr.sound(b) for a, b in same), [(a, b) for a, b in same if dr.sound(a) != dr.sound(b)]
    assert dr.sound("Pablo") != dr.sound("Paula") and dr.sound("Ana") != dr.sound("Eva")
