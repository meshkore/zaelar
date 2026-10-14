"""He asked for ONE item: a row that is a pack, a lot or a set of N is not a candidate (node 2.695).

search-buy-watch ES (2026-10-14): «yo había pedido un solo Seiko, no un pack de dos» after «Pack 2 Relojes Seiko
Automáticos — 130» was offered. «Uno solo / a single / no un pack» asks for one, «pack de 2 / 2-pack» for that many;
a row that states another count is off, a row that states none stays, and an ask that says neither judges nothing.
"""
from __future__ import annotations

from search import row_fit, spec_fit

ONE = "Búscame un Seiko automático vintage por menos de 400 euros. Perdona, yo había pedido un solo Seiko, no un pack de dos."


def test_a_pack_is_off_when_he_asked_for_one():
    rows = [{"title": t} for t in ("Pack 2 Relojes Seiko Automáticos", "Lote de relojes Seiko automáticos",
                                   "Seiko 5 automatic 3-pack", "Seiko 5 Automatic 6309-7040")]
    on, off = row_fit.split(rows, ONE, [])
    assert [r["title"] for r in on] == ["Seiko 5 Automatic 6309-7040"]
    assert all("not one, which he asked" in o["why"] for o in off)


def test_a_counted_ask_rules_out_another_count_only():
    specs = spec_fit.asked_specs("I need a 2-pack of Casio F91W watches")
    assert specs.get("count") == 2
    assert spec_fit.why_off({"title": "Casio F91W 3-pack"}, specs)
    assert not spec_fit.why_off({"title": "Casio F91W pack of 2"}, specs)
    assert not spec_fit.why_off({"title": "Casio F91W"}, specs)


def test_no_count_asked_judges_no_pack():
    assert "count" not in spec_fit.asked_specs("Búscame un Seiko automático vintage")
    assert row_fit.split([{"title": "Pack 2 Relojes Seiko"}], "relojes Seiko baratos", [])[1] == []
