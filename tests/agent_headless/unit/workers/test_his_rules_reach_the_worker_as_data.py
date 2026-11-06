"""His rules reach a worker as DATA, and a rule it proposes is written only on his yes (V2-851 F2, §6).

The door stays the only authoritative reader (`consent.decide`, `rules/cascade`): the worker's brief carries «what he
said» so it looks in the right place, the bridge's `rules` act reads the rows that cover a path, and `propose_rule`
is a CONFIRM — the sentence goes through `rules.shape.write` only after his yes.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

import rules
from nucleo.workers import rules_bridge


@pytest.fixture
def his_rule():
    rules._reset_for_tests()
    row = rules.add("widget:mensajeria", "pref", rules.NOTE, "por telegram, nunca por whatsapp",
                    text="a Rowan escríbele siempre por telegram, nunca por whatsapp")
    yield row
    rules._reset_for_tests()


@pytest.fixture
def door(monkeypatch):
    from nucleo.cli import worker_api
    rec = SimpleNamespace(task_id="r1", uid="", started=time.time(), depth=0, trace_id="", surface="", sheet="",
                          native_sid="", waiting_on="", ask="", ask_corr="", parked=False, mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    return SimpleNamespace(api=worker_api, rec=rec)


def _act(d, action, payload):
    return json.loads(asyncio.run(d.api.worker_act(task_id="r1", token="t", action=action, payload=payload)).body)


def test_the_brief_carries_his_rules_as_data(his_rule):
    from nucleo.workers.prompts.build import _build_prompt
    assert "telegram" in rules_bridge.brief_block()
    assert "telegram" in _build_prompt("escribe a Rowan", "", True)
    assert "telegram" not in _build_prompt("escribe a Rowan", "", False)       # an untrusted worker only reasons


def test_the_rules_act_reads_what_covers_the_path(his_rule, door):
    got = _act(door, "rules", {"widget": "mensajeria", "action": "send_to"})
    assert got["ok"] and any("telegram" in r["text"] for r in got["result"]["rules"])
    other = _act(door, "rules", {"widget": "agenda"})["result"]["rules"]
    assert not any("telegram" in r["text"] for r in other)                    # a rule of another card is not here
