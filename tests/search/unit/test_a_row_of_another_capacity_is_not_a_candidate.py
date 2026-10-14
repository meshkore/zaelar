"""A row whose stated capacity is not the one he asked is not a candidate (node 2.696).

«Una lavadora de 8 kg», «a 4.5 cu ft washer». Said bare, the capacity is what he needs: a smaller row is off and so
is one over 1.3 times it, a 9 kg row stays. A floor («al menos 8 kg») rules out only smaller rows, a cap («hasta
8 kg») only bigger ones. Weight and dryer facts are other numbers, and so is anything outside half to double.
"""
from __future__ import annotations

from search import measure_fit, row_fit


def test_a_bare_capacity_rules_out_smaller_and_much_bigger_rows():
    rows = [{"title": f"Lavadora Bosch Serie 4 {k}"} for k in ("7 kg", "8 kg", "9 kg", "11 kg", "8/5 kg")]
    on, off = row_fit.split(rows, "Busco una lavadora de 8 kg", [])
    assert sorted(o["title"][-5:].strip() for o in off) == ["11 kg", "7 kg"]
    assert len(on) == 3


def test_a_floor_and_a_cap_are_one_sided():
    floor = measure_fit.asked_measures("lavadora de al menos 8 kg")
    assert measure_fit.why_off({"title": "LG 7 kg"}, floor) and not measure_fit.why_off({"title": "LG 12 kg"}, floor)
    cap = measure_fit.asked_measures("lavadora de hasta 8 kg")
    assert measure_fit.why_off({"title": "LG 10 kg"}, cap) and not measure_fit.why_off({"title": "LG 6 kg"}, cap)


def test_other_quantities_of_the_same_unit_are_not_its_capacity():
    ask = measure_fit.asked_measures("a 4.5 cu ft front load washer")
    assert measure_fit.why_off({"title": "Whirlpool 3.5 cu. ft. Top Load"}, ask)
    assert not measure_fit.why_off({"title": "LG WM4000HWA 4.5 cu. ft."}, ask)
    kg = measure_fit.asked_measures("lavadora de 8 kg")
    assert not measure_fit.why_off({"title": "Balay 3TS", "facts": [{"label": "Peso", "value": "7 kg"}]}, kg)
    assert not measure_fit.why_off({"title": "Balay 3TS de 70 kg"}, kg)        # outside half..double: not a load
    assert measure_fit.asked_measures("Find me a used car under 60k miles") == {}
