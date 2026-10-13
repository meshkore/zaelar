"""A clause that puts looking at a card off until LATER keeps that card (`tres-tarjetas-y-el-video-por-alusion`, ES,
report 2026-10-14 00:37, t6).

Agenda, music and the trailer open: «Perfecto, cierra el vídeo y deja la música sonando de fondo, porfa. La agenda la
miro luego.» closed the AGENDA. `naming.split_kept` knew keep / leave / don't-touch / except, not «la miro luego», so
the only card the close words named by its catalogue name was the deferred one. `widgets.later_clause` is the reader.
"""
from __future__ import annotations

import pytest

from widgets import later_clause, naming

T6 = "Perfecto, cierra el vídeo y deja la música sonando de fondo, porfa. La agenda la miro luego."


@pytest.mark.parametrize("text, kept", [
    (T6, "La agenda la miro luego"),
    ("cierra el vídeo, la agenda ya la veré después", "la agenda ya la veré después"),
    ("cierra el vídeo y la agenda luego la miro", "la agenda luego la miro"),
    ("close the video, I'll check the calendar later", "I'll check the calendar later"),
    ("close the video and I'll look at the calendar in a bit", "I'll look at the calendar in a bit"),
])
def test_a_deferral_is_split_out_of_the_close_words(text, kept):
    close_words, kept_words = naming.split_kept(text)
    assert kept in kept_words and kept not in close_words
    assert ("vídeo" in close_words) or ("video" in close_words)


@pytest.mark.parametrize("text", [
    "Cierra la agenda, luego la miro",          # the close is its own clause: «luego la miro» names no card
    "cierra la agenda y luego el vídeo",        # «luego» = then: two closes, no look verb
    "close the calendar later",                 # a later close is still a close
    "mira la agenda",                           # a look with no «later» defers nothing
])
def test_a_close_or_a_plain_look_is_never_a_deferral(text):
    close_words, _ = naming.split_kept(text)
    assert ("agenda" in close_words) or ("calendar" in close_words)
    assert not any("agenda" in p or "calendar" in p for p in later_clause.split_deferred(text)[1])


def test_the_deferred_card_is_a_kept_card():
    from widgets import instances
    assert instances.kept_named(T6, ["agenda", "musica", "youtube"]) == ["agenda", "musica"]
