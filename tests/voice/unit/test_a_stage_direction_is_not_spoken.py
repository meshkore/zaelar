"""A stage direction the model writes is not read out loud — in any language (demo pass 2026-09-28, C5b).

«Tidying up — [spreading them out now].» went to the speaker brackets and all. The speech gate drops a
single-bracketed aside and the dash it leaves; a markdown link keeps its words and `[[aparte]]` stays a tag for
the code that reads it. And a reply in a script without Latin letters is still prose: the gate's «nothing but
punctuation» check used to read only A-Z and dropped a whole Chinese reply."""
import pytest

from nucleo.flash.dialog import sanitize_reply
from voice import speech


@pytest.mark.parametrize("said,spoken", [
    ("Tidying up — [spreading them out now].", "Tidying up."),
    ("Hecho, [los ordeno] ya.", "Hecho, ya."),
    ("整理一下——[正在排列]。", "整理一下。"),
])
def test_the_aside_is_dropped_on_every_door(said, spoken):
    assert speech.sanitize(said, drop_metadata=False) == spoken
    assert speech.inline(said) == spoken
    assert sanitize_reply(said) == spoken


def test_a_link_keeps_its_words_and_an_aside_tag_stays_for_its_reader():
    assert speech.sanitize("See [the docs](https://x.y).", drop_metadata=False) == "See the docs."
    assert sanitize_reply("[[aparte]]") == "[[aparte]]"


def test_a_reply_that_is_only_an_aside_is_not_emptied():
    assert sanitize_reply("[pause]") == "[pause]"


def test_a_reply_in_another_script_is_still_prose():
    assert speech.sanitize("好的。", drop_metadata=False) == "好的。"
    assert speech.sanitize("はい、わかりました。") == "はい、わかりました。"
    assert speech.sanitize("---") == ""
