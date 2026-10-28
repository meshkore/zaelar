"""A row he NAMED is named by a word only that row carries — never by the category or a spec he asked for (node 2.601).

cheapest-monitor EN (2026-10-14, sandbox 010127-en). He said «my work monitor is dying» and «27-inch, 4K». The
delivery backstop skipped «a row he named» by SUBSTRING over everything he had said, so «monitor» and «27» made
«Monitor AGEX 27 pulgadas 4K UHD — 179.99» and «LG 27UD68 27" IPS LED 4K UHD — 20.6» his; the only rows ever offered
were three power adapters, and «any news?» turns ended «no usable monitors yet» with both monitors in the prompt.
best-plumber-same-day ES (sandbox 010939-es): «fontanero», «Madrid» and «24» («24h») did the same to all three
plumbers.
"""
from __future__ import annotations

import pytest

from nucleo.flash import delivery, live_blocks, row_named

MONITORS = ["Monitor AGEX 27 pulgadas 4K UHD… — 179.99", "Nuevo Adaptador de CA Monitor… — 170",
            'LG 27UD68 27" IPS LED 4K UHD… — 20.6', "Adaptador 19V para LG 27UK650-W… — 17.91",
            "19.5v3.3a Adapter for LG… — 26.35"]
HIS_MONITOR = ["Hey, my work monitor is dying and I need a new one… something decent without spending a fortune",
               "27-inch, 4K, and new only — I don't want someone else's panel. Budget is up to $250"]
PLUMBERS = ["FONTANEROS URGENCIAS 24 HORAS… — 652 66 18 46", "Fontanero Urgencia Madrid — 683 13 98 19",
            "Fontaneros Madrid 24h 🧰 — 910 05 95 22"]
HIS_PLUMBER = ["Tengo una fuga en el baño y necesito un fontanero hoy sí o sí… uno que esté bien valorado porfa",
               "Madrid centro", "Vale, gracias por la sinceridad. Llamo yo a un 24h y listo. Gracias."]


def _window(user_lines):
    return [{"role": "user", "content": t} for t in user_lines]


@pytest.fixture
def sheet(monkeypatch):
    def _set(errand, rows, en):
        monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (errand, list(rows)[:n]))
        monkeypatch.setattr(delivery, "_speaks_en", lambda: en)
        delivery.forget_announced()
    return _set


def test_the_category_and_a_size_he_said_do_not_name_a_monitor():
    assert not row_named.by_him(" ".join(HIS_MONITOR), MONITORS[0], MONITORS, "27-inch, 4K, and new only")
    assert not row_named.by_him(" ".join(HIS_MONITOR), MONITORS[2], MONITORS, "27-inch, 4K, and new only")
    assert row_named.by_him("what about the AGEX pulgadas one?", MONITORS[0], MONITORS, "")
    assert row_named.by_him("is the 27UD68 any good?", MONITORS[2], MONITORS, ""), "a model code names its row"
