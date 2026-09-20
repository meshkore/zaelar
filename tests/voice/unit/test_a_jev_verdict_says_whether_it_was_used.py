"""Node 3.69 — a decision is attributable, and the timeline says whether anybody USED it.

V2-726 A6a. The audit asked the only question that decides whether any of this is worth its round
trip — «which verdict changed which outcome?» — and the engine could not answer it:

  · the brief's event reported `max()` confidence across its questions, so one sure canvas verb hid
    three unsure ones behind a 0.99 and no consumer's own threshold could be checked;
  · `jev.read` already computed `info["used"]` and EVERY consumer threw it away, so the record said
    Jev was ASKED and never whether the answer moved anything;
  · no handle carried an id, so two events in a real session could only be attributed to the same
    turn by their timestamps — temporal, not a join, which is not evidence;
  · `select_many` returned `[]` for «nothing fits», «no key», «network down» and «switched off»,
    which are two answers and two absences, and they call for opposite behaviour.

What this file pins is that each of those now produces a DISTINCT, bounded record. It does not
claim the verdicts are good — that is A6b's report, against adjudicated cases.
"""
from __future__ import annotations

import threading

import pytest

from nucleo import jev
from nucleo.flash import turn_brief as tb


@pytest.fixture
def events(monkeypatch):
    """Capture the timeline instead of writing it. A test never touches the operator's real log —
    and this one would write into it twice per read (V2-726 §7.3 rule 2, paid for once already)."""
    seen: list[dict] = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda kind, label, text="", role="", extra=None:
                        seen.append({"kind": kind, "label": label, "text": text,
                                     "extra": dict(extra or {})}))
    jev.reset_read_events()
    return seen


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "k-for-tests")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    jev.reset_breaker()

    class _Wire:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.answers: dict[str, tuple[str, float]] = {}

        def __call__(self, state, questions, timeout_s):
            self.calls.append({"state": state, "questions": questions})
            return {"answers": {k: {"choice": (a := self.answers.get(k, (next(iter(q["criteria"])), 0.95)))[0],
                                    "confidence": a[1], "probabilities": {a[0]: a[1]}}
                                for k, q in questions.items()}}

    w = _Wire()
    monkeypatch.setattr(jev, "_post_many", w)
    return w


def _settle(handle, t=2.0):
    if handle and handle.get("event"):
        handle["event"].wait(t)
    return handle


# ── the ask: one event, every question's own confidence in it ────────────────────────────────────
def test_the_brief_event_carries_EVERY_questions_confidence(events, wire):
    """`max()` cannot say whether a given consumer crossed its own threshold, which is the only
    thing the number is for. The headline keeps the maximum (the schema has one field); the per
    question map is what a report reads."""
    wire.answers[tb.CANVAS_KEY] = ("show", 0.99)
    wire.answers[tb.ESCALATE_KEY] = ("handle_inline", 0.31)
    _settle(tb.ask("abre la agenda", open_ids=[]))
    ask = [e for e in events if e["label"].startswith("jev turn-brief")]
    assert len(ask) == 1, "one trip must leave one event, or the timeline reads like N trips"
    per_q = ask[0]["extra"]["per_question"]
    assert per_q[tb.CANVAS_KEY]["confidence"] == 0.99
    assert per_q[tb.ESCALATE_KEY]["confidence"] == 0.31, (
        "the unsure escalate verdict is invisible behind the sure canvas one")


def test_the_call_has_an_id_and_the_reads_carry_it(events, wire):
    """The join. Without it, «these two events belong to the same turn» is a claim about clocks."""
    h = _settle(tb.ask("abre la agenda", open_ids=[], turn_id="turn-42"))
    tb.read(h, tb.CANVAS_KEY, "neither")
    ask = next(e for e in events if e["label"].startswith("jev turn-brief"))
    read = next(e for e in events if e["label"].startswith("jev read"))
    assert ask["extra"]["call_id"] and read["extra"]["call_id"] == ask["extra"]["call_id"]
    assert read["extra"]["turn_id"] == "turn-42"


# ── the read: used, or exactly why not ───────────────────────────────────────────────────────────
def test_a_used_verdict_says_so(events, wire):
    wire.answers[tb.CANVAS_KEY] = ("close", 0.98)
    h = _settle(tb.ask("cierra todo", open_ids=[]))
    choice, _ = tb.read(h, tb.CANVAS_KEY, "neither")
    read = next(e for e in events if e["label"] == f"jev read {tb.CANVAS_KEY}")
    assert choice == "close"
    assert (read["extra"]["used"], read["extra"]["why"]) == (True, "used")


def test_an_unsure_verdict_is_recorded_as_UNSURE_not_as_absent(events, wire):
    """The distinction the audit asked for: «the model was not sure» and «there was no model» are
    different facts about the same missing outcome, and only one of them is a quality signal."""
    wire.answers[tb.CANVAS_KEY] = ("close", 0.2)
    h = _settle(tb.ask("cierra todo", open_ids=[]))
    tb.read(h, tb.CANVAS_KEY, "neither")
    read = next(e for e in events if e["label"] == f"jev read {tb.CANVAS_KEY}")
    assert (read["extra"]["used"], read["extra"]["why"]) == (False, "unsure")
    assert read["extra"]["confidence"] == 0.2, "the number that lost is the evidence"


