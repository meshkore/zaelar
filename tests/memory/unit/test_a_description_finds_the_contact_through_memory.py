"""A DESCRIPTION reaches a contact through his memory (V2-854 F3, decision 2).

«La chica del curso de guitarra del año pasado» names nobody: no resolver over names can answer it. His memory can —
an episode he lived names the person, or her own line in the address book carries the group — and `who()` hands
back the contact ids with the evidence that put each there. It never invents: a description his memory says nothing
about returns nobody, and a first name shared by a crowd is no evidence at all.

Two languages and two domains on purpose (a guitar course in Spanish, a pottery workshop and a plumber in English).
"""
from __future__ import annotations

from memory import writer as memwriter
from nucleo.memory_agent import contacts as mc
from tests.memory.unit._address_book import add, book  # noqa: F401 — `book` is the fixture


def _episode(text: str, **meta) -> int:
    return memwriter.insert_memory(text, kind="event", level="long", meta={"source": "voice", **meta})


def test_an_episode_that_names_her_hands_back_her_contact(book):
    lucia = add(book, name="Lucía Ferrer")
    add(book, name="Lucía Prats")
    add(book, name="Marc Ferrer")
    _episode("El año pasado conoció a Lucía Ferrer en el curso de guitarra.")
    got = mc.who("la chica del curso de guitarra del año pasado")
    assert got and got[0]["contact_id"] == lucia, got
    assert got[0]["evidence"][0]["why"] == "named" and "guitarra" in got[0]["evidence"][0]["text"]


def test_her_own_line_answers_when_the_group_is_the_description(book):
    nora = add(book, name="Nora Vance", group="Pottery workshop")
    add(book, name="Northwind Plumbing", kind="company", group="Home repairs")
    got = mc.who("the woman from the pottery workshop")
    assert got and got[0]["contact_id"] == nora, got
    assert got[0]["evidence"][0]["why"] == "card"


def test_a_fact_written_about_her_points_at_her_by_id(book):
    add(book, name="Ana Ruiz")
    ana = add(book, name="Ana Ruiz", city="Bilbao")          # same name, another person: only the id can tell
    _episode("Ana le recomendó un taller de cerámica en Bilbao.", contact_id=ana)
    got = mc.who("quién me recomendó el taller de cerámica")
    assert got and got[0]["contact_id"] == ana and got[0]["evidence"][0]["why"] == "linked", got


def test_nothing_in_his_memory_means_nobody(book):
    for i in range(12):
        add(book, name=f"Laura Apellido{i:02d}")
    _episode("Laura le habló del curso de guitarra.")         # a first name a crowd shares is no evidence
    assert mc.who("la chica del curso de guitarra") == []
    assert mc.who("") == []
    assert mc.who("the plumber who fixed the boiler") == []


def test_a_memory_that_only_sits_near_the_description_names_nobody(book):
    """The vector channel always returns its nearest rows; an episode with none of his words is not evidence."""
    add(book, name="Marc Ferrer")
    _episode("Cenó con Marc Ferrer en Girona.")
    assert mc.who("the plumber who fixed the boiler") == []
