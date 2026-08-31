"""Did the results sheet open BEFORE there was a result to put in it?

That is the whole point of V2-227 C, and the screen contract cannot answer it: driving `render()` with
hand-made payloads proves the widget behaves when data arrives, not that anyone sends it or that the
sheet opens by itself when the errand starts. Green contract plus missing wiring still leaves a person
staring at a blank screen -- the tab exists and nobody opens it for them.
"""
import json
import sqlite3

from tests.use_cases.e2e.agent import verify

_REAL = '[{"title": "Bécquer", "price": "100 €"}]'
_USAGE = "usage: nav_cli [-h] {snapshot,look,navigate,click}"


def _db(tmp_path, rows):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (topic TEXT, ts_ms INT, kind TEXT, label TEXT, payload TEXT)")
    con.executemany("INSERT INTO events VALUES ('observer',?,?,'',?)", rows)
    con.commit()
    con.close()
    return str(p)


def test_the_sheet_opening_first_is_the_good_case(tmp_path):
    got = verify.sheet_timing(_db(tmp_path, [
        (1_000, "widget", json.dumps({"id": "results", "label": "show"})),
        (9_000, "navegador", json.dumps({"text": _REAL}))]))
    assert got["opened_before"] is True and got["lead_s"] == 8.0


def test_the_sheet_arriving_after_the_result_is_the_defect(tmp_path):
    got = verify.sheet_timing(_db(tmp_path, [
        (1_000, "navegador", json.dumps({"text": _REAL})),
        (9_000, "widget", json.dumps({"id": "results", "label": "show"}))]))
    assert got["opened_before"] is False


def test_a_usage_error_is_not_a_result(tmp_path):
    """The browser's first return is often a mis-typed command; taking it for a result moves the clock."""
    got = verify.sheet_timing(_db(tmp_path, [
        (1_000, "navegador", json.dumps({"text": _USAGE})),
        (5_000, "widget", json.dumps({"id": "results", "label": "show"})),
        (9_000, "navegador", json.dumps({"text": _REAL}))]))
    assert got["opened_before"] is True and got["lead_s"] == 4.0


def test_a_background_write_is_not_an_opening(tmp_path):
    """The check has to DISCRIMINATE. Its first version accepted any operation on the sheet and reported
    'opened 51s early' on a round from BEFORE the wiring existed, because a background `data` write had
    always been there. A check that goes green with the feature built and unbuilt is worse than none: it
    gives confidence. Only `show` counts as opening it."""
    got = verify.sheet_timing(_db(tmp_path, [
        (1_000, "widget", json.dumps({"id": "results", "label": "data"})),
        (9_000, "navegador", json.dumps({"text": _REAL}))]))
    assert got["sheet_ms"] is None and got["opened_before"] is None
    assert got["sheet_any_ms"] == 1_000        # it is recorded, but does not count as an opening


def test_another_widget_is_not_the_sheet(tmp_path):
    got = verify.sheet_timing(_db(tmp_path, [
        (1_000, "widget", json.dumps({"id": "navegador", "label": "data"})),
        (9_000, "navegador", json.dumps({"text": _REAL}))]))
    assert got["sheet_ms"] is None and got["opened_before"] is None


def test_not_measured_is_None_and_never_False(tmp_path):
    """`False` means it arrived late. Missing one of the two instants means nothing was measured."""
    got = verify.sheet_timing(_db(tmp_path, [(1_000, "widget", json.dumps({"id": "results"}))]))
    assert got["opened_before"] is None
