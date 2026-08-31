"""Did someone reset the engine while this round was being measured? An ATTRIBUTION fact, not a verdict.

`started_at` is sealed INSIDE `_run_scenario`, after the round's own `hard_reset()`, so a subsequent
`session/RESET` came from somewhere else — a second round, or the operator touching the set.

It matters because a reset closes ALL cards (`emit("widget","close")` → `owner._close_task`), and closing a
card with its task still alive leaves the tab `cancelled` WITHOUT touching the worker. Which is exactly the
signature of the family archived as “mid-round cancellation with the browser on the right page” (3 of 28 rounds, 2026-08-25):
`navegador_task.status == 'cancelled'` with `worker_health.cancelled == 0`. The question was never “what cancels
tabs” but “who reset the engine,” and the report had no way to answer it.
"""
import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import verify as V


@pytest.fixture
def db(tmp_path):
    """A unit test never touches the live sandbox."""
    p = tmp_path / "obs.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms INTEGER, topic TEXT, payload TEXT, "
                "cat TEXT, kind TEXT, label TEXT)")

    def add(*, ts, cat="sistema", kind="session", label="RESET"):
        con.execute("INSERT INTO events (ts_ms, topic, payload, cat, kind, label) VALUES (?,?,?,?,?,?)",
                    (int(ts * 1000), "obs", json.dumps({}), cat, kind, label))
    con.commit()
    return p, con, add


def test_una_ronda_limpia_no_acusa_a_nadie(db):
    p, con, add = db
    add(ts=100.0, label="turn")
    con.commit()
    assert V.resets_during_round(str(p), since=1000.0) == {"n": 0, "at_s": []}


def test_el_reset_de_la_PROPIA_tanda_queda_fuera(db):
    """The sensitivity that makes the instrument useful: `hard_reset()` runs BEFORE sealing `started_at`, so
    counting it would mark every round and the fact would distinguish nothing."""
    p, con, add = db
    add(ts=990.0)            # the case's own reset, just before starting
    con.commit()
    assert V.resets_during_round(str(p), since=1000.0)["n"] == 0


def test_un_reset_AJENO_se_ve_y_dice_CUÁNDO(db):
    """The second is as important as the first: a reset at 12 s takes down the entire round; one at 400 s
    may have occurred after the delivery that mattered."""
    p, con, add = db
    add(ts=1012.5)
    con.commit()
    r = V.resets_during_round(str(p), since=1000.0)
    assert r["n"] == 1
    assert r["at_s"] == [12.5]


def test_cuenta_TODOS_los_ajenos(db):
    p, con, add = db
    for t in (1010.0, 1200.0, 1305.0):
        add(ts=t)
    con.commit()
    assert V.resets_during_round(str(p), since=1000.0)["n"] == 3


def test_lo_encuentra_aunque_la_FAMILIA_cambie_de_nombre(db):
    """A signal searched for under the wrong field returns ZERO, and a zero is read as “this did not happen” —
    the quietest way an instrument can lie."""
    p, con, add = db
    add(ts=1050.0, cat="otra-cosa", kind="lo-que-sea")
    con.commit()
    assert V.resets_during_round(str(p), since=1000.0)["n"] == 1


def test_una_db_que_no_existe_no_revienta_la_ronda():
    assert V.resets_during_round("/no/such/place.db", since=1.0) == {"n": 0, "at_s": []}


def test_el_informe_LO_LLEVA():
    """Half the wiring (V2-199): the fact can be read correctly and still fail to reach whoever needs it."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert 'mech["resets_during_round"] = verifymod.resets_during_round(' in inspect.getsource(R._run_scenario)
