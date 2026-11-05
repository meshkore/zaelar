"""Each act through the worker bridge is said ONCE, by the door (V2-851 F2, §15c/§15f).

`/api/worker/act` emitted nothing: the battery read a worker's acts through the doors they happened to reach. Now the
door emits one `worker_act` event {task_id, act, door, outcome} per act, whatever its outcome — the reader
`probe.bridge_acts` prefers it. `decide` is a known act (its denial message lists it).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest


@pytest.fixture
def door(monkeypatch):
    from nucleo.cli import worker_api
    from voice import observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: seen.append((kind, label, kw.get("extra") or {})))
    rec = SimpleNamespace(task_id="e1", uid="", started=time.time(), depth=0, trace_id="t-1", surface="", sheet="",
                          native_sid="", waiting_on="", ask="", ask_corr="", parked=False, mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    return SimpleNamespace(api=worker_api, seen=seen)


@pytest.mark.parametrize("action, payload, outcome, door_name", [
    ("no_such_act", {}, "denied", "no_such_act"),
    ("use_tool", {"tool": "authenticate_web"}, "denied", "use_tool:authenticate_web"),
    ("files", {}, "ran", "files"),
    ("propose_rule", {"sentence": "nunca por whatsapp"}, "asked", "propose_rule"),
])
def test_one_event_per_act_with_its_outcome(door, action, payload, outcome, door_name):
    asyncio.run(door.api.worker_act(task_id="e1", token="t", action=action, payload=payload))
    mine = [e for e in door.seen if e[0] == "worker_act"]
    assert len(mine) == 1
    ex = mine[0][2]
    assert (ex["act"], ex["door"], ex["outcome"], ex["session"]) == (action, door_name, outcome, "e1")
    assert ex["trace"] == "t-1"


def test_decide_is_a_known_act():
    from nucleo.cli.worker_policy import _KNOWN_ACTS, deny_reason
    assert "decide" in _KNOWN_ACTS and "decide" in deny_reason("nope", {})
