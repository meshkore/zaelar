"""An intake write whose every row the door filed in Rejected (`landed: 0`) does not start the strict «candidates
existed» clock; the intake says what landed (node 2.665).

search-buy-boat-multicountry EN (2026-10-14, sandbox 093848-en): `sheet_named_ms` fell on the first `src=navegador`
write at 279.9 s — whose one row, «Advanced Search», the door had just filed as Rejected (`kept: 0`). The sheet was
EMPTY when the last turn said «nothing landed yet» at 286 s, yet the judge read «5 candidates written 7 s before»
and filed a true sentence as an [alta] denial. The five boats came at 320 s, after the conversation.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, events):
    p = tmp_path / "clock.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE events (ts_ms REAL, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    for ts, label, src, extra in events:
        d = {"id": "results::ea87f7-ls1", "label": label, "src": src, **extra}
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)", (ts, "observer", "widget", label, json.dumps(d)))
    con.commit()
    con.close()
    return str(p)


BOAT_EN = [(9_000.0, "show", "worker:1", {}),
           (279_880.0, "data", "navegador", {"landed": 0}),     # «Advanced Search — $1» → Rejected
           (320_369.0, "data", "navegador", {"landed": 5})]     # the five Lagoon 440s


def test_an_intake_the_door_emptied_is_not_the_first_candidate(tmp_path):
    out = verify.sheet_timing(_db(tmp_path, BOAT_EN), since=0)
    assert out["sheet_named_ms"] == 320_369.0, out


def test_an_intake_of_an_older_engine_still_starts_it(tmp_path):
    out = verify.sheet_timing(_db(tmp_path, [(9_000.0, "show", "worker:1", {}), (45_000.0, "data", "navegador", {})]),
                              since=0)
    assert out["sheet_named_ms"] == 45_000.0, "no `landed` field = the old meaning: an intake wrote candidates"


def test_the_intake_says_what_landed(monkeypatch):
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, **k: seen.append((kind, label, k.get("extra") or {})))
    from widgets.results import category_gate, intake
    category_gate.hear("clock1-ls1", "Find me a used Lagoon 440 catamaran for under $325,000.")
    intake.push([{"title": "Advanced Search", "price": "$1", "url": "https://www.boattrader.com/search/"}],
                sheet="clock1-ls1")
    landed = [e["landed"] for k, lab, e in seen if lab == "data" and e.get("src") == "navegador"]
    assert landed == [0], seen
