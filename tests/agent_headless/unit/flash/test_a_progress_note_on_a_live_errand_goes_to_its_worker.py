"""A `progress` note the TURN writes on a live errand's sheet goes to that errand's worker, and the reply says what
happens next — never a bare «Done.» (node 2.705).

search-buy-watch EN (2026-10-14, sandbox 102009-en): «the King Seiko hi-beat sounds good, same check though — running
and real photos. if it looks clean and well kept I'm in» → `results:progress {state: "comprobando el King Seiko…"}`
(a line in the sheet's summary tab) and «Done.». The worker was never told, and a conditional yes got a report of
nothing. `progress` is the worker's own report; from the turn it is his words for that worker.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import dispatch
from nucleo.flash import data_ops, widget_data_turn as W, worker_note_relay as R

HIS = "the King Seiko hi-beat sounds good, same check though — running and real photos. if it looks clean I'm in"
CALL = {"name": "widget_data", "args": {"widget_id": "results::cfae00-ls1", "action": "progress",
                                        "payload": {"state": "comprobando el King Seiko 5626-7041"}}}


@pytest.fixture
def watch(monkeypatch):
    sent, ran = [], []
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "2", "request": "Find me a vintage automatic Seiko for under $450.", "sheet": "cfae00-ls1",
         "waiting_on": ""}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: None)
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, msg: sent.append((which, msg)))

    async def _brain_action(wid, act, pl):
        ran.append((wid, act))
        return {"ok": True}
    monkeypatch.setattr("widgets.server_api.brain_action", _brain_action)
    return sent, ran


def test_the_text_channel_sends_his_words_and_says_what_follows(watch):
    sent, ran = watch
    parte = asyncio.run(W.execute([CALL], text=HIS))
    assert sent == [("2", HIS)], sent
    assert not ran, "the worker's summary is not written by the turn"
    line = W.spoken_for(parte, "Done.")
    assert "passed that on to «Find me a vintage automatic Seiko for under $450.»" in line, line
    assert "checks that first" in line and line != "Done."
    assert W.named_ack(parte, "Done.", HIS, asked=True) == line


def test_the_voice_channel_relays_at_the_same_door(watch):
    sent, ran = watch
    out = asyncio.run(data_ops.dispatch_and_report("results::cfae00-ls1", "progress", {"state": "x"}, text=HIS))
    assert out.get("relayed_to") and sent == [("2", HIS)] and not ran
    assert "checks that first" in R.voice_line([("results", "control", "progress")])


def test_any_other_op_runs_as_before(watch):
    sent, _ = watch
    assert R.relay("results::cfae00-ls1", "criteria", HIS) == [] and not sent
    assert R.relay("results::other-ls9", "progress", HIS) == [], "a sheet no live errand owns"
    assert R.voice_line([("results", "control", "detail")]) == ""
