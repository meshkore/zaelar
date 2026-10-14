"""No row of a clean recorded sheet is lost to the ceiling or the place gate (node 2.673) — the false-positive golden.

Every recorded sheet in `fixtures/sheets` that is not marked junk is judged through the whole door (`row_fit`),
first with only what the sheet itself holds (title, goal, criteria), then with the ask its scenario was measured on
— ceilings («menos de 2.500 €», «under $14,000», «por debajo de 300 €») and places («Madrid y alrededores»,
«Valencia», «Austin», «San Diego») included. Not one row may go.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from search import row_fit

SHEETS = Path(__file__).resolve().parents[1] / "fixtures" / "sheets"
CLEAN = sorted(p.name for p in SHEETS.glob("*.json") if not p.stem.endswith(("-junk", "-mixed", "-offsubject")))
#: The ask each scenario was measured on, as the operator would say it.
ASKS = {
    "best-plumber-same-day__es": "Necesito un fontanero urgente hoy en Madrid centro, tengo una fuga de agua",
    "best-plumber-same-day__en": "I need an emergency plumber today in the Mission, San Francisco",
    "best-rated-rental-car__en": "Find me the best rated car rental in Austin for this weekend",
    "best-rated-rental-car__es": "Búscame el alquiler de coche mejor valorado en Málaga este fin de semana",
    "cheapest-monitor__es": "Busco un monitor de 27 pulgadas 4K para trabajar, por debajo de 300 €",
    "cheapest-monitor__en": "Find me the cheapest decent monitor for work, under €350",
    "hotel-under-15-days__en": "A 4-star hotel in San Diego for Oct 16-20, under $400 a night",
    "search-buy-motorcycle__es": "Busco una moto de 125 de segunda mano por menos de 2.500 €, cerca de Valencia capital",
    "search-buy-used-car__es": "Búscame un coche de segunda mano diésel en Madrid y alrededores, que no pase de 12 mil euros",
    "search-buy-used-car__en": "Find me a used car, diesel or hybrid, under 60k miles and under $14,000",
    "weekend-barber-availability__es": "Busca una peluquería en Malasaña o el centro de Madrid con hueco este finde",
}


def _context(d: dict) -> list:
    crit = d.get("criteria") or {}
    return [d.get("title"), crit.get("goal")] + list(crit.get("changes") or []) + list(crit.get("hard") or [])


@pytest.mark.parametrize("path", CLEAN)
def test_the_sheet_alone_rules_out_no_row(path):
    d = json.loads((SHEETS / path).read_text(encoding="utf-8"))
    assert row_fit.split(d.get("items") or [], "", _context(d))[1] == []


@pytest.mark.parametrize("path", [p for p in CLEAN if p.split("__results")[0] in ASKS])
def test_the_measured_ask_rules_out_no_row(path):
    d = json.loads((SHEETS / path).read_text(encoding="utf-8"))
    on, off = row_fit.split(d.get("items") or [], ASKS[path.split("__results")[0]], _context(d))
    assert [o for o in off if "ceiling" in o["why"] or ", not " in o["why"]] == [], off
