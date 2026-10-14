"""No row of a clean recorded sheet is lost to the spec gates — page chrome, a contradicted spec, another capacity,
a second copy — judged with the sheet alone and with the ask its scenario was measured on (node 2.699, the
false-positive golden).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from search import spec_gates

SHEETS = Path(__file__).resolve().parents[1] / "fixtures" / "sheets"
CLEAN = sorted(p.name for p in SHEETS.glob("*.json") if not p.stem.endswith(("-junk", "-mixed", "-offsubject")))
#: The ask each scenario was measured on, with every spec family it can carry stated.
ASKS = {
    "cheapest-monitor__es": "Busco un monitor IPS de 27 pulgadas 4K para trabajar, uno solo, por debajo de 300 €",
    "cheapest-monitor__en": "Find me the cheapest decent LED monitor for work, a single one, under €350",
    "search-buy-motorcycle__es": "Busco una moto de 125 de gasolina, de segunda mano, por menos de 2.500 €",
    "search-buy-used-car__es": "Búscame un coche de segunda mano diésel en Madrid, que no pase de 12 mil euros",
    "search-buy-used-car__en": "Find me a used car, diesel or hybrid, automatic, under 60k miles and under $14,000",
    "hotel-under-15-days__en": "A 4-star hotel in San Diego for Oct 16-20, a single room, under $400 a night",
}


def _context(d: dict) -> list:
    crit = d.get("criteria") or {}
    return [d.get("title"), crit.get("goal")] + list(crit.get("changes") or []) + list(crit.get("hard") or [])


@pytest.mark.parametrize("path", CLEAN)
def test_the_sheet_alone_rules_out_no_row(path):
    d = json.loads((SHEETS / path).read_text(encoding="utf-8"))
    assert spec_gates.split(list(d.get("items") or []), [], "", _context(d))[1] == []


@pytest.mark.parametrize("path", [p for p in CLEAN if p.split("__results")[0] in ASKS])
def test_the_measured_ask_rules_out_no_row(path):
    d = json.loads((SHEETS / path).read_text(encoding="utf-8"))
    off = spec_gates.split(list(d.get("items") or []), [], ASKS[path.split("__results")[0]], _context(d))[1]
    assert off == [], off
