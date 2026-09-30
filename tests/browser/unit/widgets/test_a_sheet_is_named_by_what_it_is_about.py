"""A sheet is named by what its title is ABOUT, never by a request's verbs or particles (node 4.239).

Demo pass 62 (2026-09-29): the monitor sheet's title was «Find 27 inch 4K monitors under $400». «find me a free 45
minutes tomorrow afternoon…» NAMED it by «find» (C2 re-routed the agenda's answer onto the sheet), and «plan a
five day trip… under 2000 total» named it by «under» (T1: the trip was judged to continue the monitor search at
1.0 «by widget», inherited its sheet and wrote over it). Title matching kept every word of four letters or more.
"""
import pytest

from widgets import instances, runtime

MONITORS = "Find 27 inch 4K monitors under $400"
TRIP = "johnny, plan a five day trip somewhere warm for anna and me, from LAX, december 21 to 25, under 2000 total, show me when it's ready"
FREE = "find me a free 45 minutes tomorrow afternoon to talk with rowan, after my last meeting"


@pytest.fixture
def closed_sheet(monkeypatch):
    monkeypatch.setattr(instances, "recent_faces", lambda n=8: [{"id": "results::2adbe5-ls1", "label": MONITORS}])


@pytest.fixture
def open_sheet(monkeypatch):
    monkeypatch.setattr(instances, "card_face", lambda inst: {"label": MONITORS})


def test_a_closed_sheet_is_not_named_by_a_verb_or_a_particle(closed_sheet):
    assert runtime.identify_named(TRIP) is None
    assert runtime.identify_named(FREE) is None
    assert runtime.identify_named("show me the monitors") == "results::2adbe5-ls1"


def test_an_open_sheet_is_not_named_by_a_verb_or_a_particle(open_sheet, monkeypatch):
    monkeypatch.setattr(instances, "recent_faces", lambda n=8: [])
    ids = ["results::2adbe5-ls1"]
    assert runtime.identify_named(TRIP, open_ids=ids) is None
    assert runtime.identify_named(FREE, open_ids=ids) is None
    assert runtime.identify_named("so how did the monitors go, show me", open_ids=ids) == "results::2adbe5-ls1"


def test_the_errand_dedup_no_longer_joins_the_trip_to_the_monitors(closed_sheet):
    from nucleo import dedup
    prev, ev = dedup.scan(TRIP, "generic", [("3", "can you find me like three 27 inch 4k monitors, under 400 bucks")])
    assert prev is None and ev["by"] != "widget"


def test_title_words_drop_numbers_and_request_words():
    assert runtime.title_words(MONITORS) == {"inch", "monitors"}
    assert "under" not in runtime.title_words(TRIP) and "trip" in runtime.title_words(TRIP)
