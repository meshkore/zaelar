"""V2-849 step 4 · his answer to «which one?» is remembered: the word he used becomes that person's, asked once.

His three sentences, from the phone: «send Raquel a message that I'm going home» (several Raquels — ask which ONCE: she
is his wife, the default forever after), «send mum a message that I've done the transfer» (no contact is named
«Mamá»; thirteen names carry «Mama» as a label — «Amiga Mama», «Francisco Vecino Mama»), «ask Pablo if he tried
Zaelar» (several Pablos — ask which).

The mechanism (one door each):
  · the send door that asked records the question (`directory.asked`: the word he used, who was asked about); a
    narrower question about the same word keeps his word;
  · the send that goes to one of those people (`send_to` queued, never a lookup) hands it back
    (`directory.answered`): his word becomes the person's alias through the contacts card's own `set_alias`;
  · a person named by WHO they are to him (`relation`, a value the contacts manifest declares) is looked up by that
    relation only — never by a name that carries the word — and his answer becomes the relation and the alias;
  · `set_alias` (a word, a relation) is his own word: declared `worker: false`, so a worker cannot write them.
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture
def world(tmp_path, monkeypatch):
    """ISOLATED stores — never the operator's real directory or messages."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import directory
    directory._ASKED.clear()
    from widgets.contactos import data as ct
    from widgets.mensajeria import data as ms
    yield ct, ms, directory
    directory._ASKED.clear()


def _put(ct, *rows):
    db = ct.load_db()
    for i, r in enumerate(rows):
        db["contacts"].append({"id": f"c{i}", "kind": "person", "aliases": [], "relation": "", **r})
    ct.store.save(ct.WIDGET_ID, db)


def _wa(n: int, days_ago: float = 400.0) -> list[dict]:
    jid = f"3460000000{n}@s.whatsapp.net"
    return [{"platform": "whatsapp", "handle": jid, "chatId": jid, "volume": 1, "last_seen": time.time() - days_ago * 86400}]


def _send(ms, **payload):
    return ms.apply_action("send_to", {"text": "voy a casa ahora", **payload})


def _row(ct, cid: str) -> dict:
    return next(c for c in ct.load_db()["contacts"] if c["id"] == cid)


# ── «Raquel»: asked once ───────────────────────────────────────────────────────────────────────────────────────

def test_his_raquel_is_asked_once_and_never_again(world):
    ct, ms, _dr = world
    # V2-854: two of them talked to lately — one would be the answer by the recent-conversation flag, not a question
    _put(ct, {"name": "Raquel Jofre", "channels": _wa(1, days_ago=5)}, {"name": "Raquel Ares", "channels": _wa(2, days_ago=3)},
         {"name": "Raquel Salvador Esteban", "channels": _wa(3)}, {"name": "raquel.salvadoresteban", "channels": _wa(4)})
    first = _send(ms, contact="Raquel")
    assert first["ok"] is False and len(first["candidates"]) == 3, "several Raquels: a question, never a pick"
    narrower = _send(ms, contact="Raquel Salvador")
    assert narrower["ok"] is False, "his answer still matches two rows: asked again, narrower"
    sent = _send(ms, contact="Raquel Salvador Esteban")
    assert sent["ok"] is True and sent["result"]["learned"] == {"alias": "Raquel", "contact": "Raquel Salvador Esteban"}
    assert _row(ct, "c2")["aliases"] == ["Raquel"], "the word he FIRST used is the one he will say again"
    again = _send(ms, contact="Raquel")
    assert again["ok"] is True and again["result"]["to"] == "Raquel Salvador Esteban" and "learned" not in again["result"]


def test_his_own_word_for_her_is_hers_from_the_card(world):
    ct, ms, _dr = world
    _put(ct, {"name": "Raquel Salvador Esteban", "channels": _wa(3)})
    assert ct.apply_action("set_alias", {"contactId": "c0", "alias": "mi tontita"})["ok"] is True
    assert _send(ms, contact="mi tontita")["result"]["to"] == "Raquel Salvador Esteban"


