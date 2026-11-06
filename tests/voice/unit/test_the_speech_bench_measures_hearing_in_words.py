"""The speech bench (V2-856) reads hearing as WORD error rate over the phrase — accents and punctuation are not errors,
a dropped or swapped word is — and summarises each provider by its mean, leaving out the rows that never ran.
"""
from __future__ import annotations

from tests.voice.bench import speech_bench as B


def test_accents_case_and_punctuation_are_not_errors() -> None:
    assert B.wer("Recuérdame el jueves, a las cinco.", "recuerdame el jueves a las cinco") == 0.0


def test_a_dropped_and_a_swapped_word_each_count_once() -> None:
    assert B.wer("call Martha about the car", "call Marta about car") == 0.4


def test_nothing_heard_is_a_full_miss_and_the_summary_skips_rows_that_never_ran() -> None:
    assert B.wer("five thirty", "") == 1.0
    rep = {"stt": [{"provider": "a", "ok": True, "wer": 0.2, "s": 1.0}, {"provider": "a", "ok": True, "wer": 0.0, "s": 3.0},
                   {"provider": "b", "ok": None, "why": "no key"}],
           "tts": [{"provider": "c", "ok": True, "round_trip_wer": 0.1, "ttfb_s": 0.4}]}
    s = B.summary(rep)
    assert s == {"stt:a": {"n": 2, "wer": 0.1, "s": 2.0}, "tts:c": {"n": 1, "round_trip_wer": 0.1, "s": 0.4}}


def test_digits_a_clock_time_and_a_currency_sign_are_a_way_of_writing_not_a_mishearing() -> None:
    p_es, p_en = B.PHRASES[1][2], B.PHRASES[3][2]
    assert B.heard(p_es, "Busca 3 monitores de 27 pulgadas por menos de 400 euros.") == 0.0
    assert B.heard(p_en, "Find three 27-inch monitors for less than $400.") == 0.0
    assert B.heard(p_en, "Find 327-inch monitors for less than $400.") > 0, "a merged number is still a mishearing"

