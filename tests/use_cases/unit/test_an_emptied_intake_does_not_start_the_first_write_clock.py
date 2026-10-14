"""An intake the door left EMPTY (`landed: 0`) does not start the weak «first write» clock either (node 2.708).

search-buy-camper ES (2026-10-14, sandbox 103520-es): every intake row went to Rejected (the price-ceiling reader took
«menos de 150.000 km» for a ceiling of 150,000,000), the sheet was EMPTY when the reply said «Sigue sin haber
resultados», and the judge filed a 254 s «retention» from a `landed: 0` write at 54.8 s. Node 2.665 fixed the strict
clock; with no strict clock the harness falls back to this one (`run.py`, «primera escritura»), which still counted it.
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
        d = {"id": "results::3a1ab5-ls1", "label": label, "src": src, **extra}
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)", (ts, "observer", "widget", label, json.dumps(d)))
    con.commit()
    con.close()
    return str(p)


CAMPER = [(9_200.0, "show", "worker:1", {}),
          (54_831.0, "data", "navegador", {"landed": 0})]      # five campers, all filed as Rejected


def test_an_emptied_intake_is_no_first_write(tmp_path):
    out = verify.sheet_timing(_db(tmp_path, CAMPER), since=0)
    assert out["sheet_rows_ms"] is None and out["sheet_named_ms"] is None, out


def test_an_intake_that_landed_rows_still_is(tmp_path):
    out = verify.sheet_timing(_db(tmp_path, CAMPER + [(200_000.0, "data", "navegador", {"landed": 3})]), since=0)
    assert out["sheet_rows_ms"] == 200_000.0, out
