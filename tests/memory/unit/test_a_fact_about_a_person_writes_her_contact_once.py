"""What he says about a person of his book is written on her contact ONCE, when the fact is written (V2-854 F3).

«Noemí es mi mujer», «mi hermano Pau tiene un taller que se llama Motos Pau»: the distiller already reads every
turn; it now says WHICH person a pill names and who she is to him (a value of the card's declared `relations`, never
a word list here). The memory's writer resolves the name through the contacts resolver and, when exactly ONE contact
is that name, writes the relation and the other name he uses through the card's own door (`set_alias`) and stamps the
pill with her contact id. No model per send, no question to him: an ambiguous or unknown name writes nothing.

Two languages on purpose (a partner in Spanish, a brother's business in English).
"""
from __future__ import annotations

import asyncio
import json

from memory import db as memdb
from nucleo.memory_agent import ingest
from nucleo.memory_agent.processor import distill, distill_prompt
from tests.memory.unit._address_book import add, book  # noqa: F401 — `book` is the fixture


def _write(text: str, person: dict) -> dict:
    asyncio.run(ingest._write_atom({"text": text, "dest": "long", "kind": "fact", "person": person}, raw=text))
    row = memdb.get_db().query_one("SELECT meta FROM memories WHERE text=? ORDER BY id DESC", (text,))
    return json.loads(row["meta"])


def _contact(card, cid: str) -> dict:
    return next(c for c in card.load_db()["contacts"] if c["id"] == cid)


def test_a_relation_he_states_lands_on_the_one_contact_with_that_name(book):
    noemi = add(book, name="Noemí Soler")
    add(book, name="Marta Soler")
    meta = _write("Noemí es su mujer.", {"name": "Noemí", "relation": "partner", "known_as": ""})
    assert meta["contact_id"] == noemi
    assert _contact(book, noemi)["relation"] == "partner"


def test_another_name_he_uses_becomes_a_learned_word_on_her_contact(book):
    pau = add(book, name="Pau Riera")
    meta = _write("His brother Pau runs a garage called Riera Motors.",
                  {"name": "Pau", "relation": "sibling", "known_as": "Riera Motors"})
    assert meta["contact_id"] == pau
    c = _contact(book, pau)
    assert c["relation"] == "sibling" and "Riera Motors" in c["aliases"]


def test_said_again_it_writes_nothing_new(book):
    from widgets import store
    noemi = add(book, name="Noemí Soler")
    _write("Noemí es su mujer.", {"name": "Noemí", "relation": "partner", "known_as": "Raki"})
    rev = store.revision("contactos")
    _write("Su mujer, Noemí, trabaja en Lleida.", {"name": "Noemí", "relation": "partner", "known_as": "Raki"})
    assert store.revision("contactos") == rev
    assert _contact(book, noemi)["aliases"].count("Raki") == 1


def test_an_ambiguous_or_unknown_name_writes_nothing_and_asks_nobody(book):
    a, b = add(book, name="Marc Puig"), add(book, name="Marc Vidal")
    meta = _write("Marc es su compañero de trabajo.", {"name": "Marc", "relation": "colleague", "known_as": ""})
    assert "contact_id" not in meta
    assert _contact(book, a)["relation"] == _contact(book, b)["relation"] == ""
    assert "contact_id" not in _write("Iris is his cousin.", {"name": "Iris", "relation": "family", "known_as": ""})


def test_a_relation_outside_the_declared_vocabulary_is_never_written(book):
    jan = add(book, name="Jan Moll")
    meta = _write("Jan es su vecino.", {"name": "Jan", "relation": "neighbour", "known_as": ""})
    assert meta["contact_id"] == jan and _contact(book, jan)["relation"] == ""


def test_the_distiller_names_the_person_with_the_cards_vocabulary():
    system = distill_prompt.messages("hola", {})[0]["content"]
    assert "{RELATIONS}" not in system and "partner" in system and "sibling" in system
    pill = distill._pill({"text": "Su hermana Lucía tiene una floristería.", "dest": "long", "kind": "fact",
                          "person": {"name": "Lucía", "relation": "sibling", "known_as": None}})
    assert pill["person"] == {"name": "Lucía", "relation": "sibling", "known_as": ""}
    assert distill._pill({"text": "Le gusta el pádel.", "dest": "long", "person": "x"})["person"] is None
