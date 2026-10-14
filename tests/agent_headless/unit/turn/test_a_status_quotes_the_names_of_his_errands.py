"""A status sentence QUOTES the name of each errand, like every other line of ours that names one (node 2.703).

search-buy-vinyl ES (2026-10-14): «Así va todo: Comprar vinilo The Dark Side of the Moon — …» — the album's English
title sat unquoted in a Spanish sentence and read as the language of the line (the reply-language gate filed it as an
English reply). «errand_refined» and «errands_not_started» already quote; the status items now do too.
"""
from __future__ import annotations

import threading

from nucleo import dispatch
from nucleo.turn import errands_of_a_turn as E

ERRAND = "Comprar vinilo The Dark Side of the Moon"


def _brief():
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"wants_words": {"choice": "tell", "confidence": 0.99, "probs": {"tell": 0.99}}},
            "_call_id": "t", "turn_id": "t", "open_ids": []}


def test_the_name_is_quoted(monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "es")
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "2", "request": ERRAND, "phase": "", "note": "", "waiting_on": ""}])
    line = E.status_owed("¿Cómo va?", _brief())
    assert f"«{ERRAND}» — " in line, line


def test_one_item_reads_name_then_state():
    assert E.status_item({"request": ERRAND}, "en marcha") == f"«{ERRAND}» — en marcha"
