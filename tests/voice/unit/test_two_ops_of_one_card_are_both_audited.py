"""Two DIFFERENT ops on one card within 150 ms both reach the audit; only an identical repeat collapses (2026-10-14).

Sandbox 20261014-121305-en, turn 12: the model made five agenda calls in one turn. The flood guard keyed a widget
event on (label, id, src) only, so the third call — `move_meeting` on the piano series, 14 ms after a
`move_meeting` on the dentist — vanished from the timeline, and the one op that moved the whole series to Wednesday
could not be seen anywhere. The key now carries the action and its payload.
"""
from __future__ import annotations

from voice import observer


def _widget_rows(label: str) -> list[dict]:
    return [e for e in observer.debug_events("widget") if e.get("label") == label]


def test_two_payloads_of_one_action_are_two_rows():
    observer._dedup.clear()
    before = len(_widget_rows("data:move_meeting"))
    observer.emit("widget", "data:move_meeting", extra={"id": "agenda", "src": "probe", "action": "move_meeting",
                                                        "payload": {"title": "dental checkup", "newTime": "11:30"}})
    observer.emit("widget", "data:move_meeting", extra={"id": "agenda", "src": "probe", "action": "move_meeting",
                                                        "payload": {"title": "piano", "newDate": "2026-10-21"}})
    assert len(_widget_rows("data:move_meeting")) == before + 2


def test_the_same_op_repeated_inside_the_window_still_collapses():
    observer._dedup.clear()
    before = len(_widget_rows("data:set_volume"))
    for _ in range(3):
        observer.emit("widget", "data:set_volume", extra={"id": "musica", "src": "flash", "action": "set_volume",
                                                          "payload": {"level": 40}})
    assert len(_widget_rows("data:set_volume")) == before + 1