def test_a_brief_still_in_flight_reads_as_IN_FLIGHT(events):
    flying = {"event": threading.Event(), "result": None}
    tb.read(flying, tb.CANVAS_KEY, "neither")
    read = next(e for e in events if e["label"] == f"jev read {tb.CANVAS_KEY}")
    assert read["extra"]["why"] == "in_flight"


def test_no_brief_at_all_reads_as_OFF(events):
    """Jev disabled, no key, an open breaker and an assembly that failed all arrive as `None`.
    Grouped under one word on purpose: from the reader's side they are the same non-event, and the
    ASK event (or its absence) is what tells them apart."""
    tb.read(None, tb.CANVAS_KEY, "neither")
    read = next(e for e in events if e["label"] == f"jev read {tb.CANVAS_KEY}")
    assert (read["extra"]["used"], read["extra"]["why"]) == (False, "off")


def test_reading_the_same_verdict_twice_reports_it_once(events, wire):
    """Bounded on purpose. A consumer in a loop must not be able to fill the operator's timeline —
    the event exists to be counted, and a duplicate would inflate exactly the denominator a report
    divides by."""
    h = _settle(tb.ask("abre la agenda", open_ids=[]))
    for _ in range(5):
        tb.read(h, tb.CANVAS_KEY, "neither")
    reads = [e for e in events if e["label"] == f"jev read {tb.CANVAS_KEY}"]
    assert len(reads) == 1, f"one verdict, one read event — got {len(reads)}"


def test_two_consumers_of_the_same_brief_each_leave_their_own_record(events, wire):
    """The dedupe is per QUESTION, not per brief: the escalate gate and the canvas guard read
    different verdicts out of the same trip and both have to be attributable."""
    h = _settle(tb.ask("cierra todo", open_ids=[]))
    tb.read(h, tb.CANVAS_KEY, "neither")
    tb.read(h, tb.ESCALATE_KEY, "escalate")
    labels = {e["label"] for e in events if e["label"].startswith("jev read")}
    assert labels == {f"jev read {tb.CANVAS_KEY}", f"jev read {tb.ESCALATE_KEY}"}


# ── selection: an empty answer is not an absent one ──────────────────────────────────────────────
def test_nothing_fits_and_nothing_answered_are_different_statuses(wire, monkeypatch):
    rows = [{"id": "t1", "title": "piso en Madrid"}, {"id": "t2", "title": "vuelos a Tokio"}]
    wire.answers["cand_1"] = ("no", 0.9)
    wire.answers["cand_2"] = ("no", 0.9)
    picked, status = jev.select_many_status(rows, "¿es este el encargo?", key=lambda r: r["id"])
    assert (picked, status) == ([], jev.NO_MATCH), "the chooser ran and rejected them: that is an answer"

    def _boom(*a, **k):
        raise OSError("network is down")
    monkeypatch.setattr(jev, "_post_many", _boom)
    jev.reset_breaker()
    picked, status = jev.select_many_status(rows, "¿es este el encargo?", key=lambda r: r["id"])
    assert (picked, status) == ([], jev.UNAVAILABLE), "the chooser never ran: that is an absence"


def test_switched_off_is_its_own_status(wire, monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV", "0")
    picked, status = jev.select_many_status([{"id": "t1"}], "¿es este?", key=lambda r: r["id"])
    assert (picked, status) == ([], jev.DISABLED)


def test_task_recall_asks_differently_when_nobody_answered(wire, monkeypatch):
    """The behaviour the status exists for. Five candidates the chooser REJECTED have been narrowed;
    five it never saw have not. Both end in a question, and only one of them may claim it looked."""
    rows = [{"id": f"t{i}", "title": f"encargo {i}", "goal": "g"} for i in range(1, 4)]
    from nucleo.flash import task_recall as tr
    monkeypatch.setattr(tr, "candidates", lambda q, limit=5: rows)

    wire.answers.update({f"cand_{i}": ("no", 0.9) for i in (1, 2, 3)})
    out = tr.resolve("lo del piso que te dije")
    assert out["ok"] is False and out["how"] == "índice" and out["status"] == jev.NO_MATCH

    def _boom(*a, **k):
        raise OSError("network is down")
    monkeypatch.setattr(jev, "_post_many", _boom)
    jev.reset_breaker()
    out = tr.resolve("lo del piso que te dije")
    assert out["ok"] is False and out["how"] == "sin-chooser" and out["status"] == jev.UNAVAILABLE, (
        "a shortlist nobody looked at was presented as one the chooser had narrowed")


def test_a_single_candidate_still_costs_nothing(wire, monkeypatch):
    """Unchanged by A6a, and worth pinning beside it: one candidate is taken without asking. Paying
    800 ms to confirm what nothing contradicts is the call V2-726 exists to stop making."""
    from nucleo.flash import task_recall as tr
    monkeypatch.setattr(tr, "candidates", lambda q, limit=5: [{"id": "t1", "title": "x"}])
    out = tr.resolve("lo del piso")
    assert out["ok"] is True and out["how"] == "único"
    assert wire.calls == []
