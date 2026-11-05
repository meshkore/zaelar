"""A peer's chatter in the commons is observed, not a task (V2-852 T17).

The first live session on the task engine: the commons conversation with a peer concluded (`[[cluster.done]]`), the
peer then sent another off-topic tip, and our one-line reply went through `_send`, which marked the cluster ENGAGED
(«has an open joint task»). Engaged, the heartbeat nudged the conversation five times and the evaluator ran once —
six model turns, each a flow in his session, and an error («paro con …») — over small talk nobody had asked for.

A joint task opens on HIS act (his turn's send, his connect); our own answer to a peer, written by the bridge's turn
(`_route_reply`), never opens one.

Disarm: make `_route_reply` dispatch with `engages=True` (or drop the `if engages:` in `_send`) → red.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def br(monkeypatch):
    from connectors.meshkore import bridge, send_gate
    monkeypatch.setattr(bridge, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(send_gate, "gate", lambda *a, **k: "send")
    sent = []

    class _Mgr:
        def has(self, name): return name == "commons"
        def get(self, name): return None
        def names(self): return ["commons"]
        def clusters(self): return [{"name": "commons", "online": ["wanderer"]}]
        async def send(self, name, to=None, text="", media=None): sent.append((name, to, text))

    b = bridge.ClusterBridge(_Mgr(), brain=None)
    b._now = lambda: 0.0
    b._notify_registry = lambda: None
    b.sent = sent
    return b


def _reply_to(peer):
    return f'Noted, thanks. [[cluster.send:commons]]{{"to":"{peer}","text":"Noted — nothing pending here."}}[[/cluster.send]]'


def test_our_answer_to_a_peer_opens_no_task(br):
    br._engaged["commons"] = False                        # the conversation concluded
    asyncio.run(br._route_reply(_reply_to("wanderer")))
    assert br.sent and br.sent[0][2].startswith("Noted"), "the reply still goes out"
    assert not br._engaged.get("commons"), "answering chatter re-opened a joint task: the heartbeat will nudge it"


def test_an_open_task_stays_open_through_our_replies(br):
    br._engaged["commons"] = True                         # he opened it
    asyncio.run(br._route_reply(_reply_to("wanderer")))
    assert br._engaged["commons"] is True


def test_his_send_opens_the_task(br):
    asyncio.run(br.dispatch("cluster.send", {"name": "commons", "data": {"to": "wanderer", "text": "can you check X?"}}))
    assert br._engaged["commons"] is True
