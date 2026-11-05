"""Each person of his address book is ONE structured pill of his memory, in a lane of its own (V2-854 F3).

The class: contacts were not in memory at all, so «the girl from the guitar course» could never reach a contact.
Indexing them naively breaks two other things: a pill is text a model reads (a phone number or an address must
never be in it), and thousands of people would win every one of his own recalls by sheer volume. So the line is
structured (names, kind, relation, groups, platforms — no number, no address, notes redacted), it lives in the
`contacts` lane (out of `own` and `all`), a changed record supersedes its line, a record that leaves the book (or
that he hid) has its line invalidated, and a pass that finds nothing changed writes nothing.

Two languages and two kinds on purpose (a person in Spanish, a company in English).
"""
from __future__ import annotations

import json

from memory import retriever
from nucleo.memory_agent import contacts as mc
from tests.memory.unit._address_book import add, book, contact_pills  # noqa: F401 — `book` is the fixture


def _seed(card) -> tuple[str, str]:
    lucia = add(card, name="Lucía Ferrer", phone="+34 611 222 333", email="lucia.ferrer@example.com",
                group="Curso de guitarra", notes="La conocí en el curso, su móvil es 611 222 333")
    acme = add(card, name="Northwind Plumbing", kind="company", email="desk@northwind.example", city="Leeds")
    return lucia, acme


def test_each_record_is_one_structured_pill_without_a_number_or_an_address(book):
    lucia, acme = _seed(book)
    rep = mc.sync()
    assert rep["written"] == 2 and rep["pending"] == 0
    pills = {p["slot"]: p for p in contact_pills()}
    assert set(pills) == {f"contact:{lucia}", f"contact:{acme}"}
    line = pills[f"contact:{lucia}"]["text"]
    for leak in ("611", "222", "333", "@", "example.com"):
        assert leak not in line, line
    assert "Curso de guitarra" in line and "reachable on: email, phone" in line and f"[contact:{lucia}]" in line
    meta = json.loads(pills[f"contact:{acme}"]["meta"])
    assert meta["contact_id"] == acme and meta["contact_kind"] == "company" and meta["channels"] == ["email"]
    assert "desk@" not in json.dumps(meta)


def test_the_people_never_crowd_his_own_recall_and_are_found_in_their_lane(book):
    lucia, _ = _seed(book)
    mc.sync()
    own = retriever.search("curso de guitarra Lucía", lane=retriever.LANE_OWN, limit=10)
    every = retriever.search("curso de guitarra Lucía", lane=retriever.LANE_ALL, limit=10)
    assert not [h for h in own + every if h["kind"] == "contact"], own + every
    lane = retriever.search("curso de guitarra Lucía", lane=retriever.LANE_CONTACTS, limit=10, expand=False)
    assert lane and lane[0]["slot"] == f"contact:{lucia}" and {h["kind"] for h in lane} == {"contact"}


def test_a_changed_record_supersedes_its_line_and_a_quiet_pass_writes_nothing(book):
    lucia, acme = _seed(book)
    mc.sync()
    assert mc.sync() == {"written": 0, "removed": 0, "pending": 0}
    book.apply_action("update_contact", {"contactId": lucia, "groups": "Familia"})
    assert mc.sync()["written"] == 1
    pills = {p["slot"]: p["text"] for p in contact_pills()}
    assert "Familia" in pills[f"contact:{lucia}"] and "guitarra" not in pills[f"contact:{lucia}"]
    assert len(pills) == 2                                  # superseded, not added beside


def test_a_record_he_hid_or_deleted_leaves_the_index(book):
    lucia, acme = _seed(book)
    mc.sync()
    book.apply_action("hide_contact", {"contactId": lucia})
    book.apply_action("remove_contact", {"contactId": acme})
    assert mc.sync()["removed"] == 2
    assert contact_pills() == []


def test_a_large_book_is_indexed_closest_first_over_bounded_passes(book):
    ids = [add(book, name=f"Persona Número{i:03d}") for i in range(7)]
    star = add(book, name="Zoe Marlowe", favorite=True)
    rep = mc.sync(limit=3)
    assert rep == {"written": 3, "removed": 0, "pending": 5}
    assert f"contact:{star}" in {p["slot"] for p in contact_pills()}      # his circle first
    while mc.sync(limit=3)["pending"]:
        pass
    assert len(contact_pills()) == len(ids) + 1


def test_a_line_is_never_paid_an_embedding_nor_left_for_repair(book):
    """Read by its words only: a vector per person would be the first index's cost, paid for no reader."""
    from memory import db as memdb
    from memory.rem import repair
    _seed(book)
    mc.sync()
    db = memdb.get_db()
    assert db.vec_available
    ids = [p["id"] for p in contact_pills()]
    ph = ",".join("?" * len(ids))
    assert db.query(f"SELECT COUNT(*) c FROM vec_memories WHERE memory_id IN ({ph})", ids)[0]["c"] == 0
    assert repair._pending_without_vector(db) == 0


def test_a_name_that_is_a_number_or_an_address_never_reaches_a_line(book):
    """Some records are NAMED by their number or address (a chat nobody renamed, an entry made from a mail)."""
    only_number = add(book, name="+34 622 333 444")
    mixed = add(book, name="Pere Oms pere.oms@example.com", city="Reus")
    mc.sync()
    pills = {p["slot"]: p for p in contact_pills()}
    assert f"contact:{only_number}" not in pills
    line = pills[f"contact:{mixed}"]["text"] + pills[f"contact:{mixed}"]["meta"]
    assert "Pere Oms" in line and "@" not in line and "example.com" not in line
