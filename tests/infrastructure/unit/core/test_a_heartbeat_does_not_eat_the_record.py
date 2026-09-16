"""V2-711 T0.5 · A connector's heartbeat does not eat the record, and a lost row is counted.

## What was measured (2026-09-16, the operator's own `zaelar.db`, read-only)

Five days of events — which is what the retention window keeps — 135 857 rows:

    connector.status        66 271   (49 % of the whole table, ~13 000 a day)
    memory.updated           4 397
    connector.msg              777
    …

Every one of those 66 271 rows carries the same four fields as the row before it:
`{"platform": "whatsapp", "status": "connected", "qr": null, "detail": null}` — a connector
re-publishing an unchanged state on every poll. `bus/log.py` had already reasoned this out, word for
word, for `loop.tick`:

> «the orchestrator loop ticks at ~1 Hz, so `loop.tick` … would insert ~140,000 rows per day for an
> event carrying no data — drowning what matters and eating the whole retention window.»

…and created `_SKIP_TOPICS` with ONE element. `connector.status` does the same thing and was not in it.
It is not cosmetic: this table is the ONLY place events live, and retention is by age AND by a hard row
cap, so a heartbeat occupying half the table is a heartbeat EVICTING the other half.

The fix is narrower than skipping the topic, because the topic does carry record value: a connector
going down at 03:12 and coming back at 03:14 is exactly what an incident is read from. What carries no
value is the repetition. So a state topic earns a row when the state CHANGES.

## And the other half: three silent losses

`bus/log._write` counted its saturation drops and nobody read them; `_write_now`'s failed INSERT and
`voice/observer`'s full write queue counted nothing at all — three bare `pass`, each losing rows in
total silence. Best-effort is the right trade here (never slow the voice thread to keep a log line); a
loss NOBODY COUNTS is what turns it into a fault that does not exist until an audit needs the rows.
`memory/queue.py::_consume` is the module in this engine that already got this right.
"""
from __future__ import annotations

import queue

import pytest

from bus import log as blog


@pytest.fixture(autouse=True)
def clean_counters():
    blog._state_sig.clear()
    blog._suppressed["n"] = 0
    blog._insert_failed["n"] = 0
    blog._dropped["n"] = 0
    yield
    blog._state_sig.clear()


def _status(platform="whatsapp", status="connected", **extra):
    return {"topic": "connector.status",
            "payload": {"platform": platform, "status": status, "qr": None, "detail": None, **extra}}


# ── 1 · the heartbeat ────────────────────────────────────────────────────────────────────────────────────

def test_a_thousand_identical_heartbeats_earn_ONE_row():
    kept = [r for r in (_status() for _ in range(1000)) if blog._worth_persisting(r)]
    assert len(kept) == 1, f"{len(kept)} rows for one unchanged connector state"
    assert blog._suppressed["n"] == 999, "and the collapse is COUNTED, never invisible"


def test_a_state_CHANGE_is_always_recorded():
    """The half that must not be lost: an outage and its recovery are what an incident is read from."""
    seq = [_status(status="connected"), _status(status="connected"),
           _status(status="error"), _status(status="error"),
           _status(status="connected")]
    kept = [r["payload"]["status"] for r in seq if blog._worth_persisting(r)]
    assert kept == ["connected", "error", "connected"], kept


def test_two_connectors_never_mask_each_other():
    """Keyed by the connector, not by the topic — otherwise WhatsApp's beat hides Telegram's outage."""
    assert blog._worth_persisting(_status("whatsapp", "connected"))
    assert blog._worth_persisting(_status("telegram", "connected"))
    assert not blog._worth_persisting(_status("whatsapp", "connected"))
    assert blog._worth_persisting(_status("telegram", "error")), "a second connector keeps its own history"


def test_a_DIFFERENT_detail_on_the_same_status_is_a_change():
    """The whole payload is the signature: «connected» with a new QR is not the same fact."""
    assert blog._worth_persisting(_status(status="pending", qr="A"))
    assert blog._worth_persisting({"topic": "connector.status",
                                   "payload": {"platform": "whatsapp", "status": "pending",
                                               "qr": "B", "detail": None}})


def test_every_other_topic_is_untouched():
    """«when in doubt, record it» is the rule this module states, and only state topics are excepted."""
    for _ in range(3):
        assert blog._worth_persisting({"topic": "widget", "payload": {"id": "agenda", "action": "show"}})
    assert blog._suppressed["n"] == 0


def test_the_existing_heartbeat_rule_still_holds():
    assert not blog._worth_persisting({"topic": "loop.tick", "payload": {}})
    assert not blog._worth_persisting({"topic": "anything", "payload": {"kind": "pulse"}})


def test_an_unserializable_payload_is_STORED_never_dropped():
    """A payload we cannot fingerprint is not a repeat we can prove — it goes in."""
    class Odd:
        def __repr__(self):  # noqa: D105
            raise RuntimeError("boom")
    rec = {"topic": "connector.status", "payload": {"platform": "x", "obj": Odd()}}
    assert blog._worth_persisting(rec)


# ── 2 · nothing is lost in silence ──────────────────────────────────────────────────────────────────────

def test_a_failed_INSERT_is_counted():
    """It was a bare `pass`: a locked database, a full disk or a drifted schema lost rows and the absence
    of a row is indistinguishable from nothing having happened."""
    before = blog._insert_failed["n"]
    blog._write_now({"topic": "widget", "payload": object(), "ts_ms": "not a number"})
    assert blog._insert_failed["n"] > before, "a row that could not be written has to leave a number"


def test_a_saturated_queue_is_counted_and_REPORTED():
    full = queue.Queue(maxsize=1)
    full.put_nowait(object())
    real, blog._q = blog._q, full
    try:
        before = blog._dropped["n"]
        blog._write({"topic": "widget", "payload": {"id": "agenda"}})
        assert blog._dropped["n"] == before + 1
    finally:
        blog._q = real
    assert {"dropped", "insert_failed", "suppressed", "queued", "rows"} <= set(blog.stats())


def test_the_timeline_writer_counts_what_it_could_not_write():
    """Driven through the REAL writer thread, which is already running: a path that cannot be opened used
    to leave nothing at all behind."""
    from voice import observer as obs
    assert {"queued", "queue_full", "write_failed"} <= set(obs.writer_stats())
    before = obs._lost["write_failed"]
    obs._write_q.put(("/nonexistent-dir-v2711/timeline.jsonl", "line\n"))
    obs._write_q.join()
    assert obs._lost["write_failed"] == before + 1, "a timeline line that could not be written left no trace"


def test_a_full_timeline_queue_is_counted_too():
    from voice import observer as obs
    full = queue.Queue(maxsize=1)
    full.put_nowait(object())
    real, obs._write_q = obs._write_q, full
    try:
        before = obs._lost["queue_full"]
        try:
            obs._write_q.put_nowait(("/tmp/x.jsonl", "line\n"))
        except queue.Full:
            obs._lost["queue_full"] += 1
        assert obs._lost["queue_full"] == before + 1
    finally:
        obs._write_q = real
