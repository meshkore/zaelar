"""The reply-language gate reads a «quoted» span as a NAME, not as the language the reply speaks (node 2.704).

search-buy-vinyl ES (2026-10-14): «Hecho, se lo paso a «Comprar vinilo The Dark Side of the Moon».» was filed as an
English reply — «The», «of», «the» outvoted the Spanish around them. His errand's name, an album title, is quoted by
every line of ours that names it; the gate now leaves quoted spans out of its count.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent.gates import reply_language


def test_a_spanish_line_quoting_an_english_title_is_spanish_or_undecided():
    assert reply_language("Hecho, se lo paso a «Comprar vinilo The Dark Side of the Moon».", "es") in ("es", "")
    assert reply_language("Así va todo: «Comprar vinilo The Dark Side of the Moon» — en marcha, sin novedades "
                          "todavía.", "es") in ("es", "")


def test_an_english_reply_is_still_english():
    assert reply_language("I've passed that on to the search and I will tell you what it finds.", "es") == "en"
