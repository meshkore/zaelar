"""The task battery's readers name the mouth of every wall line and record red per named assertion (V2-851 F0).

The battery (`tests/agent_headless/e2e/task_battery/`) is the contract of the refactor: it asserts the doors a flow
reached, the `tasks` row and the lines on the wall — never the judge. These readers are what make that true, so they
are pinned here without an engine: a line's source is read from the event, and a BASELINE run passes only when the
case is red on the assertion it names (red for the right reason).
"""
from __future__ import annotations

import pytest

from tests.agent_headless.e2e.task_battery.probe import Check, line_source


@pytest.mark.parametrize("ev, src", [
    ({"kind": "brain", "label": "💬 chat (canal de texto)", "payload": {"wall": "agent"}}, "reply"),
    ({"kind": "brain", "label": "💬 chat (canal de texto)", "payload": '{"wall": "you"}'}, ""),
    ({"kind": "brain", "label": "🗣 the turn's follow-up", "payload": {"wall": "zaelar"}}, "follow_up"),
    ({"kind": "brain", "label": "🗣 reply: the verdict's line", "payload": {}}, ""),
    ({"kind": "notify", "label": "🔔 Conector", "payload": {"title": "Conector"}}, "notify"),
    ({"kind": "notify", "label": "🔔 zaelar", "payload": {"title": "zaelar", "task_id": "t1"}}, "say"),
    ({"kind": "reminder", "label": "🔔 zaelar", "payload": {"title": "zaelar", "key": "cron:1"}}, "notice"),
    ({"kind": "widget", "label": "🔔 widget diag", "payload": {"title": "x"}}, ""),
    ({"kind": "ask", "label": "❓", "payload": {"ask_id": "a1"}}, "ask"),
    ({"kind": "brain", "label": "jev read canvas", "payload": {}}, ""),
])
def test_every_wall_line_names_its_mouth(ev, src):
    assert line_source(ev) == src


def test_a_case_is_red_on_its_first_named_assertion():
    chk = Check("c")
    chk.that("a", True)
    chk.that("b", False, "why")
    chk.that("c", False)
    assert chk.first_red == "b"
    with pytest.raises(AssertionError, match="RED on «b»"):
        chk.done()


def test_a_baseline_passes_only_red_for_the_named_reason():
    red_right = Check("c")
    red_right.that("question on screen", False)
    red_right.done(expected_red="question on screen")            # red for the right reason: passes

    red_wrong = Check("c")
    red_wrong.that("one line on the wall", False)
    with pytest.raises(AssertionError, match="wrong reason"):
        red_wrong.done(expected_red="question on screen")

    green = Check("c")
    green.that("question on screen", True)
    with pytest.raises(AssertionError, match="does not measure"):
        green.done(expected_red="question on screen")


def test_bridge_acts_prefers_the_doors_own_event_and_keeps_the_old_readers():
    """V2-851 F2: the bridge emits ONE `worker_act` per act — the first-class source; the F0 readers stay as fallback."""
    from tests.agent_headless.e2e.task_battery.probe import bridge_acts
    act = {"kind": "worker_act", "label": "🖐 worker act",
           "payload": {"task_id": "row9", "session": "w9", "act": "widget_data", "door": "widget.data:x:y",
                       "outcome": "asked"}}
    step = {"kind": "task", "label": "· paso", "payload": {"id": "w9"}}
    assert bridge_acts([step, act], "w9") == [act]
    assert bridge_acts([step, act], "row9") == [act]
    assert bridge_acts([step], "w9") == [step]


def test_the_task_that_asked_is_the_one_resumed():
    from tests.agent_headless.e2e.task_battery.probe import same_task_resumed
    worker = {"id": "t1", "kind": "generic", "session_id": "s1"}
    assert same_task_resumed(worker, {"id": "t1", "session_id": "s1"})
    assert not same_task_resumed(worker, {"id": "t1", "session_id": "s2"})        # a worker resumes by its session
    inline = {"id": "r1", "kind": "inline", "session_id": None}
    assert same_task_resumed(inline, {"id": "r1", "session_id": "w9"})            # its worker is born on the row
    assert not same_task_resumed(inline, {"id": "r2", "session_id": "w9"})        # never on another row
