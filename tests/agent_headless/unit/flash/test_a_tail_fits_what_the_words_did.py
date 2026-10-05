"""The line after a verdict-completed act fits what the words DID — one table, keyed by their shape (passes 108-109).

«Which ones should I put side by side — the calendar or the monitor results? I've gone ahead and done it, as you
asked.» (S2, Z1, S3): the words asked WHICH, the verdict picked one and did it, and the tail answered a go-ahead
nobody had given. Asking which is not asking whether: after «which?» the voice says it went with the likeliest one
and invites a correction; after «want me to…?» it says it went ahead; after a denial, «Done.». The shape is read
from the model's own words (`clarifying`), so the table needs no extra trip on the tail — the brief is fired before
the reply exists and cannot read it. And the wall keeps the space between the question and the tail.
"""
from __future__ import annotations

import pytest

from nucleo.flash import act_repair as AR


@pytest.fixture(autouse=True)
def _en(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")


def _line(field: str) -> str:
    from i18n import langs
    return getattr(langs.current_language(), field).strip()


def test_asking_which_says_it_went_with_one():
    tail = AR.after_the_completion("Which ones should I put side by side — the calendar or the monitor results?",
                                   "results", "layout")
    assert tail.strip() == _line("data_ack_went_with")
    assert "as you asked" not in tail


def test_asking_whether_still_says_it_went_ahead():
    assert AR.after_the_completion("Want me to put them side by side?", "results", "layout").strip() == \
        _line("data_ack_went_ahead")
    assert AR.after_the_repair("Want me to write that to Quinn?", False, "mensajeria", "forward").strip() == \
        _line("data_ack_went_ahead")


def test_the_repair_reads_the_same_table():
    assert AR.after_the_repair("Which mail do you mean, the receipt or the invoice?", False, "mensajeria",
                               "forward").strip() == _line("data_ack_went_with")
    assert AR.after_the_repair("There's no unread toggle.", False, "mensajeria", "unread").strip() == _line("data_ack")


def test_every_shape_names_a_line_both_languages_carry():
    from i18n import langs
    assert set(AR.TAILS) == {"asked_which", "asked", "denied"}
    for field in AR.TAILS.values():
        for code in ("es", "en"):
            assert getattr(langs.spec(code), field, "").strip(), (code, field)


def test_the_wall_keeps_the_space_before_the_tail():
    src = open("nucleo/flash/post_stream_words.py", encoding="utf-8").read()
    assert 'send(speech.sanitize(_c_tail, drop_metadata=False))' not in src \
        and 'send(speech.sanitize(_ar_tail, drop_metadata=False))' not in src, \
        "sanitize strips the tail's leading space: «side by side?I've gone ahead» on the wall"


def test_a_question_that_also_promises_still_gets_its_tail():
    """Pass 114, C5: «Want me to fire off that Telegram to Ethan now… and I'll send it as soon as you confirm?» — the
    repair SENT it, and `promised` (the «I'll send» in the question) dropped the tail: the last thing heard asked."""
    said = "Want me to fire off that Telegram to Rowan now, and I'll send it as soon as you confirm?"
    assert AR.after_the_repair(said, True, "mensajeria", "send_to").strip() == _line("data_ack_went_ahead")
    assert AR.after_the_repair("Sending it to Rowan now.", True, "mensajeria", "send_to") == "", "a promise needs nothing"
