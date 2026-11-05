"""What a worker does is kept on its task, at the door; it asks to verify and never closes (V2-851 F2, §3 P1-2/§3b).

«Todo siempre está ahí disponible»: every act through the bridge leaves its artefact on the task row (`acts` slot,
including the act his yes ran), the worker's own files are slots of that row (`file_put` / `files`), and `verify`
reads the circuit's verdict against the end state the task declared without touching its state.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from types import SimpleNamespace

import pytest

from nucleo.circuit import ledger, spec


@pytest.fixture
def door(monkeypatch):
    from nucleo.cli import worker_api
    uid = ledger.born(f"kept-{uuid.uuid4().hex[:8]}", "busca tres hoteles en Lisboa", {})
    rec = SimpleNamespace(task_id="k1", uid=uid, started=time.time(), depth=0, trace_id="", surface="", sheet="",
                          native_sid="", waiting_on="", ask="", ask_corr="", parked=False, mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    return SimpleNamespace(api=worker_api, rec=rec, uid=uid)


def _act(d, action, payload=None):
    return json.loads(asyncio.run(d.api.worker_act(task_id="k1", token="t", action=action,
                                                   payload=payload or {})).body)


def test_every_act_through_the_door_is_recorded_on_its_task(door):
    _act(door, "file_put", {"name": "shortlist.md", "text": "1. Hotel A\n2. Hotel B"})
    _act(door, "no_such_act")                                            # a denied act leaves its trace too
    acts = ledger.artifact(door.uid, "acts")
    assert [a["act"] for a in acts] == ["file_put", "no_such_act"]
    assert acts[0]["ok"] and acts[0]["ref"].endswith("shortlist.md") and not acts[1]["ok"]


def test_a_task_file_is_a_slot_of_its_row(door):
    assert _act(door, "file_put", {"name": "notes.txt", "text": "Lisbon, 2 nights"})["ok"]
    assert ledger.artifact(door.uid, "file:notes.txt")["text"] == "Lisbon, 2 nights"
    assert _act(door, "files")["result"]["files"] == [{"name": "notes.txt", "chars": 16}]


def test_verify_reads_the_end_state_and_never_closes(door, monkeypatch):
    from nucleo.circuit import verify
    assert _act(door, "verify")["result"]["met"] is None                 # no end state declared: unreadable
    spec.persist(door.uid, {"done_when": {"widget": "results", "collection": "items", "expect": "present"}})
    monkeypatch.setattr(verify, "check", lambda dw, now=None: False)
    monkeypatch.setattr(verify, "missing", lambda dw, now=None: ["results: items present"])
    before = (ledger.get(door.uid) or {}).get("state")
    got = _act(door, "verify")["result"]
    assert got["met"] is False and got["missing"] == ["results: items present"]
    assert (ledger.get(door.uid) or {}).get("state") == before          # the circuit closes; verify writes nothing
