"""The close BACKSTOP reads his close words, never a card he told to stay (2026-10-14).

`post_stream_lanes` (and the old text channel's mirror) completed a close the model did not make with
`runtime.identify` over the WHOLE sentence: «close the video, I'll check the calendar later» matched `agenda`
outright. `close_target.identify` (ex `close_identify`) reads `naming.without_kept` and drops a kept match; the backstop calls it.
"""
from __future__ import annotations


import pytest

from nucleo.acts import close_target as close_identify

THREE = ["agenda", "musica", "youtube"]


@pytest.mark.parametrize("text", [
    "close the video, I'll check the calendar later",
    "Perfecto, cierra el vídeo y deja la música sonando de fondo, porfa. La agenda la miro luego.",
    "cierra el vídeo, la agenda déjala",
])
def test_the_backstop_reaches_the_video_not_the_kept_card(text):
    assert close_identify.identify(text, THREE).get("match") == "youtube"


def test_a_sentence_that_only_names_the_kept_card_reaches_nothing():
    assert not close_identify.identify("ciérralo, la agenda la miro luego", THREE).get("match")


def test_a_plain_close_still_reaches_its_card():
    assert close_identify.identify("cierra la agenda", THREE).get("match") == "agenda"
