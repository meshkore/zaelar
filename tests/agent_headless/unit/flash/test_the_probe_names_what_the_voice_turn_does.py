"""The text probe answers a hard interrupt and `reopen_task` the way the voice turn does (V2-778 F2-22, 2026-10-02).

`hard_turn.handle` (voice) lets the turn continue when a short stop is aimed at a live WORKER («para eso» → the model
calls `stop_worker`) and when the close or the stop was not the whole request («cierra todo y ábreme la agenda»,
V2-688). The probe mapped every hard interrupt straight to `canvas:close` / `chat`, so the bank of brain cases — which
runs on the probe — saw the worker keep running and the second order thrown away. Found by the voice/probe import
ratchet (`hard_turn` was an «owed» voice-only module).
"""
from __future__ import annotations

import asyncio

from nucleo.flash import hard_turn as HT
from nucleo.flash import probe_decide as PD
from nucleo.flash import router_guards as RG


class _Sess:
    window: list = []
    last_action = ""


def _action(text, hard, calls):
    blk = asyncio.run(PD.name_the_action(_hard=hard, _router=RG, _tbrief=None, _vault_gate=None, ingest=None,
                                         names={c["name"] for c in calls}, sess=_Sess(), tags=[], text=text,
                                         tool_calls=calls))
    return blk.get("action", "")


def test_a_bare_close_still_closes():
    assert _action("cierra todo", "close", []) == "canvas:close"


def test_a_stop_aimed_at_a_live_worker_names_stop_worker(monkeypatch):
    monkeypatch.setattr(HT, "is_worker_stop", lambda text, hard: True)
    assert _action("para eso", "stop", [{"name": "stop_worker", "args": {}}]) == "stop_worker"


def test_a_close_that_was_not_the_whole_order_names_the_rest(monkeypatch):
    monkeypatch.setattr(HT, "remainder", lambda text, hard: "ábreme la agenda")
    calls = [{"name": "show_widget", "args": {"widget_id": "agenda"}}]
    assert _action("cierra todo y ábreme la agenda", "close", calls) != "canvas:close", \
        "the probe threw away the order the close came with"


def test_the_remainder_is_the_voice_turns_own():
    """Not a copy: `handle` and the probe read the SAME function, so the two cannot drift again."""
    import inspect
    assert "remainder(text, hard)" in inspect.getsource(HT.handle)
    assert "is_worker_stop(text, hard)" in inspect.getsource(HT.handle)


# ── reopen_task (V2-728) — the probe had no branch for it, so «lo del piso que te dije» named nothing ──────────

def test_reopen_task_names_the_errand_it_found(monkeypatch):
    from nucleo.flash import task_recall as TR
    monkeypatch.setattr(TR, "resolve", lambda q: {"ok": True, "task": {"id": "abc", "title": "piso"}})
    assert _action("ábreme lo del piso que te dije", None,
                   [{"name": "reopen_task", "args": {"query": "piso"}}]) == "canvas:show:results"


def test_reopen_task_over_several_errands_asks(monkeypatch):
    from nucleo.flash import task_recall as TR
    monkeypatch.setattr(TR, "resolve", lambda q: {"ok": False, "ask": [{"id": "a"}, {"id": "b"}]})
    assert _action("lo que te dije", None, [{"name": "reopen_task", "args": {}}]) == "clarify"
