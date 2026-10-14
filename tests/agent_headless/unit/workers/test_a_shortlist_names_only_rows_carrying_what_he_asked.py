"""A finished shortlist completes its line only with rows that carry what he asked about (node 2.701).

search-buy-vinyl EN (2026-10-14): he asked twice for the pressing and the condition of each candidate. The closing
line is completed from the errand's sheet (`named_top`), and a row the sheet holds WITHOUT that answer is the same
tail he had asked not to be sent again. Rows that verify it are named; the rest are left on the sheet.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.flash import asked_fact_hold
from nucleo.workers import named_top
from widgets.results import data as sheet

COMMISSION = "Find me an original pressing of 'The Dark Side of the Moon' in good condition for under $70."
ASKED = "no need to show it again, just let me know when you have the pressing and condition details"
_OK = [{"label": "original pressing", "value": "yes — Harvest SMAS-11163"}, {"label": "good condition", "value": "no — G+"}]
ROWS = [{"title": "Dark Side · US 1st press", "price": "$33", "facts": _OK},
        {"title": "Dark Side + poster", "price": "$54", "facts": _OK},
        {"title": "Dark Side reissue LP", "price": "$27.99", "facts": [{"label": "Origin", "value": "network agent"}]},
        {"title": "Dark Side 180g", "price": "$15.36", "facts": []}]
LINE = "There's no original pressing in genuinely good condition; the closest is the US 1st press at about $33."


@pytest.fixture(autouse=True)
def _vinyl(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    sheet.store.save(sheet.sheet_key("t2701"), {"title": "Vinyl", "items": ROWS})


def _rec():
    return SimpleNamespace(sheet="t2701", goal=COMMISSION, injects=[])


def test_only_rows_that_answer_his_question_complete_the_line(monkeypatch):
    monkeypatch.setattr(asked_fact_hold, "recent_his_sentences", lambda limit=12: [COMMISSION, ASKED])
    out = named_top.complete(LINE, _rec())
    assert "Dark Side + poster — $54" in out, out
    assert "reissue" not in out and "180g" not in out, out
    assert "The 2 options:" in out, "the count is what was named, not the default three"


def test_without_his_question_the_default_three_are_named(monkeypatch):
    monkeypatch.setattr(asked_fact_hold, "recent_his_sentences", lambda limit=12: [COMMISSION])
    out = named_top.complete(LINE, _rec())
    assert "The 3 options:" in out and "reissue" in out, out
