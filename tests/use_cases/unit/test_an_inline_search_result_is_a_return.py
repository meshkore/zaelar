"""An inline web-search result is a RETURN, not a bare query (V2-781 T516, 2026-10-03).

Measured on `find-a-future-release-and-remind-me__us` and `quick-fact-opening-hours__us`: both judged FAIL for a
date / an opening hour «with no backing — N queries, 0 returns». The sandbox held the inline probe search as ONE
event, label «🔎 resultados web», the query in `text` and what came back in `evidence.items` (paramountplus.com:
«premieres Oct. 30, 2026»). `search_returns` only counted rows labelled «↩», so every sourced inline fact was
filed as a query nobody answered, and the judge read that as invention.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import verify

ROW = {"i": 14, "kind": "search", "label": "🔎 resultados web", "text": "Dexter new season premiere date fall 2026",
       "role": "system", "source": "ddg", "n": 5, "src": "probe",
       "evidence": {"items": [{"t": "Dexter®: Resurrection Season 2: Everything You Need To Know",
                               "u": "https://www.paramountplus.com/sneak-peak/dexter-resurrection-season-2",
                               "s": "Dexter®: Resurrection Season 2 premieres Oct. 30, 2026, on Paramount+."}]}}


def _db(tmp_path, rows):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (kind TEXT, label TEXT, payload TEXT, ts_ms INTEGER, topic TEXT)")
    for i, r in enumerate(rows):
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)", ("search", r["label"], json.dumps(r), 1000 + i, ""))
    con.commit()
    con.close()
    return p


def test_the_inline_row_counts_as_a_query_with_its_return(tmp_path):
    got = verify.search_returns(_db(tmp_path, [ROW]))
    assert got["queries"] == 1 and got["returns"] == 1, got
    assert "paramountplus.com" in got["sample"][0] and "Oct. 30, 2026" in got["sample"][0]


def test_a_query_with_nothing_back_is_still_a_bare_query(tmp_path):
    empty = dict(ROW, evidence={"items": []}, n=0)
    got = verify.search_returns(_db(tmp_path, [empty]))
    assert got["queries"] == 1 and got["returns"] == 0, got
