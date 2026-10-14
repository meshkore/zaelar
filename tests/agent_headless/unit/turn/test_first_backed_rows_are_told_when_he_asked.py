"""The FIRST backed rows of an errand are told to him unprompted when he asked to be told — and only then (node 2.678).

search-buy-boat-multicountry (2026-10-14): «ok, just lmk when something lands»; five Lagoon 440 rows landed on the
errand's sheet 34 s after his last turn, the worker was still running, and nothing reached him. The cues are
language data (`LangSpec.tell_me_cues` / `tell_you_cues`): his «avísame» or our «te aviso» both count.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo.turn import first_rows_notice as frn

ERRAND = {"id": "ls1", "request": "Find a used Lagoon 440 catamaran under $325,000", "secs": 300, "sheet": "ab12-ls1"}
ROWS = [
    {"title": "2004 Lagoon 440, Cancun Mexico", "price": "$289,000", "url": "https://yachtworld.com/a"},
    {"title": "2005 Lagoon 440 for sale", "url": "https://boattrader.com/b"},
    {"title": "Used Sail Lagoon Catamaran 440", "source": "Boatshed"},
    {"title": "2007 Lagoon 440", "price": "$310,000", "url": "https://yachtworld.com/d"},
]
NOW = 1_000_000.0


def _ev(t, role, text, kind="brain"):
    e = {"t_ms": t, "kind": kind, "role": role, "text": text}
    if kind == "brain":
        e["wall"] = "you" if role == "user" else "agent"
    return e


def _talk(user_line, reply="Still nothing yet — the ad sites are blocking direct access."):
    return [_ev(NOW - 200_000, "user", "Find me a used Lagoon 440 catamaran for under $325,000."),
            _ev(NOW - 190_000, "assistant", "I'm on it."),
            _ev(NOW - 40_000, "user", user_line), _ev(NOW - 34_000, "assistant", reply)]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    frn.forget()
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    yield
    frn.forget()


def test_he_asked_to_be_told_and_the_best_three_are_named():
    said, why = frn.decide("ab12-ls1", {"title": "Lagoon 440 hunt", "items": ROWS}, errand=ERRAND,
                           events=_talk("ok, just lmk when something lands"), now_ms=NOW)
    assert why == ""
    assert said.startswith("The first ones for «Lagoon 440 hunt» are in:")
    assert "2004 Lagoon 440, Cancun Mexico — $289,000" in said and "Used Sail Lagoon Catamaran 440" in said
    assert "2007 Lagoon 440" not in said              # three at most


def test_our_promise_counts_as_his_ask():
    said, why = frn.decide("ab12-ls1", {"items": ROWS}, errand=ERRAND,
                           events=_talk("ok, keep digging", "Will do — I'll flag it the second a boat lands."),
                           now_ms=NOW)
    assert why == "" and said


def test_spanish_cues_and_the_spanish_sentence(monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))
    said, why = frn.decide("ab12-ls1", {"title": "Piso en Valencia", "items": ROWS}, errand=ERRAND,
                           events=_talk("vale, avísame cuando lo tengas", "Sigo con ello."), now_ms=NOW)
    assert why == ""
    assert said.startswith("Ya tengo los primeros para «Piso en Valencia»:")


def test_without_an_ask_or_a_promise_nothing_is_said():
    said, why = frn.decide("ab12-ls1", {"items": ROWS}, errand=ERRAND,
                           events=_talk("ok, keep digging", "Still working on it."), now_ms=NOW)
    assert (said, why) == ("", "not asked")


def test_an_ask_before_the_errand_started_does_not_count():
    events = [_ev(NOW - 900_000, "user", "let me know when the pizza arrives")] + _talk("ok", "Working on it.")
    assert frn.decide("ab12-ls1", {"items": ROWS}, errand=ERRAND, events=events, now_ms=NOW)[1] == "not asked"


def test_rows_without_a_link_or_a_source_are_not_backed():
    bare = [{"title": "2004 Lagoon 440"}, {"title": "2005 Lagoon 440", "price": "$300,000"}]
    assert frn.decide("ab12-ls1", {"items": bare}, errand=ERRAND,
                      events=_talk("lmk"), now_ms=NOW)[1] == "no backed rows"


def test_no_live_errand_no_notice():
    assert frn.decide("ab12-ls1", {"items": ROWS}, errand=None, events=_talk("lmk"), now_ms=NOW)[1] == "no live errand"


def test_voice_transcripts_are_read_too():
    events = [_ev(NOW - 40_000, "user", "keep me posted", kind="transcript"),
              _ev(NOW - 35_000, "assistant", "Sure.", kind="transcript")]
    assert frn.decide("ab12-ls1", {"items": ROWS}, errand=ERRAND, events=events, now_ms=NOW)[1] == ""
