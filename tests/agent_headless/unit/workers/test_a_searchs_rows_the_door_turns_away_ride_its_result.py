"""A worker's `web_search` result carries what the sheet's door did with the rows it brought: how many landed, and
which were turned away and why (node 2.664).

Same gap as the browser extraction (node 2.663), on the other door: `findings.hand_search_rows` pushed the search's
rows to the errand's sheet and returned a count nobody read, so a worker whose rows were all filed in Rejected
reported them as delivered. The verdict now rides the result dict the worker reads back.
"""
from __future__ import annotations

from types import SimpleNamespace

from nucleo.workers import findings
from widgets.results import category_gate

SHEET = "boat03-ls1"
REC = SimpleNamespace(sheet=SHEET, surface="lista", task_id="boat03", goal="Lagoon 440")
ASKED = "Búscame un catamarán Lagoon 440 de segunda mano por menos de 300.000 euros."


def test_the_turned_away_rows_ride_the_workers_result():
    category_gate.hear(SHEET, ASKED)
    res = {"query": "q", "source": "openai", "answer": "",
           "results": [{"title": "Lagoon 440 de 2009 en venta — 299.000 €", "url": "https://www.boat24.com/es/d/1/"},
                       {"title": "Bavaria 46 Cruiser en venta — 120.000 €", "url": "https://www.boat24.com/es/d/2/"}]}
    findings.hand_search_rows(REC, res)
    door = res.get("door") or {}
    assert door.get("handed") == 2 and door.get("landed") == 1, door
    assert "Bavaria 46" in door.get("note", ""), door


def test_a_search_whose_rows_all_landed_leaves_the_result_as_it_was():
    res = {"query": "q", "source": "openai", "answer": "",
           "results": [{"title": "Lagoon 440 de 2011 en venta — 289.000 €", "url": "https://www.boat24.com/es/d/3/"}]}
    category_gate.hear("boat04-ls1", ASKED)
    findings.hand_search_rows(SimpleNamespace(sheet="boat04-ls1", surface="lista"), res)
    assert "door" not in res, res
