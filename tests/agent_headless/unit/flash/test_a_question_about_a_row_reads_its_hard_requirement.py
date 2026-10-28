"""A question about a row and one of his must-haves is answered FROM the row — «not verified» when it says «?».

rental-car-automatic-airport (2026-10-11): «¿Puedes confirmarme que [el Polo] es automático y que la recogida y
devolución son en el aeropuerto de Málaga?» got «Voy a pedirle a la búsqueda que lo confirme… ya hay candidatos en
la hoja: «105 € en total»…». `nucleo/flash/row_check.py` appends what the row's hard-requirement fact says (and the
delivery tail is not added on top: the turn answers the question).
"""
from __future__ import annotations

import pytest

from nucleo.flash import row_check
from widgets.results import data as D

SHEET = "rowcheck-1"
HARD = ["cambio automático", "recogida en el aeropuerto de Málaga"]
ITEMS = [
    {"title": "Ver oferta para Volkswagen Polo de EconomyBookings", "price": "93 €",
     "facts": {HARD[0]: "?", HARD[1]: "sí — ficha de DoYouSpain, «Aeropuerto de Málaga (AGP)»"}},
    {"title": "Ver oferta para Volkswagen Taigo de EconomyBookings", "price": "126 €",
     "facts": {HARD[0]: "sí — ficha de rentalcars, «Automático»"}},
    {"title": "Ver oferta para Fiat Panda de EconomyBookings", "price": "90 €"},
]


@pytest.fixture
def sheet(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    D.apply_action("clear", {"sheet": SHEET})
    D.apply_action("criteria", {"sheet": SHEET, "hard": HARD})
    D.apply_action("append", {"sheet": SHEET, "items": ITEMS})
    monkeypatch.setattr(row_check, "_live_sheets", lambda: [SHEET])
    yield D.view_data(SHEET)
    D.apply_action("clear", {"sheet": SHEET})


def test_the_named_row_answers_each_requirement_he_asked_about(sheet):
    out = row_check.line("¿el Polo es automático y en el aeropuerto?", sheet)
    assert "Polo" in out and "Taigo" not in out and "Panda" not in out, out
    assert "cambio automático, sin verificar" in out, "a «?» is said as not verified, never skipped"
    assert "recogida en el aeropuerto de Málaga, sí (lo dice ficha de DoYouSpain" in out


def test_a_question_naming_no_row_says_which_rows_have_it(sheet):
    assert "Con «cambio automático» verificado: Ver oferta para Volkswagen Taigo" in \
        row_check.line("¿alguno es automático?", sheet)


def test_none_verified_is_said_as_none(sheet, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    data = {"criteria": {"hard": ["automatic transmission"]},
            "items": [{"title": "View deal for Jeep Compass", "facts": [{"label": "automatic transmission",
                                                                          "value": "?"}]},
                      {"title": "View deal for Kia Sportage"}]}
    assert row_check.line("are these automatic?", data) == \
        "None of the 2 options on the sheet has «automatic transmission» verified yet."


@pytest.mark.parametrize("heard", ["El Polo me vale de tamaño, lo importante es que sea automático.",
                                   "¿alguna novedad?", "¿cuánto cuesta el Polo?"])
def test_a_statement_or_a_question_about_nothing_he_requires_owes_nothing(sheet, heard):
    assert row_check.line(heard, sheet) == ""


def test_a_word_every_row_shares_names_no_row(sheet):
    """«oferta», «Volkswagen» are in several titles: they do not name ONE of them."""
    out = row_check.line("¿la oferta del Volkswagen es automática?", sheet)
    assert out.startswith("Con «cambio automático» verificado"), out
