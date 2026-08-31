"""The waiting filler must not say the same phrase FOUR times (V2-189).

`data_acks` has had this handling since V2-038, because two consecutive “Done.” messages triggered the
loop detector. The waiting filler—which is said much more often—never received it. Measured in two
different cases from the same night:

  · `cheapest-monitor` (2026-08-20 01:21) — “Okay, give me a moment to look at it.” FOUR times, word for
    word, with the operator replying “okay, I’ll stay alert” / “okay, no rush” each time. overall 1/5,
    efficiency 1.
  · `restaurant-tonight-madrid` (01:01) — five turns of the same thing. The judge: “severe communication
    inefficiency,” high severity.

And the model does not say it: the never-silent backstop supplies the phrase on our behalf when the turn
returns without its own content. Removing it is worse (V2-092/V2-122: a silent turn is the most serious
failure), so what needed fixing was that it **not repeat** and that, after the second wait, it include the
only honest fact available—how long it has been waiting—with a way out. Never a STEP: that is the line
drawn by V2-133.
"""
from __future__ import annotations

import pytest

from nucleo.flash import router_guards as g
from voice.engine.core import langs


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(g, "_longest_pending_min", lambda: 7)
    yield


def _converse(lang, turns: int) -> list[str]:
    window, said = [], []
    for _ in range(turns):
        line = g.holding_line(window, lang)
        said.append(line)
        window += [{"role": "user", "content": "vale, quedo atento"},
                   {"role": "assistant", "content": line}]
    return said


@pytest.mark.parametrize("code", ["es", "en"])
def test_four_waits_are_never_the_same_sentence_four_times(code):
    said = _converse(langs.LANGUAGES[code], 4)
    assert len(set(said)) == 4, f"se repitió: {said}"


@pytest.mark.parametrize("code", ["es", "en"])
def test_and_never_twice_IN_A_ROW(code):
    """The form that is truly noticeable. Rotating while still repeating the one from just before fixes nothing."""
    said = _converse(langs.LANGUAGES[code], 8)
    assert all(a != b for a, b in zip(said, said[1:])), said


def test_past_the_second_wait_it_says_how_long_and_offers_a_way_out():
    said = _converse(langs.LANGUAGES["es"], 3)
    assert "7 min" in said[2]
    assert "?" in said[2]                       # a way out, not another process cycle


def test_but_it_never_states_a_STEP():
    """The V2-133 line: the filler may say that it is continuing, and how long it has been; never WHAT POINT it is at. Eight of
twelve cases in that batch failed because of an invented phase in the exact form of a worker step."""
    said = _converse(langs.LANGUAGES["es"], 6)
    prohibidas = ("login", "rellenando", "consultando", "en la página", "formulario", "fase")
    for line in said:
        assert not any(p in line.lower() for p in prohibidas), line


def test_with_no_task_to_time_it_still_never_repeats(monkeypatch):
    """The fact may be unavailable (the dispatch cannot be read). That degrades ESCALATION, not
non-repetition: continuing to say the same thing four times would be the same defect with another excuse."""
    monkeypatch.setattr(g, "_longest_pending_min", lambda: 0)
    said = _converse(langs.LANGUAGES["es"], 3)
    assert all(a != b for a, b in zip(said, said[1:])), said


def test_the_chooser_is_wired_into_BOTH_channels():
    """`probe.py` and the voice provider are parallel implementations of the same turn, and the provider only
distinguished the FIRST wait from the others: from the third onward they were all identical."""
    import inspect

    from nucleo.flash import probe as _probe
    from voice.engine.llm.providers import nucleo as _provider
    assert "holding_line(" in inspect.getsource(_probe.run_turn)
    assert "holding_line(" in inspect.getsource(_provider)
