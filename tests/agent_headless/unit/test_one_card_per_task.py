"""One card per task (V2-852 T11, invariants I1 and I7).

Measured in the operator's session (2026-11-05): a GLC search was cancelled and relaunched; his screen kept TWO results
cards. The cancelled run's card stayed open and empty beside the relaunch's own, and the relaunch's own first show was
logged «non owner» (`errand:3` against `errand:abffbc-3`) — one task carried two names, so the owner rule could not be
armed without refusing a task its own card.

The rules restored, for any task and any widget:
  · a task is named by its row, whatever numbering signs the show (`worker:<n>` is the row `task_uid(n)`);
  · a card a LIVE task owns is never shown by another task — the arbiter refuses it (`non-owner`);
  · a card whose task ENDED is taken over by the next task of that widget — never refused, never counted;
  · his hands, the turn and the lifecycle are never refused by this rule;
  · a cancelled task's empty card closes with it; a card holding rows stays his to read.
"""
from __future__ import annotations

import pytest

from nucleo.acts import canvas, canvas_arbiter as arb, card_owner, surface_owner as so
from nucleo.dispatch import confirm

NOTHING = {"text": "", "turn_credit": True, "last_reply": "", "verdict": {}}


class Rec:
    def __init__(self, tid, uid, sheet=""):
        self.task_id, self.uid, self.sheet = tid, uid, sheet or uid


@pytest.fixture
def world(monkeypatch):
    for d in (so._CLAIMS, so._LAUNCHED, so._FLOW_SAID):
        d.clear()
    rows: list[dict] = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda kind, label, **kw: rows.append({"kind": kind, "label": label, **(kw.get("extra") or {})}))
    sessions: dict = {}
    monkeypatch.setattr("nucleo.dispatch._SESSIONS", sessions)
    pending: dict = {}
    monkeypatch.setattr(confirm, "_PENDING_CONFIRM", pending)
    monkeypatch.setattr("nucleo.circuit.ledger._boot_id", lambda: "b7")
    ledger: dict = {}
    monkeypatch.setattr("nucleo.circuit.ledger.get", lambda uid: ledger.get(uid))
    yield {"rows": rows, "sessions": sessions, "ledger": ledger, "pending": pending}


def _owner_rules(rows):
    return [r["rule"] for r in rows if r["kind"] == "owner"]


# ── one name per task ────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tid", ["3", "12"])
def test_a_workers_first_show_of_its_own_card_is_its_own_before_its_record_is_registered(world, tid):
    """The relaunch showed its sheet before the dispatcher registered its record, while its confirmation still held
    the box under its NUMBER: two names for one task, and the task was refused its own card."""
    world["pending"][tid] = {"sheet": f"b7-{tid}"}
    v = arb.decide("show", f"results::b7-{tid}", f"worker:{tid}")
    assert v.allow and v.rule == "task-owned", v
    so.on_show(f"results::b7-{tid}", f"worker:{tid}")
    assert _owner_rules(world["rows"]) == ["show"], "a task's own first show was counted as a non-owner's"


# ── a live task's card is its own ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("src", ["worker:9", "wall:9", "sheet:b7-9"])
def test_another_live_tasks_card_is_refused_at_the_door(world, src):
    world["sessions"]["4"] = Rec("4", "b7-4")             # a flat search, running
    world["sessions"]["9"] = Rec("9", "b7-9")             # a car search, running, with its own card
    v = arb.decide("show", "results::b7-4", src)
    assert not v.allow and v.rule == "non-owner" and v.evidence["owner"] == "errand:b7-4", v
    widget = []
    assert canvas.apply("show", "results::b7-4", src=src, request=NOTHING,
                        emit=lambda kind, label, extra=None, **k: widget.append(label)) is False
    assert widget == [], "a refused show must not put the card on his screen"
    assert arb.decide("show", "results::b7-9", "worker:9").allow, "…and its own card is never refused"


