"""A candidate a search ANSWER names whole — a name, ONE amount and a link its citations back — reaches the errand's
sheet as a row, beside the citation rows (node 2.662).

search-buy-boat-multicountry ES (2026-10-14, sandbox 093838-es): the worker's search answered «1. **Lagoon 440 de
2009** - **Precio**: 299.000 € - **Ubicación**: Sitges … - **Enlace**: ([yachtworld.es](…))», and only the two
citation rows — listing INDEX pages — reached the sheet: `findings.hand_search_rows` read `results` alone. The
candidate stayed in the errand's «latest lead», which the turn is told is not a candidate, and his «me los pasas
cuando tengas los enlaces y años» got a step instead of the boat.
"""
from __future__ import annotations

from types import SimpleNamespace

from nucleo.workers import answer_rows, findings
from widgets.results import data as sheet_data

SHEET = "boat01-ls1"
REC = SimpleNamespace(sheet=SHEET, surface="lista", task_id="boat01", goal="Lagoon 440")
ANSWER = ("He encontrado varios catamaranes Lagoon 440 usados en venta por menos de 300.000 euros en España, Francia "
          "e Italia. A continuación, se detallan algunos de ellos:\n\n"
          "1. **Lagoon 440 de 2009**\n   - **Precio**: 299.000 €\n   - **Ubicación**: Sitges, Barcelona, España\n"
          "   - **Enlace**: ([yachtworld.es](https://www.yachtworld.es/barcos/2009-lagoon-440-8812345/))\n\n"
          "2. **Lagoon 440 de 2007** - **Precio**: 265.000 € - **Ubicación**: La Rochelle, Francia - **Enlace**: "
          "[bandofboats.com](https://www.bandofboats.com/es/barcos-en-venta/181889)\n\n"
          "También puedes mirar en [YachtWorld](https://www.yachtworld.es/).")
RESULTS = [{"title": "Barcos Lagoon 440 en venta en España | YachtWorld",
            "url": "https://www.yachtworld.es/barcos-en-venta/lagoon/440/"},
           {"title": "Lagoon 440 Barcos segunda mano", "url": "https://www.bandofboats.com/es/lagoon-440"}]


def test_the_answers_candidates_land_on_the_errands_sheet():
    res = {"query": "Lagoon 440 en venta", "answer": ANSWER, "results": RESULTS, "source": "openai"}
    findings.hand_search_rows(REC, res)
    items = sheet_data.view_data(SHEET).get("items") or []
    got = {i["title"]: i for i in items}
    assert "Lagoon 440 de 2009" in got, [i["title"] for i in items]
    row = got["Lagoon 440 de 2009"]
    assert row.get("price") == "299.000 €" and row.get("url", "").endswith("2009-lagoon-440-8812345/"), row
    assert "Sitges" in row.get("subtitle", ""), row
    assert "Lagoon 440 de 2007" in got, "the second item, written on one line, is a row too"


def test_an_item_the_answer_does_not_name_whole_is_no_row():
    two_amounts = "1. **Lagoon 440** - **Precio**: antes 320.000 €, ahora 299.000 € - [x](https://www.yachtworld.es/a)"
    no_link = "1. **Lagoon 440 de 2010** - **Precio**: 289.000 € - **Ubicación**: Palma"
    assert answer_rows.rows_of({"answer": two_amounts, "results": RESULTS}) == []
    assert answer_rows.rows_of({"answer": no_link, "results": RESULTS}) == []


def test_a_link_no_citation_backs_is_the_models_and_is_no_row():
    made_up = "1. **Lagoon 440 de 2008** - **Precio**: 280.000 € - [anuncio](https://www.barcos-inventados.example/1)"
    assert answer_rows.rows_of({"answer": made_up, "results": RESULTS}) == []
    assert answer_rows.rows_of({"answer": made_up, "results": []}), "with no citations the answer's link is all there is"
