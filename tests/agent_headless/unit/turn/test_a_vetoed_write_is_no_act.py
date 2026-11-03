"""A write the model called that a veto kept unrun is not an act: the promise doors still settle the reply (V2-845).

Live 2026-11-03 (turn T2·4b62): the model called `agenda:add_meeting` and said «Lo apunto en tu agenda el 11 de
diciembre»; a licence clause kept the write unrun and showed the card instead, which set `acted` — so the V2-790 door
never opened, the second pass never ran, and the claim stood over an empty agenda until his third complaint.

Disarm: make `promise_kept.write_kept_unrun` return "" and the first test goes red; drop `before` in
`promise_repair.landed` and the second goes red.
"""
from __future__ import annotations

from nucleo.turn import promise_kept, promise_repair


def _call(wid, action):
    return {"name": "widget_data", "args": {"widget_id": wid, "action": action, "payload": {}}}


def test_a_write_a_veto_kept_unrun_leaves_the_turn_owing_its_promise():
    calls = [_call("agenda", "add_meeting")]
    assert promise_kept.write_kept_unrun(calls, {"v": None}) == "agenda"


def test_a_write_that_ran_a_lens_or_an_op_this_turn_owes_nothing():
    assert promise_kept.write_kept_unrun([_call("agenda", "add_meeting")],
                                         {"v": True, "ops": [("agenda", "add_meeting")]}) == ""
    assert promise_kept.write_kept_unrun([_call("agenda", "show_day")], {"v": None}) == "", "a lens is no write"
    assert promise_kept.write_kept_unrun([{"name": "close_widget", "args": {}}], {"v": None}) == ""


def test_a_repair_pass_swallowed_again_by_the_veto_is_not_landed(monkeypatch):
    events, outcome = [], {}
    acted = {"widget": True}                     # the veto of the model's own call already counted
    got = promise_repair.landed({"widget_id": "agenda", "action": "add_meeting", "payload": {}}, outcome,
                                run=lambda: None, acted=acted, data_done={"v": None}, escalate_req={"v": None},
                                emit=lambda *a, **k: events.append(a))
    assert got is None and outcome["kind"] == promise_kept.SWALLOWED


def test_a_repair_pass_that_writes_lands(monkeypatch):
    outcome, done = {}, {"v": None}
    call = {"widget_id": "agenda", "action": "add_meeting", "payload": {}}
    got = promise_repair.landed(call, outcome, run=lambda: done.update(v=True), acted={"widget": True},
                                data_done=done, escalate_req={"v": None}, emit=lambda *a, **k: None)
    assert got is call
