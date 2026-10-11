"""A row zaelar NAMED is never denied when he quotes it back (V2-782) — search-buy-used-car ES, 2026-10-11.

The backstop said «Peugeot 3008 — € 7.999»; the next reply was «¿De dónde te sale el Peugeot 3008? no lo tienes», then
«no aparece en la hoja de resultados». The repair reads the window (what WE said) and every sheet (where the row is
now): named, and still there / discarded / gone — never «it does not exist».
"""
from __future__ import annotations

import pytest

from nucleo.flash import delivery, own_words
from widgets.results import data as sheet

NAMED = ("Voy a mirar los detalles. Bueno, de hecho ya hay candidatos en la hoja de resultados: «Peugeot 3008 — € 7.999». "
         "Dime si alguno te encaja o sigo afinando.")
HEARD = "¿Y el Peugeot 3008 qué año y kilometraje tiene? Es diésel, ¿no?"
WINDOW = [{"role": "user", "content": "dime año y km"}, {"role": "assistant", "content": NAMED},
          {"role": "user", "content": HEARD}]


@pytest.fixture(autouse=True)
def _spanish(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    for sid in ("t2513a", "t2513b", "t2513c"):                # each test sees only its own sheet
        sheet.store.save(sheet.sheet_key(sid), {"title": "Resultados", "items": []})


def test_still_on_the_sheet_it_is_named_and_its_listing_read():
    sheet.store.save(sheet.sheet_key("t2513a"), {"title": "Coches", "items": [
        {"title": "Peugeot 3008", "price": "€ 7.999", "subtitle": "2016 · 120.000 km · diésel"}]})
    out = own_words.keep_its_word("¿De dónde te sale el Peugeot 3008? no lo tienes.", WINDOW, HEARD)
    assert out.startswith("Sí, te lo nombré yo: «Peugeot 3008 — € 7.999».")
    assert "Sigue en la hoja" in out and "120.000 km" in out
    assert "no lo tienes" not in out and "De dónde" not in out


def test_discarded_it_says_it_discarded_it_and_why():
    sheet.store.save(sheet.sheet_key("t2513b"), {"title": "Coches", "items": [], "rejected": [
        {"title": "Peugeot 3008", "why": "tenía más de 200.000 km"}]})
    out = own_words.keep_its_word("Perdona, pero ese Peugeot 3008 no aparece en la hoja de resultados.", WINDOW, HEARD)
    assert "te lo nombré yo" in out and "Después lo descarté: tenía más de 200.000 km." in out
    assert "no aparece" not in out


def test_gone_from_every_sheet_it_says_the_list_was_redone():
    out = own_words.keep_its_word("Ese coche no existe.", WINDOW, HEARD)
    assert "te lo nombré yo" in out and "rehízo la lista" in out


def test_a_denial_of_something_it_never_named_is_left_alone():
    out = own_words.keep_its_word("No tengo ningún Audi Q5 en la hoja: no aparece.", WINDOW, "¿y el Audi Q5?")
    assert out == "No tengo ningún Audi Q5 en la hoja: no aparece."


def test_the_text_channel_runs_it(monkeypatch):
    sheet.store.save(sheet.sheet_key("t2513c"), {"title": "Coches", "items": [{"title": "Peugeot 3008", "price": "€ 7.999"}]})
    out = delivery.apply_to_reply("¿De dónde te sale el Peugeot 3008? no lo tienes.", WINDOW, heard_now=HEARD)
    assert "te lo nombré yo" in out and "no lo tienes" not in out
