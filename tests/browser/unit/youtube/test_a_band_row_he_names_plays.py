"""Node 2.593 — a row of the search band he names by title or channel PLAYS (`find-videos-on-a-topic-no-ai-slop`, EN).

«play the Palm Centre one first», twice: the model called `play_item {item: "How to Prune an Olive Tree — The Palm
Centre"}` over an empty queue, `play_item` handed it to `play_result`, which read only a number — and he heard «Solo
hay 6 resultados.» Nothing ever played. Now the band row resolves by number, exact title or the words of its title
and channel (`widgets/youtube/result_refs.py`); two rows carrying his words are refused, never guessed.

Disarm: `result_refs.resolve` reading digits only → every named-row test goes red.
"""
from __future__ import annotations

from ._band import EN, card, seed, vid  # noqa: F401 — `card` is the fixture


def test_the_title_and_channel_the_model_wrote_plays_that_row(card):  # noqa: F811
    seed(EN)
    r = card.apply_action("play_item", {"item": "How to Prune an Olive Tree — The Palm Centre"})
    assert r.get("ok") is not False, r
    assert card.view_data()["videoId"] == vid(5)


def test_his_own_words_for_it_play_it_too(card):  # noqa: F811
    seed(EN)
    assert card.apply_action("play_result", {"item": "the Palm Centre one"}).get("ok") is not False
    assert card.view_data()["videoId"] == vid(5)


def test_a_named_band_row_plays_even_with_other_videos_queued(card):  # noqa: F811
    seed(EN, queue=(1, 2))
    assert card.apply_action("play_item", {"item": "ColtivoBio"}).get("ok") is not False
    assert card.view_data()["videoId"] == vid(4), "not in the queue, but on the band he is looking at"


def test_a_number_still_means_the_row_and_words_on_two_rows_are_refused(card):  # noqa: F811
    seed(EN)
    assert card.apply_action("play_result", {"item": "9"})["error"] == "bad_index"
    r = card.apply_action("play_result", {"item": "olive tree"})       # rows 1, 5 and 6 all carry it
    assert r["ok"] is False and r["error"] == "item_not_found"
    assert not card.view_data().get("videoId"), "an ambiguity never plays a guess"
