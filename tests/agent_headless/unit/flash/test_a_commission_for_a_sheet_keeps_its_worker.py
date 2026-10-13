"""A commission whose deliverable is a SHEET is never replaced by one call on the errand's instruments (node 2.603).

Two «Done.» of 2026-10-14, both the text channel's ack over a repaired call that replaced the commission:
  · compare-insurance-quotes EN, turn 1: «can you compare a few insurers…?» (brief: escalate · lista) → the promise
    repair ran `navegador:search` and dropped «On it — I'll pull together a comparison…» → «Done.», no worker.
  · best-plumber-same-day EN, turn 10: «I need to know if any of them are top-rated and can actually come today»
    (escalate · lista, verdict `results:criteria`) → the V2-770 rung ran `results:progress` → «Done.», and his
    refinement never reached the live worker.
The rung keeps its job on a card that holds his data (`agenda:cancel_meeting`), and with no sure verdict.
"""
from __future__ import annotations

import asyncio
import inspect
import threading

import pytest

from nucleo.flash import act_repair, commission_keep


def _brief(route: str = "escalate", surface: str = "lista") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [], "_call_id": "t",
            "result": {"escalate_or_inline": {"choice": route, "confidence": 1.0},
                       "errand_surface": {"choice": surface, "confidence": 1.0}}}


@pytest.fixture
def repair_calls(monkeypatch):
    calls: list = []

    async def _promise(operator_text, reply, widget_id, spec=None, *, window=None):
        calls.append(widget_id)
        return {"widget_id": widget_id, "action": "search" if widget_id == "navegador" else "progress", "payload": {}}
    monkeypatch.setattr(act_repair, "call_for_promise", _promise)
    return calls


def _repair(widget_id: str, brief, verdict: str = ""):
    return asyncio.run(act_repair.call_for_promise_or_order(
        "can you compare a few insurers and see which one's actually worth it?",
        "On it — I'll pull together a comparison of insurers for you.", widget_id, verdict, brief=brief))


def test_the_insurance_comparison_is_not_a_browser_search(repair_calls):
    assert _repair("navegador", _brief()) is None
    assert repair_calls == [], "the repair pass is not even asked"


def test_the_plumber_refinement_is_not_a_note_on_the_sheet(repair_calls):
    assert _repair("results::02e504-1", _brief(), verdict="criteria") is None
    assert _repair("documento", _brief(surface="informe")) is None
    assert repair_calls == []


def test_a_card_that_holds_his_data_still_repairs(repair_calls):
    assert _repair("agenda", _brief())["widget_id"] == "agenda"


def test_without_a_sure_route_to_a_worker_it_repairs_as_before(repair_calls):
    assert _repair("navegador", _brief(route="handle_inline"))["action"] == "search"
    assert _repair("navegador", _brief(surface="voz"))["action"] == "search"
    assert _repair("navegador", None)["action"] == "search"
    assert repair_calls == ["navegador"] * 3


def test_both_channels_hand_the_brief_to_the_rung():
    from nucleo.flash import post_stream_words, probe
    for mod in (probe, post_stream_words):
        src = inspect.getsource(mod)
        i = src.index("call_for_promise_or_order(operator_text")
        assert "brief=" in src[i:i + 400], f"{mod.__name__}: the rung is called without the turn's brief"


def test_the_rule_itself():
    assert commission_keep.keeps_the_worker(_brief(), "results")
    assert not commission_keep.keeps_the_worker(_brief(), "agenda")
    assert not commission_keep.keeps_the_worker(None, "navegador")
