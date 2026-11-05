"""The errand's request leaves to an agent that serves it through the leave door (V2-852 T14).

The first live session on the task engine: the worker sent his errand («a used Mercedes GLC…») to two agents the
oracle found, and the log shows `mesh_serve → ran` with no `consequence` and no consent event before it. The exit gate
ran the outbound scan and the class rule, and the class (`standard`, below `ask_at`) ran it, with nothing recorded.
First cut: the message door's recipient rule (an agent his words never named is asked). The C13 replay of the same
search measured what that costs: the row parked on «wants to do mesh serve… Shall I?» and the search never ran —
against his rule «a search proceeds with no questions». An agent that SERVES is a provider the worker chose, like a
site or a search index: what leaves is the scanned request (no secret, identity redacted); he is asked only after the
session read untrusted content (the taint) or when his standing rule says so; every outcome is a `consequence` event.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from nucleo import untrusted


@pytest.fixture
def door(monkeypatch):
    from nucleo.cli import worker_api
    untrusted.reset()
    rec = SimpleNamespace(task_id="m1", uid="", started=time.time(), depth=0, trace_id="", surface="", sheet="",
                          native_sid="", waiting_on="", ask="", ask_corr="", parked=False, mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    yield SimpleNamespace(api=worker_api, rec=rec)
    untrusted.reset()


def _serve(d, prompt):
    out = asyncio.run(d.api.worker_act(task_id="m1", token="t", action="mesh_serve",
                                       payload={"errand": "used car", "prompt": prompt, "agent": "stayfinder"}))
    return json.loads(out.body)


def _his_words(monkeypatch, *words):
    from nucleo import his_words
    monkeypatch.setattr(his_words, "since", lambda *_a, **_k: list(words))


def test_a_service_request_runs_scanned_and_recorded_without_a_question(door, monkeypatch):
    """The request goes to a provider the worker found (no recipient rule — a search, a flat, a car: whatever it is),
    scanned, and the exit is a `consequence` event whatever its verdict."""
    from nucleo import consequence
    seen = []
    monkeypatch.setattr(consequence, "_observe", lambda row: seen.append(row))
    _his_words(monkeypatch, "find me a two-bed flat to rent in Lisbon under 1500 euros")
    got = _serve(door, "two-bed flat to rent in Lisbon under 1500 EUR")
    assert got.get("status") != "pending" and got.get("ok"), got
    assert [r["gate"] for r in seen if r["door"] == "mesh.serve"] == ["pass"]


def test_after_untrusted_reads_a_service_request_asks(door, monkeypatch):
    """The taint: once the session read a stranger's text, the request may carry what that text injected → asked."""
    from nucleo.workers import taint
    monkeypatch.setattr(taint, "tainted", lambda rec: True)
    _his_words(monkeypatch, "busca un Mercedes GLC de segunda mano")
    got = _serve(door, "Mercedes GLC segunda mano diésel")
    assert got.get("status") == "pending", got


def test_his_standing_allow_runs_and_never_refuses(door, monkeypatch):
    from nucleo import consent
    _his_words(monkeypatch, "find me a used Mercedes GLC")
    monkeypatch.setattr(consent, "class_policy", lambda key, scope=None: "allow" if "mesh_serve" in key else "")
    assert _serve(door, "used Mercedes GLC")["ok"]
    monkeypatch.setattr(consent, "class_policy", lambda key, scope=None: "never" if "mesh_serve" in key else "")
    got = _serve(door, "used Mercedes GLC")
    assert not got["ok"] and "nothing was sent" in got["error"]