def test_his_hands_the_turn_and_the_lifecycle_are_never_refused_by_the_owner_rule(world):
    world["sessions"]["4"] = Rec("4", "b7-4")
    for src in ("user", "turn:T5·aa", "system", "recall:results::b7-4"):
        assert arb.decide("show", "results::b7-4", src).rule != "non-owner", src


# ── an ended task's card is taken over ───────────────────────────────────────────────────────────────────────

def test_a_new_task_takes_over_the_card_of_an_ended_one(world):
    world["ledger"]["b7-2"] = {"id": "b7-2", "sheet": "b7-2", "state": "cancelled"}   # ended: a record, not a holder
    world["sessions"]["3"] = Rec("3", "b7-3", sheet="b7-2")                               # inherited its box
    v = arb.decide("show", "results::b7-2", "worker:3")
    assert v.allow, f"a new task of the same widget was refused the card it inherits: {v}"
    so.on_show("results::b7-2", "worker:3")
    assert "non_owner_show" not in _owner_rules(world["rows"])


def test_a_widget_card_claimed_by_an_ended_task_passes_to_the_next_one(world):
    world["sessions"]["5"] = Rec("5", "b7-5")
    so.on_show("documento", "worker:5")
    world["sessions"].pop("5")                            # that task ended
    world["sessions"]["6"] = Rec("6", "b7-6")
    so.on_show("documento", "worker:6")
    assert _owner_rules(world["rows"]) == ["show", "show"], _owner_rules(world["rows"])
    assert so._CLAIMS["documento"]["owner"] == "errand:b7-6"


# ── a cancelled task's empty card closes with it ─────────────────────────────────────────────────────────────

@pytest.fixture
def sheet(monkeypatch):
    held: dict = {}
    monkeypatch.setattr("widgets.results.data.view_data", lambda sid="": {"empty": not held.get(sid)})
    closes: list = []
    monkeypatch.setattr("nucleo.acts.canvas.apply", lambda op, wid="", **kw: closes.append((op, wid, kw.get("src"))) or True)
    return held, closes


def test_a_cancelled_tasks_empty_card_closes_with_it(world, sheet):
    held, closes = sheet
    world["ledger"]["b7-2"] = {"id": "b7-2", "sheet": "b7-2"}
    assert card_owner.task_ended("b7-2", "cancelled") is True
    assert closes == [("close", "results::b7-2", "system:task-ended")]
    assert "orphan" in _owner_rules(world["rows"])


@pytest.mark.parametrize("state, rows, other_live", [
    ("cancelled", ["a flat in Valencia"], False),   # it holds rows: his to read
    ("done", [], False),                            # a finished task's card is its deliverable
    ("failed", [], False),
    ("cancelled", [], True),                        # another live task holds that card now
])
def test_a_card_that_is_still_his_or_anothers_stays(world, sheet, state, rows, other_live):
    held, closes = sheet
    world["ledger"]["b7-2"] = {"id": "b7-2", "sheet": "b7-2"}
    held["b7-2"] = rows
    if other_live:
        world["sessions"]["3"] = Rec("3", "b7-3", sheet="b7-2")
    assert card_owner.task_ended("b7-2", state) is False
    assert closes == []


def test_a_row_that_ends_on_the_bus_reaches_the_card_owner(monkeypatch):
    """The wiring, not the rule: `circuit._state_event` says `task.ended` on the bus and the card owner hears it
    (V2-852 T11 seam). Disarm: drop the sink and the call never arrives."""
    import bus
    seen = []
    monkeypatch.setattr(card_owner, "task_ended", lambda uid, state, **k: seen.append((uid, state)) or False)
    bus.reset()
    card_owner.subscribe()
    bus.emit_sync("task.ended", {"task_id": "abc-7", "state": "cancelled", "trace": "T1"})
    bus.emit_sync("task.other", {"task_id": "abc-8", "state": "cancelled"})
    assert seen == [("abc-7", "cancelled")]
