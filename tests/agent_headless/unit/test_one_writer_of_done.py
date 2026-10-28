"""ONE writer of «done»: `circuit.settle` (refactor2710-02b T-02).

Five places closed a request: the spec's attest marked its own entry met, the pulse and the worker's ending wrote the
entry's status, the harness expired or met its goals in place, the data-op door wrote «unverifiable» on a replay, and
the inline row had its own settle. Each wrote a different subset (the status, the row, an event) — so a reader could
see an entry «met» whose row never moved, or a row settled with no event. Now the readers only READ (`spec.attest`,
`harness.verify` return what they saw), and whoever acts on what they read calls the one door, which writes the entry,
its row and one `verdict` event together.

Disarm: make `circuit.settle` return before writing → every test below goes red.
"""
from __future__ import annotations

import pytest

from nucleo import circuit
from nucleo.circuit import spec


@pytest.fixture
def seen(monkeypatch):
    from voice import observer
    events: list = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: events.append(
        {"kind": kind, "label": label, **(extra or {})}))
    return events


@pytest.fixture
def rows(monkeypatch):
    store: dict = {}

    class _TS:
        def task_get(self, uid):
            return store.get(uid)

        def task_patch(self, uid, **f):
            store[uid].update(f)
    from nucleo.circuit import ledger
    monkeypatch.setattr(ledger, "store", lambda: _TS())
    return store


def _verdicts(events):
    return [e["verdict"] for e in events if e["kind"] == "verdict"]


def test_the_door_writes_the_entry_its_row_and_one_event(seen, rows):
    rows["r1"] = {"id": "r1", "verdict": "", "trace_id": "t1"}
    e = {"status": "started", "row": "r1", "trace": "t1"}
    circuit.settle(e, verdict="met", now=100.0)
    assert e["status"] == "met" and e["met_at"] == 100.0
    assert rows["r1"]["verdict"] == "met" and rows["r1"]["state"] == "done"
    assert _verdicts(seen) == ["met"], "one event per settle, not one per record it wrote"


def test_an_entry_with_no_row_still_says_its_verdict(seen):
    g = {"status": "started", "source": "shown", "trace": "t2"}
    circuit.settle(g, verdict="unverifiable")
    assert g["status"] == "unverifiable" and _verdicts(seen) == ["unverifiable"]
    assert seen[-1]["trace"] == "t2"


def test_a_non_ending_writes_nothing(seen, rows):
    rows["r2"] = {"id": "r2", "verdict": "", "state": "running"}
    e = {"status": "started", "row": "r2"}
    for name in ("started", "asked", "skipped", "nonsense"):
        circuit.settle(e, verdict=name)
    assert e == {"status": "started", "row": "r2"} and rows["r2"]["state"] == "running" and not _verdicts(seen)


def test_the_spec_reader_reads_and_never_closes(monkeypatch, seen):
    from nucleo.circuit import verify
    monkeypatch.setattr(verify, "check", lambda done_when, now=None: True)
    e = {"status": "started", "done_when": {"widget": "agenda", "field": "x", "is": "y"}, "id": "s1"}
    assert spec.attest(e) is True
    assert e["status"] == "started", "attest is a reader: closing is the door's"
    assert not _verdicts(seen)


def test_the_harness_expiry_settles_through_the_door(monkeypatch, seen):
    from nucleo.circuit import harness
    g = {"status": "started", "source": harness.SOURCE, "born": 1.0}
    monkeypatch.setattr(spec, "open_specs", lambda now=None: [g])
    harness._expire(now=harness.TTL_S + 10)
    assert g["status"] == "unverifiable" and g["why"] == "expired" and _verdicts(seen) == ["unverifiable"]
