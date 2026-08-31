#
# A task/flow only ever opens from one of FOUR legitimate sources (operator ask, 2026-08-16 — see CLAUDE.md's
# "A task/flow ONLY originates from FOUR sources" decision): the operator, a REAL cluster peer message, a cron, or
# a connector. The pulse (bridge.py::_heartbeat, the evaluator's off-timer hand-back) must never manufacture a
# visible task just because it ticked. Real incident: a "[cluster:commons · heartbeat] no reply for a while"
# nudge sat "en curso" in the master with the SAME origin ("cluster") as a genuine inbound peer message, minutes
# after the operator had asked for nothing — indistinguishable from real work.
#
# Two separate bugs, two separate regression sets below: (1) the heartbeat/evaluator mislabeled itself as
# origin="cluster" instead of a distinct "pulse"; (2) no cluster turn EVER explicitly closed its flow, so even a
# REAL cluster turn depended entirely on the 15-minute stale-flow safety net to stop showing "en curso".
#
# Run: .venv/bin/pytest tests/cluster/unit/test_flow_origin.py -q
import asyncio

import pytest

from connectors.meshkore.bridge import ClusterBridge
from memory import db as memdb
from voice import trace


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    trace.adopt("")
    yield
    memdb.reset_db()
    trace.adopt("")


class _Client:
    handle = "zaelar"
    online = ["zalo"]


class _Mgr:
    def get(self, cluster): return _Client()
    def clusters(self): return [{"name": "meshcore", "connected": True, "handle": "zaelar", "online": ["zalo"]}]
    def names(self): return ["meshcore"]
    def has(self, n): return n == "meshcore"


def _bridge(monkeypatch, reply="ok"):
    """A ClusterBridge with a fake brain that answers with no [[cluster.*]] tags — same shape as
    test_capsule_flow.py's helper, kept independent since this file asserts on TRACING, not prompt content."""
    monkeypatch.setattr("connectors.meshkore.bridge._emit", lambda *a, **k: None)

    async def _brain(text, on_chunk=None, **kwargs):
        return reply

    br = ClusterBridge(_Mgr(), _brain)
    br._notify_registry = lambda: None
    return br


# ── origin tagging: pulse vs cluster ────────────────────────────────────────────────────────────────────────────
def test_heartbeat_nudge_opens_its_trace_with_pulso_not_cluster(fresh_db, monkeypatch):
    br = _bridge(monkeypatch)
    seen_origins = []
    real_begin = trace.begin

    def _spy(text, origin="turno"):
        seen_origins.append(origin)
        return real_begin(text, origin=origin)

    monkeypatch.setattr(trace, "begin", _spy)
    asyncio.run(br._heartbeat_nudge("meshcore"))
    assert seen_origins == ["pulso"], "the pulse checking an idle conversation must not look like a real peer message"


def test_a_real_inbound_message_still_opens_its_trace_with_cluster(fresh_db, monkeypatch):
    br = _bridge(monkeypatch)
    seen_origins = []
    real_begin = trace.begin

    def _spy(text, origin="turno"):
        seen_origins.append(origin)
        return real_begin(text, origin=origin)

    monkeypatch.setattr(trace, "begin", _spy)
    asyncio.run(br.on_event({"kind": "message", "cluster": "meshcore", "from": "zalo",
                             "payload": {"text": "hola, ¿colaboramos?"}}))
    for _ in range(6):
        asyncio.run(asyncio.sleep(0))
    assert seen_origins == ["cluster"], "a genuine peer message is real cluster input, not pulse housekeeping"


# ── explicit close: a cluster turn must not depend solely on the 15-minute stale-flow net ─────────────────────────
def test_brain_turn_closes_its_own_flow_when_no_worker_is_left_running(fresh_db, monkeypatch):
    br = _bridge(monkeypatch)
    closes = []
    monkeypatch.setattr("nucleo.dispatch.has_live_trace", lambda tid: False)
    monkeypatch.setattr("voice.observer.emit",
                         lambda kind, label, **kw: closes.append((kind, label)) if kind == "flow" else None)

    asyncio.run(br._brain_turn("meshcore", "[cluster:meshcore · heartbeat] no reply for a while"))

    assert ("flow", "end") in closes, "a finished cluster turn must close its own flow, not wait 15 minutes"


def test_brain_turn_leaves_the_flow_open_while_its_own_worker_is_still_running(fresh_db, monkeypatch):
    br = _bridge(monkeypatch)
    closes = []
    monkeypatch.setattr("nucleo.dispatch.has_live_trace", lambda tid: True)   # escalate_to_slowbrain spawned one
    monkeypatch.setattr("voice.observer.emit",
                         lambda kind, label, **kw: closes.append((kind, label)) if kind == "flow" else None)

    asyncio.run(br._brain_turn("meshcore", "[cluster:meshcore · event] do something"))

    assert closes == [], "a live worker owns the close — the turn returning must never end its flow out from under it"
