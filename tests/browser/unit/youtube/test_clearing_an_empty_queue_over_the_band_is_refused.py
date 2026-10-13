"""Node 2.595 — `clear_list` over an EMPTY queue with the band on screen is refused, naming the band's writes.

`find-videos-on-a-topic-no-ai-slop` (ES, 2026-10-14): «Ponme el de Iván, el de José Manuel y el de Jaén» reached
`clear_list`; the empty queue stayed empty, the card said `ok`, and «Hecho.» was said twice over three videos that
were never added. The refusal is true and declares `redirect` = the two actions that act on the band, which the
same-turn redirect (`nucleo/flash/refusal_redirect.py`, node 2.596) may run instead.

Disarm: drop the empty-queue check in `_a_clear_list` → the first test goes red.
"""
from __future__ import annotations

from ._band import ES, card, seed  # noqa: F401 — `card` is the fixture


def test_clearing_nothing_with_results_on_screen_is_a_refusal_with_a_redirect(card):  # noqa: F811
    seed(ES)
    r = card.apply_action("clear_list", {})
    assert r["ok"] is False and r["error"] == "queue_empty", r
    assert r["redirect"] == ["add_results", "play_result"]
    assert str(r.get("message") or "").strip(), "the refusal is a sentence he can hear"


def test_a_queue_with_videos_is_still_emptied(card):  # noqa: F811
    seed(ES, queue=(1, 2))
    r = card.apply_action("clear_list", {})
    assert r["ok"] is True and card.view_data()["list"] == []


def test_without_a_band_an_empty_queue_is_left_as_today(card):  # noqa: F811
    seed([])
    assert card.apply_action("clear_list", {})["ok"] is True
