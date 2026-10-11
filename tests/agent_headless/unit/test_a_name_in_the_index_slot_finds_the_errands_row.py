"""A row named in the INDEX slot is found on the errand's sheet when the base sheet has none (V2-782).

search-buy-used-car ES (2026-10-11): «dime año y kilometraje de los tres» → `detail {"index": "Fiat Tipo"}` with no sheet,
against the EMPTY base sheet. The cross-sheet fallback (demo pass 107) only read `title`/`item`/`name`, so it never ran,
the reply said «No encuentro ese resultado en la hoja», and the next turn denied the row existed.
"""
from __future__ import annotations

from widgets.results import data as sheet


def test_detail_by_a_name_in_the_index_slot_reaches_the_instance(monkeypatch):
    monkeypatch.setattr(sheet, "sheets", lambda: ["", "t2517"])     # the sheets on disk are other tests' business
    sheet.store.save(sheet.sheet_key(""), {"title": "Coches completos", "items": []})
    sheet.store.save(sheet.sheet_key("t2517"), {"title": "Coches", "items": [{"title": "Fiat Tipo Lounge 2517", "price": "€ 10.490"}]})
    res = sheet.apply_action("detail", {"index": "Fiat Tipo Lounge 2517"})
    assert res.get("ok") and res.get("detail") == "Fiat Tipo Lounge 2517"


def test_a_numeric_index_stays_an_ordinal_of_the_sheet_it_targets():
    sheet.store.save(sheet.sheet_key(""), {"title": "Coches completos", "items": []})
    assert not sheet.apply_action("detail", {"index": "1"}).get("ok")
