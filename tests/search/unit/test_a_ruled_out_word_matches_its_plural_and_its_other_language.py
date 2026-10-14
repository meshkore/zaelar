"""A word he RULES OUT rejects the row in its singular, its plural and its ES/EN twin — first request or correction (node 2.632).

hotel-under-15-days ES (2026-10-14, sandbox 023118-es): «no hostales ni albergues» stood on the sheet while «Hostel
Ikigai», «Urban Cube Hostel Sevilla», «La Banda Living Hostel» and «The Nomad Hostel&Pension» stayed candidates, and
the next reply presented two of them. «hostales» kept its «e» («hostale» never matched «hostal») and the rows said
the same kind of thing in English (`search/excluded.py`, `category_words.SAME_THING`).
"""
from __future__ import annotations

from search import category, excluded

ROWS = [{"title": "Hostel Ikigai", "price": "€ 241"}, {"title": "Urban Cube Hostel Sevilla", "price": "€ 269"},
        {"title": "The Nomad Hostel&Pension", "price": "€ 275"}, {"title": "Hostal Sierpes", "price": "€ 180"},
        {"title": "Albergue Inturjoven Sevilla", "price": "€ 120"}, {"title": "Hotel San Gil", "price": "1.088 €"},
        {"title": "Bellavista Sevilla", "price": "779 €"}]
KEPT = ["Hotel San Gil", "Bellavista Sevilla"]


def _kept(asked: str, context=()) -> list[str]:
    return [r["title"] for r in category.split(ROWS, asked, list(context))[0]]


def test_his_measured_correction_rules_out_every_hostel_in_either_language():
    assert _kept("Búscame un hotel para dos personas, cuatro estrellas. Oye, que te pedí hoteles de 4 estrellas, "
                 "no hostales ni albergues.") == KEPT


def test_an_exclusion_in_the_first_request_reaches_the_door():
    kept = _kept("Búscame un hotel de 4 estrellas en Sevilla para dos, nada de hostales")
    assert "Hostel Ikigai" not in kept and "Hostal Sierpes" not in kept and "Hotel San Gil" in kept


def test_the_english_ask_rules_out_the_spanish_row():
    kept = _kept("find me a 4-star hotel in Seville for two, no hostels")
    assert "Hostal Sierpes" not in kept and "Albergue Inturjoven Sevilla" not in kept and "Hostel Ikigai" not in kept
    assert "Hotel San Gil" in kept


def test_a_guesthouse_is_a_pension():
    assert excluded.named_in("pensiones", "the nomad hostel&pension")
    assert excluded.named_in("guesthouses", "casa pension triana")


def test_a_word_he_asked_for_is_never_read_as_ruled_out():
    # «hostel» in his ask before the negation: hostels are his category, the hotels are not ruled out by it
    kept = [r["title"] for r in category.split(ROWS, "busco un hostel barato, no hoteles", [])[0]]
    assert "Hostel Ikigai" in kept and "Hotel San Gil" not in kept


def test_the_forms_never_cross_into_another_word():
    assert not excluded.named_in("hostales", "hotel san gil")
    assert not excluded.named_in("maquetas", "maquillaje")
    assert excluded.named_in("maquetas", "maqueta seat 600")
