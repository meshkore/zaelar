"""An exclusion reaches the sheet DECLARED, and a criteria change never names a subject by its capitals (node 2.835).

search-buy-used-car ES (V2-835, 2026-11-02). He said «evita coches de flexicar» (lowercase); the turn recorded the
criteria change in its own words, «excluir los coches de Flexicar (regla personal…)». The door read the change's
capitals as the SUBJECT every row must name, so every car that was not from Flexicar went to the Rejected tab and
the one Flexicar car stayed: the exclusion worked as an inclusion. The negation table never knew «excluir», and
growing it is not the fix (word tables only shrink). Now a change adds no subject at all, and what he rules out is
`criteria.excluded` — a list of names, carried structured by the `criteria` op.
"""
from __future__ import annotations

from search import category
from widgets.results import category_gate
from widgets.results import data as sheet

#: His commissioning words, as recorded (the link cut).
ASK_ES = ("Quiero compar un coche. HE visto este: https://www.autoscout24.es/anuncios/"
          "mercedes-benz-glc-220-220d-4matic-aut-diesel-gris-cat_ma47mo21086-e55b85a5")
CHANGE_ES = "excluir los coches de Flexicar (regla personal para búsquedas de coches)"
CARS = [
    {"title": "Mercedes-Benz GLC 220 d 4Matic AMG Line", "price": "€ 23.499",
     "url": "https://www.autoscout24.es/anuncios/mercedes-benz-glc-220-d-4matic-a7a15bb8"},
    {"title": "Mercedes-Benz GLC 220d 4MATIC 2019", "price": "23.990 €",
     "url": "https://www.coches.net/mercedes-benz-glc-220d-4matic-2019-48211"},
    {"title": "GLC 220d 4MATIC (2020)", "subtitle": "Negro · FLEXICAR COSLADA (Madrid) · 23.990 €", "price": "23.990 €",
     "url": "https://www.autoscout24.es/anuncios/mercedes-benz-glc-220d-4matic-negro-5b68d80e"},
]

ASK_EN = "Find me a two-bedroom flat to rent in Lisbon under 1,500 euros a month"
CHANGE_EN = "avoid Airbnb listings, only long-term rentals"
FLATS = [
    {"title": "2-bed flat in Alfama, long term", "price": "€1,350", "url": "https://www.idealista.pt/en/imovel/3301"},
    {"title": "Bright 2BR in Graça", "price": "€1,420", "url": "https://www.airbnb.com/rooms/99812"},
    {"title": "Two-bedroom apartment, Arroios", "price": "€1,290", "url": "https://www.imovirtual.com/anuncio/88"},
]


def _titles(rows):
    return [r["title"] for r in rows]


def test_a_change_in_the_models_words_names_no_subject():
    data = {"asked": ASK_ES, "criteria": {"changes": [CHANGE_ES]}, "items": []}
    on, _ = category_gate.gate(data, CARS, {})
    assert _titles(on) == _titles(CARS), "«Flexicar» in a change became the subject every car must name"


def test_a_declared_exclusion_rules_out_its_rows_by_title_or_link():
    data = {"asked": ASK_ES, "criteria": {"changes": [CHANGE_ES], "excluded": ["Flexicar"]}, "items": []}
    on, off = category_gate.gate(data, CARS, {})
    assert _titles(on) == _titles(CARS[:2])
    assert [r["why"] for r in data["rejected"]] == ["he ruled out «flexicar»"] and off["off_category"]


def test_the_criteria_op_carries_it_and_rejudges_the_rows_already_there():
    sid = "t2835a"
    sheet.store.save(sheet.sheet_key(sid), {"title": "Mercedes GLC 220d", "asked": ASK_ES, "items": list(CARS)})
    res = sheet.apply_action("criteria", {"sheet": sid, "criteria": {"changes": [CHANGE_ES], "excluded": ["Flexicar"]}})
    view = sheet.view_data(sid)
    assert res["ok"] and view["criteria"]["excluded"] == ["Flexicar"]
    assert _titles(view["items"]) == _titles(CARS[:2])
    sheet.apply_action("criteria", {"sheet": sid, "criteria": {"excluded": ["Clicars"]}})
    assert sheet.view_data(sid)["criteria"]["excluded"] == ["Flexicar", "Clicars"], "a later one adds"
    sheet.apply_action("append", {"sheet": sid, "items": [{"title": "Mercedes-Benz GLC 220 d", "price": "24.900 €",
                                                            "url": "https://www.flexicar.es/mercedes-benz/glc/7731"}]})
    assert _titles(sheet.view_data(sid)["items"]) == _titles(CARS[:2]), "a later row by its link alone"


def test_another_domain_and_language():
    data = {"asked": ASK_EN, "criteria": {"changes": [CHANGE_EN]}, "items": []}
    on, _ = category_gate.gate(data, FLATS, {})
    assert _titles(on) == _titles(FLATS), "«Airbnb» in a change is no subject"
    data = {"asked": ASK_EN, "criteria": {"changes": [CHANGE_EN], "excluded": ["Airbnb"]}, "items": []}
    on, _ = category_gate.gate(data, FLATS, {})
    assert _titles(on) == [FLATS[0]["title"], FLATS[2]["title"]]


def test_a_declared_exclusion_is_never_a_subject_even_in_his_words():
    ask = category.asked_from("Busco un GLC 220d, pero nada de Flexicar", (), None, ["Flexicar"])
    assert "flexicar" not in ask["subjects"] and ask["declared_out"] == ["flexicar"]


def test_his_own_words_still_name_the_subject_without_a_brief():
    data = {"asked": "Búscame entradas para un concierto de Rosalía en Madrid",
            "criteria": {"changes": ["solo entradas de Rosalía, nada del Teatro Real"]}, "items": []}
    rows = [{"title": "Rosalía — Motomami Tour, WiZink Center", "price": "80 €", "url": "https://x/r"},
            {"title": "El Cascanueces — Teatro Real", "price": "40 €", "url": "https://x/c"}]
    on, _ = category_gate.gate(data, rows, {})
    assert _titles(on) == [rows[0]["title"]]
    assert category.asked_from("un monitor Samsung o LG de 27 pulgadas")["subjects"] == ["samsung", "lg"]


TICKETS_ASK = "entradas para un concierto en Madrid este mes"
TICKETS_CHANGE = "solo entradas de Rosalía"
TICKETS = [
    {"title": "Rosalía · Motomami Tour", "price": "85 €", "url": "https://www.ticketmaster.es/event/rosalia-1"},
    {"title": "El Cascanueces · Ballet de Moscú", "price": "40 €", "url": "https://www.ticketmaster.es/event/cascanueces-2"},
]


@__import__("pytest").mark.xfail(strict=True, reason=(
    "DECLARED DEBT (V2-835 audit §8.2): a subject that lives ONLY in a criteria change is no longer read — a change is "
    "the turn's paraphrase and its capitals no longer make a subject. The class: the `criteria` op cannot DECLARE a "
    "subject yet (`criteria.subjects` is written by the research brief only). When it can, this turns green."))
def test_a_subject_said_only_in_a_change_narrows_the_list_once_the_op_can_declare_it():
    data = {"asked": TICKETS_ASK, "criteria": {"changes": [TICKETS_CHANGE]}, "items": []}
    on, _ = category_gate.gate(data, TICKETS, {})
    assert _titles(on) == ["Rosalía · Motomami Tour"]
