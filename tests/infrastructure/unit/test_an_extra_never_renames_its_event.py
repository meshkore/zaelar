"""An event's `extra` never renames the event (refactor2710-99 finding (a), fixed in refactor2710-06e).

`voice/observer.emit` built the event and then poured `extra` over it, so a field named `kind` — a memory pill's kind,
a provider cooldown's kind, a harness goal's kind — replaced the event's own kind: the memory write reached the Master
as kind `result`, a family it could not classify. A colliding identity key is now kept beside, as `extra_<key>`.
"""
from __future__ import annotations

from voice import observer


def test_a_kind_in_extra_stays_beside_the_events_own(monkeypatch):
    ev = {"kind": "memory", "label": "píldora escrita · fact", "text": "", "role": "system"}
    observer._merge(ev, {"kind": "fact", "label": "x", "layer": "write", "i": 9})
    assert ev["kind"] == "memory" and ev["label"] == "píldora escrita · fact"
    assert ev["extra_kind"] == "fact" and ev["extra_label"] == "x" and ev["extra_i"] == 9 and ev["layer"] == "write"


def test_the_recorded_event_keeps_its_kind(monkeypatch):
    import bus
    got = []
    monkeypatch.setattr(bus, "emit_sync", lambda topic, payload: got.append(payload), raising=False)
    observer.emit("memory", "píldora escrita · request", role="system", extra={"kind": "request", "layer": "write"})
    mine = [e for e in got if isinstance(e, dict) and e.get("label") == "píldora escrita · request"]
    assert mine and all(e["kind"] == "memory" and e["extra_kind"] == "request" for e in mine), mine
