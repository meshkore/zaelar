"""A parked errand answers only to its own words, and one errand is counted once (node 2.457).

three-tasks-at-once (EN, 2026-10-11 02:58). The game parked; «yeah go ahead with the game, and add coins… btw for the
monitor it has to be at least 27 inches» was not read as a yes and was FOLDED into the parked game whole — monitor
words included. The next turn, «none of those work tbh… at least 27 inches and no more than $150, keep looking», was
about the monitor listings; but the game now «carried» monitor and inches, so the sentence named it, and its «no»
CANCELLED the game. A sentence that also talks about another errand is not folded into a parked one.

And the harness counted the game's parked ask and its confirmed launch as «2-3 workers para UN encargo»: an
escalation was «born» if ANY worker spawned within 25 s. It is born when ITS OWN worker spawned (same id).
"""
from __future__ import annotations

import json
import sqlite3
import time
import types

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as dc
from nucleo.turn import confirm_gates as gates
from nucleo.turn import errands_of_a_turn as E
from widgets import confirm as wconfirm

GAME = "Build a playable platform game widget, Super Mario style: a side-scrolling platformer with a character"
MONITOR = E.listing_errand({"query": "cheap used monitor"})


@pytest.fixture
def parked(monkeypatch):
    out = []
    monkeypatch.setattr("nucleo.acts.errand.escalate_to_slowbrain", lambda req, context=None: out.append(req) or 1)
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [{"id": "3", "request": MONITOR, "phase": "",
                                                                  "waiting_on": ""}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"2": {"request": GAME, "kind": "code", "trusted": True,
                                                       "context": {}, "sheet": "", "ts": time.time(),
                                                       "question": "Shall I?"}})
    return out


def test_a_mixed_sentence_is_not_folded_and_the_monitor_no_spares_the_game(parked, monkeypatch):
    monkeypatch.setattr(wconfirm, "_judge", lambda q, r, timeout=4.0: "other")
    # a sentence about the game AND the monitor that answers nothing: the game waits, unpolluted
    assert not gates.resolve_all("the game sounds fun. btw for the monitor it has to be at least 27 inches, used is "
                                 "fine")
    assert not dc._PENDING_CONFIRM["2"].get("refinements")
    monkeypatch.setattr(wconfirm, "_judge", lambda q, r, timeout=4.0: "no")      # even a judge reading «no»
    assert not gates.resolve_all("none of those work tbh. the dell's over $150 and the acer is only 24 inches, "
                                 "at least 27 inches and no more than $150, keep looking")
    assert "2" in dc._PENDING_CONFIRM and not parked, "the game was not cancelled by a sentence about monitors"


def test_a_sentence_only_about_the_game_still_folds_in(parked):
    assert not gates.resolve_all("and for the game, the coins should add points")
    assert dc._PENDING_CONFIRM["2"].get("refinements")


def test_an_escalation_is_born_by_its_own_worker(tmp_path):
    from tests.use_cases.e2e.agent import verify
    db = tmp_path / "e.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, payload TEXT, ts_ms INTEGER)")
    rows = [("escalate.requested", {"id": 1, "request": "Write a report on electric cars for city driving",
                                    "context": {"src": "probe"}}, 1000),
            ("escalate.requested", {"id": 2, "request": GAME + " with coins", "context": {"src": "probe"}}, 2000),
            ("worker.spawned", {"id": "1", "goal": "Write a report on electric cars"}, 5000),
            ("escalate.requested", {"id": 8, "request": GAME + " with coins and a higher jump",
                                    "context": {"src": "probe", "confirmed": True}}, 300000),
            ("worker.spawned", {"id": "8", "goal": GAME}, 301000)]
    for topic, payload, ts in rows:
        con.execute("INSERT INTO events VALUES (?, ?, ?)", (topic, json.dumps(payload), ts))
    con.commit()
    con.close()
    out = verify.duplicate_errands(str(db))
    assert not out.get("groups"), f"the parked ask (2) had no worker of its own: {out.get('groups')}"
