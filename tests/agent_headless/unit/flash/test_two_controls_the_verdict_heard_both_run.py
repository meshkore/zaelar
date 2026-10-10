"""«Unmute it and skip to the next one» runs BOTH controls when the turn's verdict heard both (V2-781).

Measured in `build-a-video-playlist-from-links` (ES, 2026-10-10 19:50): «súbele un poco el volumen que lo tengo
silenciado. Y ya pásate al siguiente.» → the model called `youtube:unmute {}` and `youtube:next {}`; only `unmute`
ran (the enumeration guard drops a second action on one card when neither names a target), and the reply said «Te
paso al siguiente». The turn brief's `screen_action` distribution had already read both in his sentence:
volume_up 0.52 · next 0.28 · unmute 0.20.

Driven through the real door both channels share (`data_ops.admite_data_op`) and the text channel's executor, with
the brief exactly as `jev.ask_many` hands it over. The enumeration it exists for is measured beside it: the same
two calls with a verdict that heard only one of them — or none — still run only the first.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import data_ops as RG
from nucleo.flash import turn_brief as tb


def _brief(probs: dict) -> dict:
    ev = threading.Event()
    ev.set()
    top = max(probs.items(), key=lambda kv: kv[1])
    return {"event": ev, "turn_id": "t", "open_ids": ["youtube"],
            "result": {tb.TARGET_KEY: {"choice": top[0], "confidence": top[1], "probabilities": probs}}}


MEASURED = {"youtube:volume_up": 0.52, "youtube:next": 0.28, "youtube:unmute": 0.20, "youtube:load": 0.0}


def _op(act, **payload):
    return {"widget_id": "youtube", "action": act, "payload": payload}


def test_two_controls_the_verdict_heard_both_enter():
    assert RG.admite_data_op(_op("next"), [_op("unmute")], _brief(MEASURED)) is True


def test_without_a_brief_the_enumeration_guard_holds():
    assert RG.admite_data_op(_op("next"), [_op("unmute")]) is False


def test_a_verdict_that_heard_only_one_is_still_a_menu():
    only_volume = {"youtube:volume_up": 0.9, "youtube:unmute": 0.08, "youtube:next": 0.02}
    assert RG.admite_data_op(_op("next"), [_op("unmute")], _brief(only_volume)) is False


def test_the_agenda_enumeration_still_does_not_run():
    """«muéstrame la agenda» → done/drop/snooze: the verdict hears a view, not three row actions."""
    probs = {"agenda:show_day": 0.9, "agenda:done": 0.03, "agenda:drop": 0.02}
    done = {"widget_id": "agenda", "action": "done", "payload": {"item": 1}}
    drop = {"widget_id": "agenda", "action": "drop", "payload": {"item": 1}}
    assert RG.admite_data_op(drop, [done], _brief(probs)) is False


@pytest.fixture
def rail(monkeypatch):
    ran = []

    async def _brain_action(wid, act, payload):
        ran.append((wid, act))
        return {"ok": True}
    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    from widgets import actions as _wa
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.FAST)
    from nucleo.flash import verdict_card as _vc
    monkeypatch.setattr(_vc, "retarget", lambda brief, wid, act, pl, order: (wid, act, pl))
    return ran


def test_the_text_channel_runs_the_next_it_was_dropping(rail):
    from nucleo.flash import widget_data_turn as WDT
    calls = [{"name": "widget_data", "args": _op("unmute")}, {"name": "widget_data", "args": _op("next")}]
    parte = asyncio.run(WDT.execute(calls, text="súbele el volumen que lo tengo silenciado y pásate al siguiente",
                                    brief=_brief(MEASURED)))
    assert rail == [("youtube", "unmute"), ("youtube", "next")], rail
    assert "descartadas" not in parte
