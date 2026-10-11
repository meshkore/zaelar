"""A size he states as a MINIMUM is a floor, not an exact size (node 2.554).

three-tasks-at-once (ES/EN, 2026-10-11 11:34). «el monitor, que sea de 27 al menos» and «has to be at least 27
inches»; the delivered shortlist opened with an LG 24", a BenQ 24" and an Asus 23,8". `asked.size_inches` needs a
unit, so «27 al menos» was no size at all; and with a unit the gate read an EXACT size, so a 32" would have left the
list for a «27 or bigger» ask. `search/asked_size.size_floor` reads the floor; `search/category` rejects a row under
it and keeps one over it.
"""
from __future__ import annotations

import pytest

from search import category
from search.asked_size import size_floor


@pytest.mark.parametrize("said,floor", [
    ("Y el monitor, que sea de 27 al menos, que con", 27),
    ("monitor has to be at least 27 inches, and no more than $150", 27),
    ("te pedí mínimo 27", 27),
    ("me has dicho que el monitor era de 27 o más", 27),
    ('27" or bigger please', 27),
    ("a 27+ monitor", 27),
    ("al menos 150 €", None),          # a price, not a size
    ("hasta 150, no quiero pasarme", None),
    ("monitor de 27 pulgadas", None),   # a size, not a minimum
])
def test_the_floor_is_read_off_the_shape_of_the_sentence(said, floor):
    assert size_floor(said) == floor


ASK = "Y el monitor, que sea de 27 al menos"
ROWS = {'LG UltraGear 24" IPS 144Hz': False, 'Asus VA24DQ 23,8" IPS 75Hz': False,
        'Fujitsu P27-8 TE Pro 27" QHD': True, 'Samsung Odyssey G5 32" curvo': True, "Monitor Dell sin medida": True}


def test_a_row_under_the_floor_is_off_and_one_over_it_is_a_candidate():
    on, off = category.split([{"title": t} for t in ROWS], ASK)
    assert {r["title"] for r in on} == {t for t, keep in ROWS.items() if keep}
    assert all("minimum" in r["why"] for r in off), off


def test_an_exact_size_still_reads_as_exact():
    on, off = category.split([{"title": 'Samsung 32"'}, {"title": 'Samsung 27"'}], "un monitor de 27 pulgadas")
    assert [r["title"] for r in on] == ['Samsung 27"'] and off[0]["title"] == 'Samsung 32"'
