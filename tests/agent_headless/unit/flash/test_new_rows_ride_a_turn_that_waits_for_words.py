"""After a first tail, NEW rows still ride a turn of his that waits to be told — whatever the reply's wording (node 2.602).

cheapest-monitor EN (2026-10-14, sandbox 010127-en). The first tail carried three power adapters. Then «ok sounds good,
keep me posted» got «Will do — I'll ping you the moment I've got real monitors to show.», and `delivery_repeat` held
the delivery («rows already delivered once, and this reply answers something of its own») because «I'll ping you»
is not in the wait vocabulary — with «Monitor AGEX 27" 4K — 179.99» never announced and in the prompt. The rows are
owed by HIS turn (the brief: `wants_words=tell`, not routed to a worker), not by how the reply happens to sound.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import delivery, delivery_repeat, live_blocks

FIRST = ["Nuevo Adaptador de CA Monitor… — 170", "Adaptador 19V para LG 27UK650-W… — 17.91",
         "19.5v3.3a Adapter for LG… — 26.35"]
LATER = FIRST + ["Monitor AGEX 27 pulgadas 4K UHD… — 179.99", 'LG 27UD68 27" IPS LED 4K UHD… — 20.6']
ERRAND = "27-inch, 4K, and new only — I don't want someone else's panel"
REPLY = "Will do — I'll ping you the moment I've got real monitors to show."


def _brief(words: str, route: str = "handle_inline") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [], "_call_id": "t",
            "result": {"wants_words": {"choice": words, "confidence": 1.0},
                       "escalate_or_inline": {"choice": route, "confidence": 1.0}}}


@pytest.fixture
def delivered_once(monkeypatch):
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: True)
    delivery.forget_announced()
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (ERRAND, FIRST[:n]))
    first = delivery.apply_to_reply("Ha, fair — I'll keep it tight.", [], heard_now="ok, just don't take forever lol")
    assert "Adaptador 19V" in first, first
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (ERRAND, LATER[:n]))


def test_keep_me_posted_gets_the_rows_it_was_never_told(delivered_once):
    out = delivery.apply_to_reply(REPLY, [], heard_now="ok sounds good, keep me posted", brief=_brief("tell"))
    assert "AGEX" in out and "27UD68" in out, out
    assert "Adaptador 19V" not in out, "what was announced is never announced again"


def test_without_a_verdict_the_reply_wording_still_decides(delivered_once):
    assert delivery.apply_to_reply(REPLY, [], heard_now="ok sounds good, keep me posted") == REPLY


def test_a_turn_that_orders_work_or_wants_an_act_keeps_its_reply(delivered_once):
    assert delivery.apply_to_reply(REPLY, [], heard_now="ok 👍", brief=_brief("act")) == REPLY
    assert delivery.apply_to_reply(REPLY, [], heard_now="look on Amazon too",
                                   brief=_brief("tell", route="escalate")) == REPLY


def test_the_rule_itself():
    assert delivery_repeat.waits_for_words(_brief("tell"))
    assert not delivery_repeat.waits_for_words(_brief("tell", route="escalate"))
    assert not delivery_repeat.waits_for_words(None)
