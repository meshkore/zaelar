"""A column read while the engine is still writing is a snapshot reported as a conclusion.

Three findings were misread this way in one night, all the same shape: `worker_health` said «4 spawned,
0 ok» (one had errored, three were still working), `worker_deaths` listed a corpse that was a provider
handoff in flight, and `notes_from_search` said 0 with twelve answers on the wire — the notes were queued
six seconds after the read. Every one of them reached the fixing agent before being caught.
"""
from __future__ import annotations

import sqlite3
import threading
import time

from tests.use_cases.e2e.agent import verify


def _db(tmp_path):
    p = tmp_path / "s.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (ts_ms INTEGER, topic TEXT, kind TEXT, label TEXT, span TEXT, payload TEXT)")
    con.commit()
    con.close()
    return str(p)


def test_a_quiet_store_settles_at_once(tmp_path):
    got = verify.wait_for_quiescence(_db(tmp_path), quiet_for=0.4, poll=0.1, max_wait=5)
    assert got["settled"] is True
    assert got["events"] == 0


def test_it_WAITS_for_a_worker_that_has_not_FINISHED(tmp_path):
    """The one that matters, and the reason silence alone is not the condition: the store goes quiet for
    longer than `quiet_for` while a worker is still alive, and the note lands after that gap."""
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO events VALUES (0,'worker.spawned',NULL,NULL,NULL,'{\"id\":\"1\"}')")
    con.commit()
    con.close()

    def late():
        time.sleep(0.8)
        con = sqlite3.connect(db)
        con.execute("INSERT INTO events VALUES (1,'observer','brain','n',NULL,'{}')")
        con.execute("INSERT INTO events VALUES (2,'worker.done',NULL,NULL,NULL,'{\"id\":\"1\",\"ok\":true}')")
        con.commit()
        con.close()

    t = threading.Thread(target=late)
    t.start()
    got = verify.wait_for_quiescence(db, quiet_for=0.4, poll=0.1, max_wait=6)
    t.join()
    assert got["settled"] is True
    assert got["events"] == 3, "the late writes must be inside the measurement, not after it"
    assert got["waited_s"] >= 0.8


def test_a_store_that_never_settles_SAYS_so(tmp_path):
    """A round that never goes quiet is a worker still running when the conversation ended — a finding,
    not a defect, and the report has to be able to tell the difference."""
    db = _db(tmp_path)
    stop = threading.Event()

    def noisy():
        i = 0
        while not stop.is_set():
            con = sqlite3.connect(db)
            con.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (i, "observer", "task", "x", None, "{}"))
            con.commit()
            con.close()
            i += 1
            time.sleep(0.05)

    t = threading.Thread(target=noisy)
    t.start()
    got = verify.wait_for_quiescence(db, quiet_for=0.5, poll=0.1, max_wait=1.2)
    stop.set()
    t.join()
    assert got["settled"] is False
    assert "seguía escribiendo" in got.get("note", "")


def test_an_unreadable_store_is_not_reported_as_settled(tmp_path):
    got = verify.wait_for_quiescence(str(tmp_path / "does-not-exist.db"), quiet_for=0.2, poll=0.1, max_wait=1)
    assert got["settled"] is None, "could not look is not the same as nothing happened"
