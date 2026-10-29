"""A locked database DELAYS the event record, never loses it (V2-831 T-22).

`bus/log.py` writes the `events` table — what the Master and `observability/flows.py` read — into `zaelar.db`, the
SAME file central memory writes. Measured with a simulated load (one writer holding a 3 s transaction on the file):
rows were delayed up to 9.1 s, and every row that waited past SQLite's 5 s busy timeout was LOST, only counted. The
emit time was always right (`ts_ms` is stamped at dispatch); the record was not.

Class: a locked database is waited out with backoff, in order, in one commit per batch, bounded by
`_LOCK_BUDGET_S`; past the bound the rows are dropped LOUDLY (an error in the log), never silently.

Disarm: treat «locked» like any other error (no retry) → the first test reds (rows lost).
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import time

import pytest

from bus import log as blog
from tests.waiting import until


@pytest.fixture
def own_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    old = blog._conn
    blog._conn = None
    conn = blog._connect()
    conn.execute("PRAGMA busy_timeout=150")         # the 5 s default, shortened so the test takes seconds
    blog._insert_failed["n"] = 0
    yield tmp_path / "zaelar.db"
    blog.drain(5.0)
    conn.close()
    blog._conn = old


def _hold_lock(path, seconds: float, held: threading.Event):
    """Another writer of the same file (central memory) holding a write transaction."""
    c = sqlite3.connect(str(path), timeout=5)
    c.execute("CREATE TABLE IF NOT EXISTS mem(a)")
    c.execute("BEGIN IMMEDIATE")
    c.execute("INSERT INTO mem VALUES (1)")
    held.set()
    time.sleep(seconds)
    c.commit()
    c.close()


def _probe_rows():
    from observability import flows
    return [e for e in flows.events(limit=1000) if str(e.get("label") or "").startswith("probe ")]


def test_rows_written_during_a_lock_all_land_in_order_with_their_emit_time(own_db):
    held = threading.Event()
    t = threading.Thread(target=_hold_lock, args=(own_db, 1.5, held), daemon=True)
    t.start()
    assert held.wait(5)
    sent = []
    for n in range(20):
        ts = time.time() * 1000.0
        sent.append(ts)
        blog._write({"topic": "observer", "ts_ms": ts, "payload": {"kind": "brain", "label": f"probe {n}"}})
    asyncio.run(until(lambda: len(_probe_rows()) == 20, "all 20 rows written during the lock, read by the Master's reader",
                      timeout_s=15))
    rows = _probe_rows()
    assert [r["label"] for r in rows] == [f"probe {n}" for n in range(20)], "the record lost its order"
    assert [r["ts_ms"] for r in rows] == sent, "a row carries its write time, not its emit time"
    assert blog._insert_failed["n"] == 0
    t.join(5)


def test_past_the_bound_the_loss_is_said_loudly(own_db, monkeypatch):
    from loguru import logger
    monkeypatch.setattr(blog, "_LOCK_BUDGET_S", 0.3)
    said = []
    sink = logger.add(lambda m: said.append(m.record["message"]), level="ERROR")
    held = threading.Event()
    t = threading.Thread(target=_hold_lock, args=(own_db, 2.0, held), daemon=True)
    t.start()
    assert held.wait(5)
    try:
        blog._write_now({"topic": "observer", "ts_ms": time.time() * 1000.0,
                         "payload": {"kind": "brain", "label": "probe lost"}})
    finally:
        logger.remove(sink)
    t.join(5)
    assert blog._insert_failed["n"] == 1, "a dropped row was not counted"
    assert any("LOST" in m and "locked" in m for m in said), f"the loss was not said: {said}"


def test_a_bad_row_does_not_take_its_batch_with_it(own_db):
    good = {"topic": "observer", "ts_ms": time.time() * 1000.0, "payload": {"kind": "brain", "label": "probe ok"}}
    blog._write_batch([good, {"topic": "observer", "ts_ms": "not a number", "payload": {}}, dict(good)])
    assert len(_probe_rows()) == 2 and blog._insert_failed["n"] == 1


def test_a_backlog_is_written_in_batches_not_one_commit_per_row(own_db, monkeypatch):
    sizes = []
    real = blog._insert
    monkeypatch.setattr(blog, "_insert", lambda rows: (sizes.append(len(rows)), real(rows))[1])
    with blog._lock:                                  # the writer is behind (here: stalled on the lock)
        for n in range(50):
            blog._write({"topic": "observer", "ts_ms": time.time() * 1000.0,
                         "payload": {"kind": "brain", "label": f"probe {n}"}})
        time.sleep(0.2)
    asyncio.run(until(lambda: len(_probe_rows()) == 50, "the 50-row backlog written", timeout_s=10))
    assert sum(sizes) == 50 and len(sizes) <= 3, f"one commit per row again: {sizes}"
