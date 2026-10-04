"""A finished errand is seeded into the sandbox before the opening line (V2-781 T517, 2026-10-04).

`flat-hunt-recall-the-report` («Enséñame lo del piso que te dije») had never run: its premise is a flat hunt
finished days ago whose sheet is already gone, and a fresh sandbox holds no errand, so a round would have
measured «I have nothing», not recall. The harness now writes what a closed commission leaves behind — the
durable row and its `task_artifacts` — through the engine's own store, in a child process aimed at the
sandbox DB, and reports which seeded row the round reached.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import errand_seed as ES
from tests.use_cases.e2e.agent import scenarios as SC


@pytest.mark.parametrize("locale,wanted", [("es", "Gràcia"), ("us", "Williamsburg")])
def test_both_twins_seed_two_plausible_flat_hunts_and_the_wanted_one_first(locale, wanted):
    errands = ES.errands_for("flat-hunt-recall-the-report", locale, now=2_000_000_000)
    assert len(errands) == 2, "the ambiguity half needs a second plausible errand"
    assert wanted in errands[0]["row"]["title"]
    for e in errands:
        assert e["row"]["state"] == "done" and e["row"]["kind"] != "inline"
        assert e["artifacts"]["result"]["items"] and e["artifacts"]["considered"]["rows"][0]["why"]
    assert ES.errands_for("remember-and-remind-deadline", locale) == []


def test_both_twins_exist():
    ids = {s.id for s in SC.all_scenarios()}
    assert {"flat-hunt-recall-the-report__es", "flat-hunt-recall-the-report__us"} <= ids


def test_sow_writes_the_row_and_its_report_through_the_engine_store(tmp_path):
    db = tmp_path / "memory" / "_data" / "sandbox.db"
    db.parent.mkdir(parents=True)
    errands = ES.errands_for("flat-hunt-recall-the-report", "es")
    assert ES.sow(str(db), errands, str(tmp_path)) == ["seed-flat-gracia", "seed-flat-santantoni"]
    con = sqlite3.connect(db)
    slots = {r[0] for r in con.execute("SELECT slot FROM task_artifacts WHERE task_id='seed-flat-gracia'")}
    assert slots == {"result", "criteria", "considered"}
    rows = json.loads(con.execute("SELECT payload FROM task_artifacts WHERE task_id='seed-flat-gracia' "
                                  "AND slot='considered'").fetchone()[0])["rows"]
    assert len(rows) == 5 and all(r["why"] for r in rows)
    # the lexical index the recall narrows with knows the row, so «lo del piso» can find it without a model
    assert con.execute("SELECT task_id FROM fts_tasks WHERE fts_tasks MATCH 'Gràcia'").fetchall()


def test_the_report_names_which_row_the_round_reached(tmp_path):
    db = tmp_path / "e.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (ts_ms INTEGER, payload TEXT)")
    con.execute("INSERT INTO events VALUES (5000, ?)", (json.dumps({"show": "results::seed-flat-gracia"}),))
    con.execute("INSERT INTO events VALUES (500, ?)", (json.dumps({"show": "results::seed-flat-santantoni"}),))
    con.commit()
    con.close()
    got = ES.opened(str(db), ["seed-flat-gracia", "seed-flat-santantoni"], since=1.0)
    assert got == ["seed-flat-gracia"], "an event before the round started is not the round's"
    note = ES.judge_note({"seeded": ["seed-flat-gracia", "seed-flat-santantoni"], "opened": got,
                          "titles": ["Pisos de alquiler en Gràcia", "Pisos de alquiler en Sant Antoni"]})
    assert "seed-flat-gracia" in note and "Gràcia" in note
    assert "FALLÓ" in ES.judge_note({"seeded": [], "error": "boom"})
