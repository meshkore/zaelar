"""Two delivery paths, measured side by side — the experiment that turned a judgement into a diagnosis.

2026-08-20, inside ONE conversation, one model, one turn budget:

    19:43:31  system note pushed («el proceso pregunta: ¿A qué ciudad…?»)
    19:43:34  turn 1 relayed it almost verbatim               → said in 3 seconds
    (no note)  the FAILED task, rendered only as a prompt state line, 7 turns running
               turns 1-7 answered "sigo esperando", "te aviso"  → 0 of 7

Same information, opposite outcomes, and the losing path was imperative and in capitals. That is what turned
"the model disobeys" into "one kind of fact has a delivery path and the other does not" — a different fix with a
different owner. Hand-queried three times before it earned a place in the report.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import judge as J, verify as V


def _db(tmp_path, notes):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER, topic TEXT, "
                "label TEXT, payload TEXT)")
    for ts, txt in notes:
        con.execute("INSERT INTO events (ts_ms, topic, label, payload) VALUES (?,?,?,?)",
                    (int(ts), "observer", "📩 system note → FlashBrain (probe)", json.dumps({"text": txt})))
    con.execute("INSERT INTO events (ts_ms, topic, label, payload) VALUES (?,?,?,?)",
                (1, "observer", "🌐 web", json.dumps({"text": "no es una nota"})))
    con.commit()
    con.close()
    return p


def test_it_reads_the_pushed_notes(tmp_path):
    rows = V.proactive_notes(_db(tmp_path, [(100_000, "aviso uno"), (200_000, "aviso dos")]))
    assert [r["text"] for r in rows] == ["aviso uno", "aviso dos"]


def test_an_event_that_is_not_a_note_is_not_counted(tmp_path):
    """Sensitivity: the whole measurement is a contrast, so counting anything else collapses it."""
    assert len(V.proactive_notes(_db(tmp_path, [(100_000, "x")]))) == 1


def test_coverage_ties_a_note_to_the_turn_it_could_have_changed():
    """A note only counts for the turn that came AFTER it and before the next — that is the window in which it
    could have changed what was said."""
    turns = [{"turn": 0, "at_ms": 1000, "alert": True}, {"turn": 1, "at_ms": 2000, "alert": True},
             {"turn": 2, "at_ms": 3000, "alert": True}]
    cov = V.note_coverage(turns, [{"at_ms": 1500, "text": "x"}])
    assert cov == {"alert_turns": 3, "with_note": 1, "notes": 1}


def test_a_note_AFTER_the_last_turn_covers_nothing():
    """The theatre round ended before its confirm question was pushed. That is "unverified", never "delivered"."""
    turns = [{"turn": 0, "at_ms": 1000, "alert": True}]
    assert V.note_coverage(turns, [{"at_ms": 9000, "text": "x"}])["with_note"] == 0


def test_no_alert_turns_means_nothing_to_cover():
    assert V.note_coverage([{"turn": 0, "at_ms": 1, "alert": False}], [])["alert_turns"] == 0


def test_the_judge_is_told_to_name_WHICH_of_the_two_defects():
    txt = J.mechanism_facts({"note_coverage": {"alert_turns": 7, "with_note": 1, "notes": 1}})
    assert "7 turno(s) tenían algo que contar" in txt
    assert "solo 1 recibieron un AVISO EMPUJADO" in txt
    assert "cada uno lo arregla otra persona" in txt


def test_and_says_nothing_when_there_was_nothing_to_report():
    assert "ENTREGA vs RENDERIZADO" not in J.mechanism_facts({"note_coverage": {"alert_turns": 0}})