def test_an_alias_is_one_persons_and_can_be_taken_back(world):
    ct, _ms, dr = world
    _put(ct, {"name": "Raquel Jofre"}, {"name": "Raquel Salvador Esteban"})
    ct.apply_action("set_alias", {"contactId": "c0", "alias": "Raquel"})
    ct.apply_action("set_alias", {"contactId": "c1", "alias": "raquel"})
    assert _row(ct, "c0")["aliases"] == [] and _row(ct, "c1")["aliases"] == ["raquel"], "the word moved"
    ct.apply_action("set_alias", {"contactId": "c1", "alias": "Raquel", "remove": True})
    assert _row(ct, "c1")["aliases"] == [] and len(dr.resolve("Raquel")) == 2, "«no, esa no»: asked again"


# ── «mamá»: a relation, asked, never read off a label ─────────────────────────────────────────────────────────

def test_mum_is_asked_never_picked_from_a_label_and_then_known(world):
    ct, ms, _dr = world
    _put(ct, {"name": "Amiga Mama", "channels": _wa(1)}, {"name": "Francisco Vecino Mama", "channels": _wa(2)},
         {"name": "Carmen López", "channels": _wa(3)})
    asked = _send(ms, contact="mamá", relation="mother", text="ya he hecho el bizum")
    assert asked["ok"] is False and asked["say"] == "widgets.mensajeria.refusal_who_is_relation"
    sent = _send(ms, contact="Carmen López", text="ya he hecho el bizum")
    assert sent["ok"] is True and sent["result"]["learned"]["relation"] == "mother"
    assert _row(ct, "c2")["relation"] == "mother" and _row(ct, "c2")["aliases"] == ["mamá"]
    assert _send(ms, contact="mi madre", relation="mother")["result"]["to"] == "Carmen López"
    assert _send(ms, contact="mum", relation="mother")["result"]["to"] == "Carmen López", "the same in English"


def test_a_relation_outside_the_declared_vocabulary_is_refused(world):
    ct, _ms, _dr = world
    _put(ct, {"name": "Carmen López"})
    assert ct.apply_action("set_alias", {"contactId": "c0", "relation": "boss"})["ok"] is False


# ── what is never learned ──────────────────────────────────────────────────────────────────────────────────────

def test_a_send_to_somebody_he_was_not_asked_about_learns_nothing(world):
    ct, ms, _dr = world
    _put(ct, {"name": "Pablo Sabin", "channels": _wa(1)}, {"name": "Pablo Hernandez", "channels": _wa(2)},
         {"name": "Lucía Gil", "channels": _wa(3)})
    assert _send(ms, contact="Pablo")["ok"] is False
    assert "learned" not in _send(ms, contact="Lucía Gil")["result"]
    assert _row(ct, "c2")["aliases"] == []


def test_a_question_left_unanswered_expires(world, monkeypatch):
    ct, ms, dr = world
    _put(ct, {"name": "Pablo Sabin", "channels": _wa(1)}, {"name": "Pablo Hernandez", "channels": _wa(2)})
    _send(ms, contact="Pablo")
    dr._ASKED["at"] = time.time() - dr.ASKED_FOR_S - 1
    assert "learned" not in _send(ms, contact="Pablo Sabin")["result"]


def test_a_lookup_learns_nothing_only_a_send_does(world):
    ct, ms, _dr = world
    _put(ct, {"name": "Pablo Sabin", "channels": _wa(1)}, {"name": "Pablo Hernandez", "channels": _wa(2)})
    _send(ms, contact="Pablo")
    from widgets.mensajeria.outbound import targets
    assert targets.resolve_target({"contact": "Pablo Sabin", "text": "x"})["ok"] is True
    assert _row(ct, "c0")["aliases"] == [], "the consent rule's read-only lookup is not his answer"


def test_a_worker_cannot_write_who_a_person_is_to_him():
    from nucleo.cli import worker_policy as wp
    assert wp.classify_act("widget_data", {"widget_id": "contactos", "action": "set_alias"}) == wp.DENY


def test_an_older_store_gains_the_two_fields(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store.save("contactos", {"_v": 2, "contacts": [{"id": "c1", "name": "Ana", "phone": "", "email": ""}], "next_id": 2})
    from widgets.contactos import data as ct
    row = ct.load_db()["contacts"][0]
    assert row["aliases"] == [] and row["relation"] == ""
