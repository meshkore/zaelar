"""Progress is judged by the longest SILENCE, not by how many phases were emitted.

The requirement is about a person: "if the worker takes a long time, the user gets bored; they cannot stare at a
blank screen for seven minutes". Twenty phases in the first ten seconds followed by four minutes of nothing is
exactly that failure, and any average hides it — which is why the headline number here is the gap.
"""
import json
import sqlite3

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, rows):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (topic TEXT, ts_ms INT, kind TEXT, label TEXT, payload TEXT)")
    # The REAL format, copied from a round's database: topic `worker.phase` and the text in `phase`.
    con.executemany("INSERT INTO events VALUES ('worker.phase',?,'','',?)",
                    [(ms, json.dumps({"id": "2", "phase": t})) for ms, t in rows])
    con.commit()
    con.close()
    return str(p)


def test_a_burst_then_a_long_silence_is_caught(tmp_path):
    """The shape that averages out to 'healthy' and is the actual complaint."""
    rows = [(1000 + i * 500, f"paso {i}") for i in range(20)] + [(1000 + 240_000, "listo")]
    got = verify.progress_phases(_db(tmp_path, rows))
    assert got["n"] == 21
    assert got["gap_max_s"] > 200


def test_a_steady_beat_has_a_small_worst_gap(tmp_path):
    rows = [(1000 + i * 8000, "entrando en booking.com") for i in range(10)]
    got = verify.progress_phases(_db(tmp_path, rows))
    assert got["gap_max_s"] == 8.0


def test_the_texts_are_kept_so_they_can_be_read_as_sentences(tmp_path):
    """B1 (reads like a sentence) and B2 (it beats) fail independently, so the texts have to survive."""
    got = verify.progress_phases(_db(tmp_path, [(1000, "entrando en booking.com"), (9000, "12 resultados")]))
    assert [p["text"] for p in got["phases"]] == ["entrando en booking.com", "12 resultados"]
    assert got["phases"][1]["at_s"] == 8.0


def test_no_phases_is_zero_not_an_exception(tmp_path):
    got = verify.progress_phases(_db(tmp_path, []))
    assert got == {"n": 0, "phases": [], "gap_max_s": 0.0, "span_s": 0.0}


def test_an_empty_phase_text_does_not_count_as_progress(tmp_path):
    got = verify.progress_phases(_db(tmp_path, [(1000, "  "), (2000, "entrando en booking.com")]))
    assert got["n"] == 1
