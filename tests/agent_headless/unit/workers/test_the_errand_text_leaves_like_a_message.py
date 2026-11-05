"""The errand text leaves to a third-party agent like a message (V2-852 T14).

The first live session on the task engine: the worker sent his errand («a used Mercedes GLC…») to two agents the
oracle found, and the log shows `mesh_serve → ran` with no `consequence` and no consent event before it. The exit gate
ran the outbound scan and the class rule, and the class (`standard`, below `ask_at`) ran it. Sending his words to a
recipient he did not choose is what the message door asks about: the agent must be one his words name, or his standing
rule (`errand.mesh_serve`) or a mandate allows it; and every outcome is a `consequence` event (door `mesh.serve`).
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


def test_the_errand_text_to_an_agent_he_never_named_is_asked_and_recorded(door, monkeypatch):
    """V2-852 T14 — the first live session: the worker sent his errand to agents the oracle found, with no question
    and no event. An agent his words do not name is a recipient he did not choose: the message door's rule asks, and
    the exit is a `consequence` event whatever its verdict."""
    from nucleo import consequence
    seen = []
    monkeypatch.setattr(consequence, "_observe", lambda row: seen.append(row))
    _his_words(monkeypatch, "find me a used Mercedes GLC, diesel, under 30000 euros")
    got = _serve(door, "used Mercedes GLC 2021-22 diesel under 30000 EUR")
    assert got.get("status") == "pending" and "stayfinder" in door.api._ACTS[got["corr_id"]]["question"]
    assert [r["gate"] for r in seen if r["door"] == "mesh.serve"] == ["ask"]


def test_his_standing_allow_or_a_mandate_clears_the_recipient_question(door, monkeypatch):
    from nucleo import consent
    _his_words(monkeypatch, "find me a used Mercedes GLC")
    monkeypatch.setattr(consent, "class_policy", lambda key, scope=None: "allow" if "mesh_serve" in key else "")
    assert _serve(door, "used Mercedes GLC")["ok"]
    monkeypatch.setattr(consent, "class_policy", lambda key, scope=None: "never" if "mesh_serve" in key else "")
    got = _serve(door, "used Mercedes GLC")
    assert not got["ok"] and "nothing was sent" in got["error"]
