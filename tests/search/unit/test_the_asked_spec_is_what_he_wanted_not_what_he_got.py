"""The value a family is judged against is the one he WANTED, never the one he complains he got (node 2.694).

search-buy-tv ES (2026-10-14): his correction «Oye, que yo pedí OLED — esos no me valen. El Philips y el Xiaomi son
LED normales, y el LG encima es QNED» joins the sheet's `asked`. Read as a bag of values it would ask for OLED, LED
and QNED alike and rule nothing out — which is how «LG 55QNED70B6C» came back twice. The asked value is the FIRST
one not ruled out, plus any tied to it («diésel o híbrido») or wanted in so many words; his words come before the
sheet's title and criteria.
"""
from __future__ import annotations

from search import spec_fit

CORRECTED = ("Búscame una tele OLED de 55 pulgadas por menos de 900 euros. Oye, que yo pedí OLED — esos no me valen. "
             "El Philips y el Xiaomi son LED normales, y el LG encima es QNED, no me sirve")


def test_a_complaint_naming_what_he_got_never_becomes_the_ask():
    assert spec_fit.asked_specs(CORRECTED) == {"panel": {"OLED"}}
    assert spec_fit.why_off({"title": "LG 55QNED70B6C"}, spec_fit.asked_specs(CORRECTED))


def test_a_ruled_out_value_is_never_asked_and_a_tied_one_is():
    assert spec_fit.asked_specs("una tele, no QLED ni LED, que sea OLED") == {"panel": {"OLED"}}
    assert spec_fit.asked_specs("Find me a used car, diesel or hybrid, under $14,000") == {
        "fuel": {"diesel", "hybrid"}}
    assert spec_fit.asked_specs("una tele OLED; también me vale un QLED") == {"panel": {"OLED", "QLED"}}


def test_his_words_come_before_the_sheet_and_the_sheet_speaks_when_he_is_silent():
    ctx = ["Buscar tele QLED 55\""]
    assert spec_fit.asked_specs("una tele OLED de 55", ctx) == {"panel": {"OLED"}}
    assert spec_fit.asked_specs("una tele de 55", ctx) == {"panel": {"QLED"}}
    assert spec_fit.asked_specs("", ["Relayed: descarta el cuarzo, solo reloj automático"]) == {
        "movement": {"automatic"}}
