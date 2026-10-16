"""A subject is any of the names he offered, siglas included; the sheet never forgets the sentence that opened it (node 12.12).

Measured 2026-10-16 (audit V2-783 P0-1): «un monitor Samsung o LG de 27 pulgadas» read ONE subject, «samsung»,
because the subject reader took Title-case runs only and «LG» is two capitals — every LG monitor left for «does not
name «samsung»». And `keep_asked` kept the LAST 900 characters of `asked`, so after a few corrections the sentence that
commissioned the hunt — the one that names the subject — was the part cut off.
"""
from __future__ import annotations

from search import asked as _asked
from search import category
from widgets.results import category_gate


def _ask(text: str) -> dict:
    return category.asked_from(text)


def test_a_sigla_offered_as_an_alternative_is_a_subject_too():
    assert _asked.subjects("un monitor Samsung o LG de 27 pulgadas") == ["samsung", "lg"]
    assert _asked.subjects("a Dell or HP laptop under 600") == ["dell", "hp"]
    assert _asked.subjects("una moto Honda, Yamaha o KTM de 125") == ["honda", "yamaha", "ktm"]


def test_a_row_naming_any_of_the_offered_names_stays():
    ask = _ask("un monitor Samsung o LG de 27 pulgadas")
    lg = {"title": "LG 27UL500-W 27\" 4K UHD monitor", "price": "149 €", "url": "https://x/lg"}
    samsung = {"title": "Samsung S27E510C 27\" curved", "price": "120 €", "url": "https://x/s"}
    aoc = {"title": "AOC 27B2H 27\" IPS", "price": "99 €", "url": "https://x/a"}
    assert category.why_off(lg, ask) == ""
    assert category.why_off(samsung, ask) == ""
    assert "does not name" in category.why_off(aoc, ask)


def test_a_sigla_that_is_a_spec_or_a_category_is_still_no_subject():
    assert _asked.subjects("un SUV diésel 4K TDI") == []
    assert _asked.subjects("quiero una TV grande") == []


def test_the_sentence_that_opened_the_hunt_survives_every_correction():
    data: dict = {"asked": "", "items": [], "criteria": {}}
    category_gate.keep_asked(data, {}, {"asked": "Búscame entradas para un concierto de Rosalía en Madrid este mes."})
    for i in range(40):
        data["asked"] = (data["asked"] + " " + f"corrección número {i}: mejor en la zona centro y no muy caro.").strip()
        category_gate.keep_asked(data, {}, {})
    assert data["asked"].startswith("Búscame entradas para un concierto de Rosalía")
    assert len(data["asked"]) <= category_gate._MAX_ASKED
    assert data["asked"].endswith("corrección número 39: mejor en la zona centro y no muy caro.")
