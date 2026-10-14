"""A neighbourhood he would LIKE, or a zone he names, is never a subject every row must name (node 2.675).

search-rent-apartment ES (2026-10-14, sandbox 093858-es): «si puedes, mira por Ruzafa o el centro» reached the sheet
as «zona: Ruzafa o el centro, bien comunicado», and the three real Valencia flats from Fotocasa went to the Rejected
tab «does not name «ruzafa»». «an apartment in the Mission» is the same family in English.
"""
from __future__ import annotations

import pytest

from search import asked, row_fit

FC = "https://www.fotocasa.es/es/alquiler/vivienda/valencia-capital/"
ASKED = "Búscame un piso de alquiler en Valencia, dos habitaciones, por menos de 1.100 euros al mes, que admita mascotas."
#: The sheet's `asked` + the criteria change the turn wrote from his sentence (`category_gate._own`), as recorded.
OWN = ASKED + " zona: Ruzafa o el centro, bien comunicado"
ROWS = [
    {"title": "Apartamento con 1 baño en…", "price": "850 €", "url": FC + "aire-acondicionado-calefaccion-amueblado-internet/187250997/d"},
    {"title": "Piso con 2 baños en Valencia…", "price": "1.045 €", "url": FC + "ascensor-patio-amueblado/189303858/d"},
]


def test_the_measured_valencia_flats_stay_on_the_sheet():
    on, off = row_fit.split(ROWS, OWN, ["Buscar piso alquiler Valencia 2 hab mascotas <1100€"])
    assert off == []
    assert [r["title"] for r in on] == [r["title"] for r in ROWS]


@pytest.mark.parametrize("text", [
    "zona: Ruzafa o el centro, bien comunicado",
    "si puedes, mira por Ruzafa o el centro",
    "Busco piso en Valencia, Ruzafa si puedes",
    "Busco piso, preferiblemente Ruzafa",
    "Busco piso en Valencia. Si puedes, Ruzafa.",
    "el centro o Ruzafa",
    "barrio de Ruzafa",
    "an apartment in the Mission",
    "a flat near the Mission district",
    "find me a flat, ideally Soho or Chelsea",
    "I want a flat. If possible, Soho.",
    "downtown or the Mission",
    "neighborhood: Mission",
])
def test_a_zone_or_a_soft_wish_names_no_subject(text):
    assert asked.subjects(text) == []


@pytest.mark.parametrize("text, subject", [
    ("Búscame entradas para un concierto de Rosalía en Madrid", "rosalia"),
    ("Busco entradas de Rosalía si puedes", "rosalia"),
    ("Find tickets for Bad Bunny, ideally near the stage", "bad bunny"),
    ("tickets to the Weeknd concert", "weeknd"),
])
def test_the_name_he_asks_about_is_still_his_subject(text, subject):
    assert asked.subjects(text) == [subject]
