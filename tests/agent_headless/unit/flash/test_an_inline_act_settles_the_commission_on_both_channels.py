"""The commission gate runs on the typed channel too (2026-10-15, live bench E3).

«send the invoice to quinn, tell him we're already trying inworld and he should book it» → the model called
`forward` AND `escalate_to_slowbrain`. The voice annuls that worker (`escalation_guard.settle_commission`: the brief
read `handle_inline`, the turn acted, the reply promised nothing); the old text channel launched it beside the send —
a worker free to send the same mail again. The typed channel now runs the voice turn itself
(`nucleo.cli.turn.run_turn`), so these cases drive it there.
"""
from __future__ import annotations

import asyncio

from tests.brain import harness as H

SAID = "send the invoice to quinn, tell him we're already trying inworld and he should book it"
ESCALATE = {"name": "escalate_to_slowbrain", "args": {"request": "forward the Inworld invoice to Quinn"}}
FORWARD = {"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "forward",
                                           "payload": {"contact": "Quinn", "text": "book it"}}}


def _turn(brief: dict, tools: list) -> dict:
    case = {"id": "commission", "lang": "en", "phrase": SAID, "source": "test", "screen": {"open": ["mensajeria"]},
            "expect": "talk", "brief": brief, "model": {"say": "Done.", "tools": tools}}
    with H.Isolated("en") as iso:
        iso.seed(case)
        from nucleo.cli import turn
        try:
            return asyncio.run(turn.run_turn(SAID, sid="commission", ingest=False))
        finally:
            turn.reset("commission")


def _spawned(res: dict) -> bool:
    return any(e.get("door") == "worker.spawn" for e in res.get("consequences") or [])


def test_an_act_on_a_card_read_inline_launches_no_worker_beside_it():
    res = _turn({"escalate_or_inline": ("handle_inline", 0.95)}, [ESCALATE, FORWARD])
    assert res["action"].startswith("widget_data"), res
    assert not _spawned(res), res["consequences"]


def test_a_brief_that_escalates_keeps_the_worker():
    """The same rule the voice runs — an act covers a promise (`reply_promises`), so only the brief keeps a worker."""
    for brief in ({"escalate_or_inline": ("escalate", 0.95)}, {"escalate_or_inline": ("handle_inline", 0.3)}):
        res = _turn(brief, [ESCALATE, FORWARD])
        assert res["action"] == "escalate", (brief, res)


def test_a_worker_alone_is_left_to_the_turn():
    res = _turn({"escalate_or_inline": ("handle_inline", 0.95)}, [ESCALATE])
    assert res["action"] == "escalate", res


def test_a_carried_out_sure_order_settles_a_commission_the_brief_did_not_judge():
    """Live bench E3: the escalate key missing from the brief, `forward` sure at 0.74 under an order at 1.00 — the act
    the turn ran is the commission. A sure «escalate» (a compound turn) keeps its worker."""
    brief = {"screen_action": ("mensajeria:forward", 0.74), "request_type": ("order", 1.0)}
    res = _turn(brief, [ESCALATE, FORWARD])
    assert res["action"].startswith("widget_data") and not _spawned(res), res
    res = _turn(dict(brief, escalate_or_inline=("escalate", 0.95)), [ESCALATE, FORWARD])
    assert res["action"] == "escalate", res
