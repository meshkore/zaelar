"""A meshcore reconnection is information with a backoff, not an error (V2-852 T18).

The first live session on the task engine: `meshcore: error · ConnectionClosedError: no close frame received or
sent` and, one second later, `✓ joined meshcore`. The client's loop repaired the link on its own, yet the status said
`error`, because a ConnectionClosed with no close frame fell to the catch-all reason. A link that drops (no frame) or
a network failure is `reconnecting` with `retry_in_s`; a refused handshake or a server close stays `error`.

Disarm: drop the `ConnectionClosed` branch in `MeshKoreClient._classify` → red.
"""
from __future__ import annotations

import asyncio

from websockets.exceptions import ConnectionClosedError

from connectors.meshkore import client as _client
from connectors.meshkore.client import MeshKoreClient


def _one_failure(monkeypatch, exc):
    """Run the client's loop for exactly one failed connection and return the status event it surfaced."""
    got = []

    def _connect(*a, **k):
        raise exc
    monkeypatch.setattr(_client, "connect", _connect)
    c = MeshKoreClient.__new__(MeshKoreClient)
    c.name, c.connected, c.online, c._ws, c._closing = "meshcore", True, set(), None, False
    c._url = lambda: "wss://example.invalid/ws"

    async def _sink(ev):
        got.append(ev)
        c._closing = True                     # one attempt only
    c._on_event = _sink
    asyncio.run(c._run())
    return got[0]


def test_a_dropped_link_is_reconnecting_with_its_backoff(monkeypatch):
    ev = _one_failure(monkeypatch, ConnectionClosedError(None, None))
    assert ev["status"] == "reconnecting" and ev["reason"] == "dropped", ev
    assert ev["retry_in_s"] is None or ev["retry_in_s"] > 0


def test_a_refused_handshake_is_still_an_error(monkeypatch):
    class _Refused(Exception):
        response = type("R", (), {"status_code": 403})()
    ev = _one_failure(monkeypatch, _Refused("forbidden"))
    assert ev["status"] == "error" and ev["reason"] == "auth_rejected", ev


def test_the_bridge_records_it_as_a_cluster_event_never_an_error(monkeypatch):
    from connectors.meshkore import bridge, journal
    seen = []
    monkeypatch.setattr(bridge, "_emit", lambda kind, label, **k: seen.append((kind, label, k.get("extra") or {})))
    monkeypatch.setattr(journal, "record", lambda *a, **k: None)
    br = bridge.ClusterBridge(manager=None, brain=None)
    br._notify_registry = lambda: None
    asyncio.run(br.on_event({"type": "status", "cluster": "meshcore", "status": "reconnecting", "reason": "dropped",
                             "detail": "ConnectionClosedError", "retry_in_s": 2.0}))
    (kind, label, extra), = seen
    assert kind == "cluster" and "error" not in label and extra["retry_in_s"] == 2.0
