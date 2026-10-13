"""Node 2.594 — the band rows he NAMES reach the queue, by name, without a fresh search (2026-10-14, ES+EN).

«Ponme el de Iván, el de José Manuel y el de Jaén» over six numbered results: `add_results` read numbers only, so the
names had no way in; and EN `add {url: "Cómo podar un olivo… — ColtivoBio"}` sent a row on screen to a network search.

Disarm: `result_refs.indices` without names, or `_a_add` without the band lookup → red.
"""
from __future__ import annotations

from ._band import EN, ES, card, seed, vid  # noqa: F401 — `card` is the fixture


def test_three_names_queue_those_three_in_his_order(card):  # noqa: F811
    seed(ES)
    r = card.apply_action("add_results", {"items": "Iván, José Manuel y Jaén"})
    assert r["ok"], r
    assert [it["videoId"] for it in card.view_data()["list"]] == [vid(5), vid(3), vid(1)]


def test_a_name_that_matches_no_row_adds_nothing(card):  # noqa: F811
    seed(ES)
    r = card.apply_action("add_results", {"items": "Iván, Rodrigo"})
    assert r["ok"] is False and not card.view_data()["list"], "a partial add would be «Hecho» over less than he said"


def test_numbers_and_all_keep_working(card):  # noqa: F811
    seed(ES)
    assert card.apply_action("add_results", {"items": "1 3"})["added"] and len(card.view_data()["list"]) == 2
    card.apply_action("add_results", {"items": "all"})
    assert len(card.view_data()["list"]) == 6


def test_an_add_by_the_title_of_a_row_on_screen_adds_that_row(card):  # noqa: F811
    seed(EN)
    r = card.apply_action("add", {"url": "Cómo podar un olivo: la guía profesional completa — ColtivoBio"})
    assert r["ok"], r
    assert [it["videoId"] for it in card.view_data()["list"]] == [vid(4)]
