"""A row whose title or facts name ANOTHER value of an attribute he stated is not a candidate (node 2.693).

search-buy-tv ES (2026-10-14): «una tele OLED de 55 pulgadas» → «LG 65QNED70B6C», «PHILIPS 55MLED920», then
«LG 55QNED70B6C» after his correction. search-buy-watch ES: «un Seiko automático» → «Majesta HAQ» (quartz) and
«Seiko Solar». A row silent on the attribute stays, and so does one that also names the asked value. A family whose
words other domains share («automático», «eléctrico») applies only when the request names its domain.
"""
from __future__ import annotations

from search import row_fit, spec_fit

TV = "Búscame una tele OLED de 55 pulgadas por menos de 900 euros."
WATCH = "Búscame un Seiko automático vintage por menos de 400 euros."


def _titles(rows):
    return sorted(r["title"] for r in rows)


def test_a_tv_of_another_panel_is_off_and_an_oled_or_a_silent_row_stays():
    rows = [{"title": t, "price": "549 €"} for t in (
        "LG 55QNED70B6C - Smart TV QNED", "PHILIPS Ambilight 55MLED920 'The Xtra'", "Samsung Neo QLED QE55QN90D",
        "Xiaomi TV A Pro 55 LED 4K", "Philips 55OLED801 Ambilight", "LG OLED55C54LA", "Sony Bravia 8 55\"")]
    on, off = row_fit.split(rows, TV, [])
    assert _titles(off) == _titles(rows[:4])
    assert _titles(on) == _titles(rows[4:])
    assert all("not OLED" in o["why"] for o in off)


def test_a_fact_can_contradict_and_a_row_naming_both_stays():
    specs = spec_fit.asked_specs(TV)
    assert spec_fit.why_off({"title": "Hisense 55U7", "facts": [{"label": "Panel", "value": "Mini-LED"}]}, specs)
    assert not spec_fit.why_off({"title": "OLED vs QNED: LG 55C4 OLED", "facts": []}, specs)


def test_a_watch_of_another_movement_is_off():
    rows = [{"title": t} for t in ("Seiko 9533-5000 Majesta HAQ Seiko", "Seiko Solar Exc+5 Vintage SEIKO",
                                   "Seiko Kinetic 5M62", "Seiko 5 Automatic 6309-7040", "Seiko NEAR MINT Vintage")]
    on, off = row_fit.split(rows, WATCH, [])
    assert _titles(off) == _titles(rows[:3])
    assert all("not automatic" in o["why"] for o in off)


def test_a_guitar_a_fuel_and_a_gearbox_read_the_same_way():
    guitar = spec_fit.asked_specs("Busco una guitarra acústica para empezar")
    assert spec_fit.why_off({"title": "Fender Squier Stratocaster guitarra eléctrica"}, guitar)
    assert not spec_fit.why_off({"title": "Yamaha APX600 electroacústica"}, guitar)
    car = spec_fit.asked_specs("Búscame un coche diésel automático de segunda mano")
    assert spec_fit.why_off({"title": "Seat León 1.5 TSI gasolina"}, car)
    assert spec_fit.why_off({"title": "Golf 2.0 TDI", "facts": [{"label": "Cambio", "value": "Manual"}]}, car)
    assert not spec_fit.why_off({"title": "Golf 2.0 TDI DSG"}, car)


def test_a_family_outside_its_domain_asks_nothing():
    assert "transmission" not in spec_fit.asked_specs(WATCH)            # a watch's «automático» is no gearbox
    assert "movement" not in spec_fit.asked_specs("Un coche automático")
    assert spec_fit.asked_specs("Una bombilla LED para el salón") == {}  # no screen asked: LED is not a panel
    assert row_fit.split([{"title": "Philips Hue LED bulb"}], "Una lámpara de pie", [])[1] == []


def test_a_value_that_is_another_one_too_serves_it():
    led = spec_fit.asked_specs("Find me the cheapest decent LED monitor for work")
    assert not spec_fit.why_off({"title": 'AOC Q27G3XMN 27" mini-LED'}, led)    # a Mini-LED panel IS LED-lit
    assert spec_fit.why_off({"title": "LG 27GS95QE OLED"}, led)
    assert spec_fit.why_off({"title": 'AOC Q27G3XMN 27" mini-LED'}, spec_fit.asked_specs(TV))
