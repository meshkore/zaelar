"""REM links the records of one person, never deletes them, and leaves the doubtful ones to him (V2-854 F3).

The class: one person arrives as several records (a chat with a nickname and a phone, an address-book entry with the
same phone and an e-mail, a second entry made from that e-mail), none linked, so a name finds one third of her. The
deep sleep links them (`parentId`, through the card's own `link_contact`) when an identifier only one person has
ties them AND the names fit one person; everything else — a home line two people share, a switchboard, names that
contradict the shared number, two near-identical names with nothing in common — is a PROPOSAL kept for him. Nothing
is ever deleted, and a second sleep links nothing new.

Synthetic people shaped like a real book (Spanish and English names, a family line, a company switchboard).
"""
from __future__ import annotations

from memory import api as memapi
from memory import rem
from memory.rem import contacts as rule
from nucleo.memory_agent import contacts as mc
from tests.memory.unit._address_book import add, book  # noqa: F401 — `book` is the fixture


def _seed(card) -> dict:
    ids = {
        # one person, three records: the chat (nickname + phone), the entry (phone + mail), the entry from the mail
        "chat": add(card, name="Marta", phone="+34 611 222 333", favorite=True),
        "entry": add(card, name="Marta Soler Vidal", phone="611222333", email="marta.soler@example.com"),
        "from_mail": add(card, name="marta.soler", email="marta.soler@example.com"),
        # a home line two different people share: same surname, different first names
        "joan": add(card, name="Joan Puig", phone="+34 933 444 555"),
        "anna": add(card, name="Anna Puig", phone="933444555"),
        # a switchboard three records share
        "desk1": add(card, name="Northwind Sales", kind="company", phone="+44 20 7946 0000"),
        "desk2": add(card, name="Northwind Support", kind="company", phone="020 7946 0000"),
        "desk3": add(card, name="Northwind Billing", kind="company", phone="2079460000"),
        # near-identical names, nothing in common
        "laia": add(card, name="Laia Vidal", email="laia@home.example"),
        "laia2": add(card, name="laia.vidal", email="lvidal@work.example"),
    }
    return ids


def _contacts(card) -> dict:
    return {c["id"]: c for c in card.load_db()["contacts"]}


def test_one_persons_records_are_linked_to_the_one_that_stands_for_her(book):
    ids = _seed(book)
    rep = mc.unify()
    assert rep["linked"] == 2, rep
    cs = _contacts(book)
    assert len(cs) == len(ids)                                   # nothing deleted
    head = ids["chat"]                                           # his mark (favorite) stands for her
    assert cs[ids["entry"]]["parentId"] == head and cs[ids["from_mail"]]["parentId"] == head
    for k in ("joan", "anna", "desk1", "desk2", "desk3", "laia", "laia2"):
        assert cs[ids[k]]["parentId"] == "", k


def test_the_doubtful_ones_are_proposals_for_him(book):
    ids = _seed(book)
    mc.unify()
    props = {tuple(p["ids"]): p["reason"] for p in memapi.kv_get(mc.PROPOSALS_KEY, [])}
    assert props[tuple(sorted((ids["anna"], ids["joan"])))] == "names-differ:tel"
    assert props[tuple(sorted((ids["desk1"], ids["desk2"], ids["desk3"])))] == "shared:tel"
    assert props[tuple(sorted((ids["laia"], ids["laia2"])))] == "near-name"
    assert not [p for p in props if ids["entry"] in p or ids["from_mail"] in p]   # settled by the links


def test_a_second_sleep_links_nothing_new(book):
    _seed(book)
    mc.unify()
    again = rule.same_person(list(_contacts(book).values()))
    assert again["links"] == []


def test_a_group_is_never_unified_and_a_record_under_her_company_is_never_moved(book):
    a = add(book, name="Familia Soler", kind="group", phone="611222333")
    b = add(book, name="Marta Soler", phone="+34 611 222 333")
    co = add(book, name="Soler Arquitectes", kind="company")
    c = add(book, name="Marta Soler Vidal", phone="611222333")
    book.apply_action("link_contact", {"contactId": c, "parentId": co})
    found = rule.same_person(list(_contacts(book).values()))
    assert found["links"] == []                                  # the group is not a person; her company holds c
    assert {"ids": sorted((b, c)), "reason": "has-parent"} in found["proposals"]
    assert not [p for p in found["proposals"] if a in p["ids"]]


def test_the_phase_runs_in_the_deep_sleep(book):
    ids = _seed(book)
    assert "contacts" in rem._PHASES
    report = rem.run()
    assert report["contacts"]["unify"]["linked"] == 2
    assert _contacts(book)[ids["entry"]]["parentId"] == ids["chat"]
